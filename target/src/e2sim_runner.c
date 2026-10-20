/*
 * e2Sim - runner (MIT)
 *
 * Generic process of one simulated firmware instance:
 *  - loads the firmware DLL and runs its main() (renamed e2sim_app_main) in a fiber;
 *  - owns virtual time, timers, interrupts, ports, memory blocks;
 *  - exchanges inputs / outputs with the host once per quantum (MSG_RUN / MSG_DONE);
 *  - reset = fiber destroyed + DLL reloaded: .data / .bss / CRT init of the firmware as at boot,
 *    the process (and an attached debugger) stays.
 *
 * Usage: e2sim_runner --dll <firmware.dll> --host <127.0.0.1:port> [--connect-timeout <ms>]
 */
#define __USE_MINGW_ANSI_STDIO 1
#define E2SIM_RUNNER

#include <windows.h>

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "e2sim.h"
#include "e2sim_wire.h"

#define MAX_TIMERS      64u
#define MAX_PORTS       512u /* power of 2 */
#define MAX_PENDING_ISR 256u
#define MAX_STREAMS     16u
#define STREAM_RX_SIZE  8192u
#define MAX_BLOCKS      16u
#define MAX_SAMPLES     64u
#define SAMPLE_BYTES    1024u
#define FIBER_STACK     (1u << 20)
#define RESET_TIME_NS   100000u /* reset + boot: a reset held active cannot loop at zero time */
#define HANG_FRAMES     16u

typedef int (*app_main_t)(void);

typedef struct
{
    bool active;
    bool periodic;
    uint64_t period;
    uint64_t next;
    e2sim_isr_t isr;
    void *ctx;
} timer_t_;

typedef struct
{
    bool used;
    bool is_out;
    uint32_t key;
    int32_t value;
    e2sim_isr_t isr;
    void *ctx;
} port_t;

typedef struct
{
    e2sim_isr_t isr;
    void *ctx;
} pending_t;

typedef struct
{
    bool used;
    uint16_t idx;
    uint8_t buf[STREAM_RX_SIZE];
    size_t head; /* write */
    size_t tail; /* read */
} stream_rx_t;

typedef struct
{
    bool used;
    uint16_t idx;
    size_t size;
    HANDLE file;
    HANDLE mapping;
    void *view;
    char name[64];
    /* configuration from the host */
    bool cfg;
    uint8_t fill;
    char path[MAX_PATH];
} block_t;

static struct
{
    /* time */
    uint64_t now;
    uint64_t quantum_end;
    uint64_t deadline;
    uint64_t yield_cost;

    /* execution */
    void *sched_fiber;
    void *app_fiber;
    bool in_fiber;
    bool powered;
    bool halted;
    int irq_disabled;
    int reset_pending; /* -1: none, else cause */
    bool reset_process; /* board.yaml reset: process: a reset ends the process, the host starts a new one */
    bool ever_ran;      /* the DLL of this process has run (reset_process: next reset = new process) */
    bool exiting;       /* reset_process: reset reported, the process ends after this RUN */
    e2sim_reset_cause_t reset_cause;

    /* firmware DLL */
    char dll_path[MAX_PATH];
    HMODULE dll;
    app_main_t app_main;

    /* hardware */
    timer_t_ timers[MAX_TIMERS];
    port_t ports[MAX_PORTS];
    pending_t pending[MAX_PENDING_ISR];
    unsigned pending_n;
    stream_rx_t streams[MAX_STREAMS];
    block_t blocks[MAX_BLOCKS];

    /* memory sampling for the host (eScope endpoint): does not change the firmware behaviour */
    uint64_t sample_period;
    uint64_t sample_next;
    unsigned sample_n;
    uintptr_t sample_addr[MAX_SAMPLES];
    uint16_t sample_size[MAX_SAMPLES];
    wbuf_t samples; /* REC_SAMPLE records: do not stop a long run */

    /* host link */
    wbuf_t done;  /* records of MSG_DONE being built */
    wbuf_t tx;    /* scratch for other messages */
    wbuf_t rx;    /* last received message */
} g = {.reset_pending = -1};

/* hang monitor: progress of the RUN being served, watched by a thread (wall clock) */
static volatile LONG s_progress;
static volatile LONG s_in_run;
static HANDLE s_main_thread;
static DWORD s_hang_ms = 3000;
static bool mem_valid(uintptr_t addr, size_t size, bool write);

static void fatal(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "e2sim_runner: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    exit(2);
}

/*============================================================================*/
/* firmware DLL                                                               */
/*============================================================================*/
static void dll_load(void)
{
    g.dll = LoadLibraryA(g.dll_path);
    if (g.dll == NULL)
    {
        fatal("cannot load %s (error %lu)", g.dll_path, GetLastError());
    }
    g.app_main = (app_main_t)(void *)GetProcAddress(g.dll, "e2sim_app_main");
    if (g.app_main == NULL)
    {
        fatal("%s: e2sim_app_main not found (sources built with -Dmain=e2sim_app_main ?)", g.dll_path);
    }
}

static void dll_unload(void)
{
    if (g.dll != NULL)
    {
        FreeLibrary(g.dll);
        g.dll = NULL;
        g.app_main = NULL;
    }
}

/*============================================================================*/
/* ports                                                                      */
/*============================================================================*/
static port_t *port_get(e2sim_class_t c, uint16_t idx)
{
    uint32_t key = ((uint32_t)c << 16) | idx;
    uint32_t h = (key * 2654435761u) & (MAX_PORTS - 1u);
    for (unsigned i = 0; i < MAX_PORTS; i++)
    {
        port_t *p = &g.ports[(h + i) & (MAX_PORTS - 1u)];
        if (!p->used)
        {
            p->used = true;
            p->key = key;
            return p;
        }
        if (p->key == key)
        {
            return p;
        }
    }
    fatal("too many ports");
    return NULL;
}

static stream_rx_t *stream_get(uint16_t idx)
{
    for (unsigned i = 0; i < MAX_STREAMS; i++)
    {
        if (g.streams[i].used && (g.streams[i].idx == idx))
        {
            return &g.streams[i];
        }
    }
    for (unsigned i = 0; i < MAX_STREAMS; i++)
    {
        if (!g.streams[i].used)
        {
            g.streams[i].used = true;
            g.streams[i].idx = idx;
            return &g.streams[i];
        }
    }
    fatal("too many streams");
    return NULL;
}

static block_t *block_find(uint16_t idx, bool create)
{
    for (unsigned i = 0; i < MAX_BLOCKS; i++)
    {
        if (g.blocks[i].used && (g.blocks[i].idx == idx))
        {
            return &g.blocks[i];
        }
    }
    if (!create)
    {
        return NULL;
    }
    for (unsigned i = 0; i < MAX_BLOCKS; i++)
    {
        if (!g.blocks[i].used)
        {
            memset(&g.blocks[i], 0, sizeof(g.blocks[i]));
            g.blocks[i].used = true;
            g.blocks[i].idx = idx;
            return &g.blocks[i];
        }
    }
    fatal("too many blocks");
    return NULL;
}

static void pending_push(e2sim_isr_t isr, void *ctx)
{
    if (isr == NULL)
    {
        return;
    }
    if (g.pending_n >= MAX_PENDING_ISR)
    {
        e2sim_log(E2SIM_LOG_ERROR, "e2sim: pending interrupt queue full");
        return;
    }
    g.pending[g.pending_n].isr = isr;
    g.pending[g.pending_n].ctx = ctx;
    g.pending_n++;
}

/*============================================================================*/
/* scheduler                                                                  */
/*============================================================================*/
static void recompute_deadline(void)
{
    uint64_t d = g.quantum_end;
    if ((g.sample_period != 0u) && (g.sample_next < d))
    {
        d = g.sample_next;
    }
    if (g.irq_disabled == 0)
    {
        if (g.pending_n != 0u)
        {
            d = g.now;
        }
        for (unsigned i = 0; i < MAX_TIMERS; i++)
        {
            if (g.timers[i].active && (g.timers[i].next < d))
            {
                d = g.timers[i].next;
            }
        }
    }
    g.deadline = d;
}

static void to_sched(void)
{
    g.in_fiber = false;
    SwitchToFiber(g.sched_fiber);
    g.in_fiber = true;
}

static void WINAPI fiber_proc(void *arg)
{
    (void)arg;
    g.in_fiber = true;
    int ret = g.app_main();
    e2sim_log(E2SIM_LOG_WARNING, "e2sim: main() returned %d, MCU halted", ret);
    g.halted = true;
    for (;;)
    {
        to_sched();
    }
}

/* run interrupts due at the current time (scheduler context) */
static void service_due(void)
{
    if ((g.irq_disabled != 0) || (g.reset_pending >= 0))
    {
        return;
    }
    for (;;)
    {
        if (g.pending_n != 0u)
        {
            pending_t p = g.pending[0];
            g.pending_n--;
            memmove(&g.pending[0], &g.pending[1], g.pending_n * sizeof(g.pending[0]));
            p.isr(p.ctx);
        }
        else
        {
            int best = -1;
            for (unsigned i = 0; i < MAX_TIMERS; i++)
            {
                timer_t_ *t = &g.timers[i];
                if (t->active && (t->next <= g.now) && ((best < 0) || (t->next < g.timers[best].next)))
                {
                    best = (int)i;
                }
            }
            if (best < 0)
            {
                break;
            }
            timer_t_ *t = &g.timers[best];
            e2sim_isr_t isr = t->isr;
            void *ctx = t->ctx;
            if (t->periodic)
            {
                t->next += t->period;
            }
            else
            {
                t->active = false;
            }
            isr(ctx);
        }
        if ((g.reset_pending >= 0) || (g.irq_disabled != 0))
        {
            break;
        }
    }
}

static void outputs_clear(void)
{
    for (unsigned i = 0; i < MAX_PORTS; i++)
    {
        port_t *p = &g.ports[i];
        p->isr = NULL;
        p->ctx = NULL;
        if (p->used && p->is_out)
        {
            p->value = 0;
        }
    }
}

static void blocks_flush(void)
{
    for (unsigned i = 0; i < MAX_BLOCKS; i++)
    {
        if (g.blocks[i].used && (g.blocks[i].file != NULL))
        {
            FlushViewOfFile(g.blocks[i].view, 0);
        }
    }
}

/* stop the MCU: fiber destroyed, interrupts, timers and buffers cleared */
static void mcu_stop(void)
{
    if (g.app_fiber != NULL)
    {
        DeleteFiber(g.app_fiber);
        g.app_fiber = NULL;
    }
    memset(g.timers, 0, sizeof(g.timers));
    g.pending_n = 0;
    for (unsigned i = 0; i < MAX_STREAMS; i++)
    {
        g.streams[i].head = 0;
        g.streams[i].tail = 0;
    }
    outputs_clear();
    g.irq_disabled = 0;
    g.halted = false;
    blocks_flush();
}

/* restart the MCU as after a reset: DLL reloaded, new fiber (reset_process: the process ends instead) */
static void mcu_boot(e2sim_reset_cause_t cause, bool add_reset_time);

static void mcu_reset(e2sim_reset_cause_t cause)
{
    if (g.reset_process && g.ever_ran)
    {
        mcu_stop();
        g.reset_pending = -1;
        g.exiting = true;
        wbuf_u8(&g.done, REC_RESET);
        wbuf_u8(&g.done, (uint8_t)cause);
        wbuf_u64(&g.done, g.now + RESET_TIME_NS); /* the new process starts at this time */
        wbuf_u64(&g.done, (uint64_t)(uintptr_t)g.dll);
        return;
    }
    mcu_boot(cause, true);
}

static void mcu_boot(e2sim_reset_cause_t cause, bool add_reset_time)
{
    mcu_stop();
    dll_unload();
    dll_load();
    if (add_reset_time)
    {
        g.now += RESET_TIME_NS;
    }
    g.ever_ran = true;
    g.reset_cause = cause;
    g.reset_pending = -1;
    wbuf_u8(&g.done, REC_RESET);
    wbuf_u8(&g.done, (uint8_t)cause);
    wbuf_u64(&g.done, g.now);
    wbuf_u64(&g.done, (uint64_t)(uintptr_t)g.dll);
    if (g.powered)
    {
        g.app_fiber = CreateFiber(FIBER_STACK, fiber_proc, NULL);
        if (g.app_fiber == NULL)
        {
            fatal("CreateFiber failed (error %lu)", GetLastError());
        }
    }
}

static uint64_t next_timer(void)
{
    uint64_t d = UINT64_MAX;
    for (unsigned i = 0; i < MAX_TIMERS; i++)
    {
        if (g.timers[i].active && (g.timers[i].next < d))
        {
            d = g.timers[i].next;
        }
    }
    return d;
}

/* samples due at the current time (scheduler context, between two runs of the fiber) */
static void sample_due(void)
{
    while ((g.sample_period != 0u) && (g.sample_next <= g.now))
    {
        size_t n = 0;
        for (unsigned i = 0; i < g.sample_n; i++)
        {
            n += g.sample_size[i];
        }
        wbuf_u8(&g.samples, REC_SAMPLE);
        wbuf_u64(&g.samples, g.sample_next);
        wbuf_u16(&g.samples, (uint16_t)n);
        for (unsigned i = 0; i < g.sample_n; i++)
        {
            wbuf_bytes(&g.samples, (const void *)g.sample_addr[i], g.sample_size[i]);
        }
        g.sample_next += g.sample_period;
    }
}

/* MCU not running: no sample, the next one after the time jump */
static void sample_skip(uint64_t until)
{
    if ((g.sample_period != 0u) && (g.sample_next < until))
    {
        g.sample_next += (until - g.sample_next + g.sample_period - 1u) / g.sample_period * g.sample_period;
    }
}

/* one quantum (or up to until): same code path as one RUN of the host */
static void run_slice(uint64_t until)
{
    g.quantum_end = until;
    for (;;)
    {
        if (g.exiting)
        {
            break;
        }
        service_due();
        if (g.powered && (g.app_fiber != NULL))
        {
            sample_due();
        }
        if (g.reset_pending >= 0)
        {
            mcu_reset((e2sim_reset_cause_t)g.reset_pending);
            continue; /* exiting: leaves at the top of the loop */
        }
        if (!g.powered || (g.app_fiber == NULL))
        {
            if (g.now < until)
            {
                g.now = until;
            }
            sample_skip(until);
            break;
        }
        if (g.halted)
        {
            /* main() returned: only interrupts run */
            uint64_t t = next_timer();
            if ((g.irq_disabled != 0) || (t >= until))
            {
                if (g.now < until)
                {
                    g.now = until;
                }
                break;
            }
            if (t > g.now)
            {
                g.now = t;
            }
            continue;
        }
        if (g.now >= until)
        {
            break;
        }
        recompute_deadline();
        g.in_fiber = true;
        SwitchToFiber(g.app_fiber);
        g.in_fiber = false;
    }
}

/* run quantum after quantum from the host boundary 'from', until 'until' or the end of the first quantum
   that produced a record (output, stream, log, reset...): exactly as if the host had sent one empty RUN
   per quantum, without the round trips. q = 0: one slice. Returns the boundary reached. */
static uint64_t run_until(uint64_t from, uint64_t until, uint64_t q)
{
    uint64_t end = ((q != 0u) && (from + q < until)) ? from + q : until;
    for (;;)
    {
        run_slice(end);
        if ((end >= until) || (g.done.n != 0u) || g.exiting) /* records of the RUN itself (reset...) included */
        {
            return end;
        }
        end = (end + q < until) ? end + q : until;
    }
}

/*============================================================================*/
/* API: time and execution                                                    */
/*============================================================================*/
E2SIM_API uint64_t e2sim_time_ns(void) { return g.now; }

E2SIM_API void e2sim_yield(void)
{
    s_progress++;
    if (!g.in_fiber)
    {
        return;
    }
    g.now += g.yield_cost;
    if (g.now >= g.deadline)
    {
        to_sched();
    }
}

E2SIM_API void e2sim_idle(void)
{
    s_progress++;
    if (!g.in_fiber)
    {
        return;
    }
    recompute_deadline();
    if (g.deadline > g.now)
    {
        g.now = g.deadline;
    }
    to_sched();
}

E2SIM_API void e2sim_reset(e2sim_reset_cause_t cause)
{
    g.reset_pending = (int)cause;
    if (g.in_fiber)
    {
        for (;;)
        {
            to_sched(); /* the fiber is deleted by the scheduler */
        }
    }
}

E2SIM_API e2sim_reset_cause_t e2sim_reset_cause(void) { return g.reset_cause; }

/*============================================================================*/
/* API: ports                                                                 */
/*============================================================================*/
E2SIM_API int32_t e2sim_in(e2sim_class_t c, uint16_t idx) { return port_get(c, idx)->value; }

E2SIM_API void e2sim_out(e2sim_class_t c, uint16_t idx, int32_t v)
{
    port_t *p = port_get(c, idx);
    p->is_out = true;
    if (p->value == v)
    {
        return;
    }
    p->value = v;
    wbuf_u8(&g.done, REC_OUT);
    wbuf_u8(&g.done, (uint8_t)c);
    wbuf_u16(&g.done, idx);
    wbuf_u32(&g.done, (uint32_t)v);
    wbuf_u64(&g.done, g.now);
}

E2SIM_API void e2sim_event_out(uint16_t idx)
{
    wbuf_u8(&g.done, REC_EVENT);
    wbuf_u16(&g.done, idx);
    wbuf_u64(&g.done, g.now);
}

E2SIM_API size_t e2sim_stream_read(uint16_t idx, uint8_t *buf, size_t max)
{
    stream_rx_t *s = stream_get(idx);
    size_t n = 0;
    while ((n < max) && (s->tail != s->head))
    {
        buf[n++] = s->buf[s->tail];
        s->tail = (s->tail + 1u) % STREAM_RX_SIZE;
    }
    return n;
}

E2SIM_API void e2sim_stream_write(uint16_t idx, const uint8_t *buf, size_t len)
{
    while (len != 0u)
    {
        size_t chunk = (len > 0xFFFFu) ? 0xFFFFu : len;
        wbuf_u8(&g.done, REC_STREAM);
        wbuf_u16(&g.done, idx);
        wbuf_u64(&g.done, g.now);
        wbuf_u16(&g.done, (uint16_t)chunk);
        wbuf_bytes(&g.done, buf, chunk);
        buf += chunk;
        len -= chunk;
    }
}

E2SIM_API size_t e2sim_xfer(e2sim_class_t c, uint16_t idx, const uint8_t *tx, size_t tx_len, uint8_t *rx,
                            size_t rx_max)
{
    if (tx_len > 0xFFFFu)
    {
        tx_len = 0xFFFFu;
    }
    wbuf_reset(&g.tx);
    wbuf_u8(&g.tx, (uint8_t)c);
    wbuf_u16(&g.tx, idx);
    wbuf_u64(&g.tx, g.now);
    wbuf_u16(&g.tx, (uint16_t)tx_len);
    wbuf_bytes(&g.tx, tx, tx_len);
    s_in_run = 0; /* the host answers: its time is not a hang of the firmware */
    if (wire_send(MSG_XFER_REQ, &g.tx) != 0)
    {
        fatal("host link lost");
    }
    uint8_t type;
    if ((wire_recv(&type, &g.rx) != 0) || (type != MSG_XFER_REPLY))
    {
        fatal("host link lost (xfer)");
    }
    s_progress++;
    s_in_run = 1;
    rbuf_t r = {g.rx.p, g.rx.n, 0, 0};
    uint64_t cost = rbuf_u64(&r);
    size_t n = rbuf_u16(&r);
    const uint8_t *data = rbuf_bytes(&r, n);
    size_t copy = (n < rx_max) ? n : rx_max;
    if ((data != NULL) && (copy != 0u))
    {
        memcpy(rx, data, copy);
    }
    if (g.in_fiber)
    {
        g.now += cost;
    }
    return copy;
}

E2SIM_API void *e2sim_block(uint16_t idx, size_t size)
{
    block_t *b = block_find(idx, true);
    if (b->view != NULL)
    {
        if (size > b->size)
        {
            fatal("block %u: size %zu requested, %zu already mapped", idx, size, b->size);
        }
        return b->view;
    }
    b->size = size;
    snprintf(b->name, sizeof(b->name), "Local\\e2sim_%lu_%u", GetCurrentProcessId(), idx);
    HANDLE file = INVALID_HANDLE_VALUE;
    bool fresh = true;
    if (b->cfg && (b->path[0] != '\0'))
    {
        file = CreateFileA(b->path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file == INVALID_HANDLE_VALUE)
        {
            fatal("block %u: cannot open %s (error %lu)", idx, b->path, GetLastError());
        }
        LARGE_INTEGER cur;
        GetFileSizeEx(file, &cur);
        fresh = ((uint64_t)cur.QuadPart < size);
        b->file = file;
    }
    b->mapping = CreateFileMappingA(file, NULL, PAGE_READWRITE, (DWORD)((uint64_t)size >> 32), (DWORD)size, b->name);
    if (b->mapping == NULL)
    {
        fatal("block %u: CreateFileMapping failed (error %lu)", idx, GetLastError());
    }
    b->view = MapViewOfFile(b->mapping, FILE_MAP_ALL_ACCESS, 0, 0, size);
    if (b->view == NULL)
    {
        fatal("block %u: MapViewOfFile failed (error %lu)", idx, GetLastError());
    }
    if (fresh)
    {
        memset(b->view, b->cfg ? b->fill : 0, size);
    }
    wbuf_u8(&g.done, REC_BLOCK);
    wbuf_u16(&g.done, idx);
    wbuf_u32(&g.done, (uint32_t)size);
    wbuf_str(&g.done, b->name);
    return b->view;
}

/*============================================================================*/
/* API: interrupts                                                            */
/*============================================================================*/
E2SIM_API e2sim_timer_t e2sim_timer_start(uint64_t period_ns, bool periodic, e2sim_isr_t isr, void *ctx)
{
    if ((isr == NULL) || (period_ns == 0u))
    {
        return -1;
    }
    for (unsigned i = 0; i < MAX_TIMERS; i++)
    {
        timer_t_ *t = &g.timers[i];
        if (!t->active)
        {
            t->active = true;
            t->periodic = periodic;
            t->period = period_ns;
            t->next = g.now + period_ns;
            t->isr = isr;
            t->ctx = ctx;
            if (t->next < g.deadline)
            {
                g.deadline = t->next;
            }
            return (e2sim_timer_t)i;
        }
    }
    fatal("too many timers");
    return -1;
}

E2SIM_API void e2sim_timer_stop(e2sim_timer_t t)
{
    if ((t >= 0) && ((unsigned)t < MAX_TIMERS))
    {
        g.timers[t].active = false;
    }
}

E2SIM_API void e2sim_on_input(e2sim_class_t c, uint16_t idx, e2sim_isr_t isr, void *ctx)
{
    port_t *p = port_get(c, idx);
    p->isr = isr;
    p->ctx = ctx;
}

E2SIM_API void e2sim_irq_disable(void) { g.irq_disabled++; }

E2SIM_API void e2sim_irq_enable(void)
{
    if (g.irq_disabled > 0)
    {
        g.irq_disabled--;
    }
    if (g.irq_disabled == 0)
    {
        recompute_deadline();
        if (g.in_fiber && (g.deadline <= g.now))
        {
            to_sched();
        }
    }
}

/*============================================================================*/
/* API: diagnostic                                                            */
/*============================================================================*/
E2SIM_API void e2sim_log(e2sim_log_level_t level, const char *fmt, ...)
{
    char text[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(text, sizeof(text), fmt, ap);
    va_end(ap);
    wbuf_u8(&g.done, REC_LOG);
    wbuf_u64(&g.done, g.now);
    wbuf_u8(&g.done, (uint8_t)level);
    wbuf_str(&g.done, text);
}

/*============================================================================*/
/* host link                                                                  */
/*============================================================================*/
static bool mem_valid(uintptr_t addr, size_t size, bool write)
{
    DWORD ok = write ? (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)
                     : (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READ |
                        PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY);
    uintptr_t end = addr + size;
    if ((size == 0u) || (end < addr))
    {
        return false;
    }
    while (addr < end)
    {
        MEMORY_BASIC_INFORMATION mbi;
        if (VirtualQuery((const void *)addr, &mbi, sizeof(mbi)) == 0)
        {
            return false;
        }
        if ((mbi.State != MEM_COMMIT) || ((mbi.Protect & ok) == 0u) || ((mbi.Protect & PAGE_GUARD) != 0u))
        {
            return false;
        }
        addr = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
    }
    return true;
}

E2SIM_API bool e2sim_mem_valid(const void *addr, size_t size, bool write)
{
    return mem_valid((uintptr_t)addr, size, write);
}

static void handle_run(void)
{
    rbuf_t r = {g.rx.p, g.rx.n, 0, 0};
    wbuf_reset(&g.samples);
    uint64_t until = rbuf_u64(&r);
    uint64_t from = rbuf_u64(&r);
    uint64_t quantum = rbuf_u64(&r);
    uint64_t end = until;
    wbuf_reset(&g.done);

    for (;;)
    {
        uint8_t rec = rbuf_u8(&r);
        if (r.error || (rec == REC_END))
        {
            break;
        }
        switch (rec)
        {
        case REC_IN:
        {
            e2sim_class_t c = (e2sim_class_t)rbuf_u8(&r);
            uint16_t idx = rbuf_u16(&r);
            int32_t v = (int32_t)rbuf_u32(&r);
            port_t *p = port_get(c, idx);
            if (p->value != v)
            {
                p->value = v;
                if (g.app_fiber != NULL)
                {
                    pending_push(p->isr, p->ctx);
                }
            }
            break;
        }
        case REC_STREAM_IN:
        {
            uint16_t idx = rbuf_u16(&r);
            size_t n = rbuf_u16(&r);
            const uint8_t *data = rbuf_bytes(&r, n);
            stream_rx_t *s = stream_get(idx);
            for (size_t i = 0; (data != NULL) && (i < n); i++)
            {
                size_t next = (s->head + 1u) % STREAM_RX_SIZE;
                if (next == s->tail)
                {
                    e2sim_log(E2SIM_LOG_ERROR, "e2sim: stream %u rx overflow", idx);
                    break;
                }
                s->buf[s->head] = data[i];
                s->head = next;
            }
            if (g.app_fiber != NULL)
            {
                port_t *p = port_get(E2SIM_UART, idx);
                pending_push(p->isr, p->ctx);
            }
            break;
        }
        case REC_EVENT_IN:
        {
            port_t *p = port_get(E2SIM_EVENT, rbuf_u16(&r));
            if (g.app_fiber != NULL)
            {
                pending_push(p->isr, p->ctx);
            }
            break;
        }
        case REC_RESET_IN:
        {
            e2sim_reset_cause_t cause = (e2sim_reset_cause_t)rbuf_u8(&r);
            if (g.powered)
            {
                mcu_reset(cause);
            }
            break;
        }
        case REC_POWER:
        {
            bool on = rbuf_u8(&r) != 0u;
            if (on && !g.powered)
            {
                g.powered = true;
                mcu_reset(E2SIM_RESET_POWER_ON);
            }
            else if (!on && g.powered)
            {
                g.powered = false;
                mcu_stop();
            }
            break;
        }
        case REC_MEM_READ:
        {
            uint32_t id = rbuf_u32(&r);
            uintptr_t addr = (uintptr_t)rbuf_u64(&r);
            uint32_t size = rbuf_u32(&r);
            bool ok = (size <= 0xFFFFu) && mem_valid(addr, size, false);
            wbuf_u8(&g.done, REC_MEM);
            wbuf_u32(&g.done, id);
            wbuf_u8(&g.done, ok ? MEM_OK : MEM_INVALID);
            wbuf_u16(&g.done, ok ? (uint16_t)size : 0u);
            if (ok)
            {
                wbuf_bytes(&g.done, (const void *)addr, size);
            }
            break;
        }
        case REC_MEM_WRITE:
        {
            uint32_t id = rbuf_u32(&r);
            uintptr_t addr = (uintptr_t)rbuf_u64(&r);
            size_t n = rbuf_u16(&r);
            const uint8_t *data = rbuf_bytes(&r, n);
            bool ok = (data != NULL) && mem_valid(addr, n, true);
            if (ok)
            {
                memcpy((void *)addr, data, n);
            }
            wbuf_u8(&g.done, REC_MEM);
            wbuf_u32(&g.done, id);
            wbuf_u8(&g.done, ok ? MEM_OK : MEM_INVALID);
            wbuf_u16(&g.done, 0);
            break;
        }
        case REC_SAMPLE_CFG:
        {
            uint64_t period = rbuf_u64(&r);
            unsigned n = rbuf_u16(&r);
            size_t bytes = 0;
            int bad = -1;
            for (unsigned i = 0; i < n; i++)
            {
                uintptr_t addr = (uintptr_t)rbuf_u64(&r);
                uint16_t size = rbuf_u16(&r);
                if ((i < MAX_SAMPLES) && mem_valid(addr, size, false) && (bytes + size <= SAMPLE_BYTES))
                {
                    g.sample_addr[i] = addr;
                    g.sample_size[i] = size;
                    bytes += size;
                }
                else if (bad < 0)
                {
                    bad = (int)i;
                }
            }
            g.sample_n = (bad < 0) ? n : 0u;
            g.sample_period = ((bad < 0) && (n != 0u)) ? period : 0u;
            g.sample_next = g.now - g.now % ((period != 0u) ? period : 1u) + period; /* aligned on the period */
            wbuf_u8(&g.done, REC_SAMPLE_ACK);
            wbuf_u8(&g.done, (bad < 0) ? MEM_OK : MEM_INVALID);
            wbuf_u16(&g.done, (uint16_t)((bad < 0) ? 0 : bad));
            break;
        }
        default:
            fatal("unknown record 0x%02x", rec);
        }
    }
    if (r.error)
    {
        fatal("malformed RUN message");
    }

    if (until > g.now)
    {
        end = run_until(from, until, quantum);
    }
    else
    {
        g.quantum_end = g.now;
        service_due(); /* inputs changed at zero time: their interrupts still run */
        if (g.reset_pending >= 0)
        {
            mcu_reset((e2sim_reset_cause_t)g.reset_pending);
        }
    }

    wbuf_reset(&g.tx);
    wbuf_u64(&g.tx, g.now);
    wbuf_u64(&g.tx, end);
    wbuf_u8(&g.tx, g.powered ? 1u : 0u);
    wbuf_u8(&g.tx, g.halted ? 1u : 0u);
    wbuf_u8(&g.tx, g.exiting ? 1u : 0u);
    wbuf_bytes(&g.tx, g.done.p, g.done.n);
    wbuf_bytes(&g.tx, g.samples.p, g.samples.n);
    wbuf_u8(&g.tx, REC_END);
    if (wire_send(MSG_DONE, &g.tx) != 0)
    {
        fatal("host link lost");
    }
}

static void handle_config(void)
{
    rbuf_t r = {g.rx.p, g.rx.n, 0, 0};
    g.yield_cost = rbuf_u64(&r);
    unsigned n = rbuf_u16(&r);
    for (unsigned i = 0; i < n; i++)
    {
        block_t *b = block_find(rbuf_u16(&r), true);
        b->cfg = true;
        b->fill = rbuf_u8(&r);
        rbuf_str(&r, b->path, sizeof(b->path));
    }
    g.reset_process = rbuf_u8(&r) != 0u;
    uint64_t start = rbuf_u64(&r);
    uint8_t boot = rbuf_u8(&r);
    char shm[96];
    rbuf_str(&r, shm, sizeof(shm));
    uint32_t host_pid = rbuf_u32(&r);
    if (r.error)
    {
        fatal("malformed CONFIG message");
    }
    if ((shm[0] != '\0') && (wire_use_shm(shm, host_pid) != 0))
    {
        fatal("cannot open the shared memory %s of the host", shm);
    }
    g.now = start;
    if (boot != 0xFFu) /* new process after a reset (reset_process): boot at once */
    {
        g.powered = true;
        mcu_boot((e2sim_reset_cause_t)boot, false);
    }
}

/*============================================================================*/
/* hang monitor: a RUN without any yield point for s_hang_ms of wall clock (and no debugger attached) is a
   loop of the firmware that never calls the HAL. Its stack is sent to the host (frame pointers: -O0), then
   the process ends. */
static DWORD WINAPI hang_monitor(void *arg)
{
    (void)arg;
    LONG last = -1;
    DWORD since = GetTickCount();
    for (;;)
    {
        Sleep(100);
        LONG p = s_progress;
        if (!s_in_run || (p != last) || IsDebuggerPresent())
        {
            last = p;
            since = GetTickCount();
            continue;
        }
        if (GetTickCount() - since < s_hang_ms)
        {
            continue;
        }
        SuspendThread(s_main_thread);
        CONTEXT ctx __attribute__((aligned(16)));
        memset(&ctx, 0, sizeof(ctx));
        ctx.ContextFlags = CONTEXT_FULL;
        uint64_t pcs[HANG_FRAMES];
        unsigned n = 0;
        if (GetThreadContext(s_main_thread, &ctx))
        {
#if defined(__x86_64__)
            /* x64: unwind tables of the PE (the frame pointer chain is not reliable) */
            while ((n < HANG_FRAMES) && (ctx.Rip != 0u))
            {
                pcs[n] = (n == 0u) ? ctx.Rip : ctx.Rip - 1u; /* return address: inside the call */
                n++;
                DWORD64 base;
                PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry(ctx.Rip, &base, NULL);
                if (fn == NULL)
                {
                    if (!mem_valid((uintptr_t)ctx.Rsp, 8u, false))
                    {
                        break;
                    }
                    ctx.Rip = *(DWORD64 *)ctx.Rsp; /* leaf function */
                    ctx.Rsp += 8u;
                }
                else
                {
                    PVOID handler;
                    DWORD64 frame;
                    RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, ctx.Rip, fn, &ctx, &handler, &frame, NULL);
                }
            }
#else
            uintptr_t fp = (uintptr_t)ctx.Ebp;
            pcs[n++] = (uintptr_t)ctx.Eip;
            while ((n < HANG_FRAMES) && (fp != 0u) && mem_valid(fp, 2u * sizeof(void *), false))
            {
                uintptr_t ret = ((uintptr_t *)fp)[1];
                uintptr_t next = ((uintptr_t *)fp)[0];
                if (ret == 0u)
                {
                    break;
                }
                pcs[n++] = ret - 1u; /* inside the call instruction */
                if (next <= fp)
                {
                    break;
                }
                fp = next;
            }
#endif
        }
        wbuf_t msg = {0};
        wbuf_u64(&msg, g.now);
        wbuf_u8(&msg, (uint8_t)n);
        for (unsigned i = 0; i < n; i++)
        {
            wbuf_u64(&msg, pcs[i]);
        }
        wire_send(MSG_HANG, &msg);
        fprintf(stderr, "e2sim_runner: no yield point for %lu ms: firmware loop without HAL call\n",
                (unsigned long)s_hang_ms);
        ExitProcess(3);
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *host = "127.0.0.1:47600";
    uint32_t timeout_ms = 30000;
    g.dll_path[0] = '\0';
    for (int i = 1; i < argc; i++)
    {
        if ((strcmp(argv[i], "--dll") == 0) && (i + 1 < argc))
        {
            snprintf(g.dll_path, sizeof(g.dll_path), "%s", argv[++i]);
        }
        else if ((strcmp(argv[i], "--host") == 0) && (i + 1 < argc))
        {
            host = argv[++i];
        }
        else if ((strcmp(argv[i], "--connect-timeout") == 0) && (i + 1 < argc))
        {
            timeout_ms = (uint32_t)strtoul(argv[++i], NULL, 0);
        }
        else if ((strcmp(argv[i], "--hang-timeout") == 0) && (i + 1 < argc))
        {
            s_hang_ms = (DWORD)strtoul(argv[++i], NULL, 0); /* 0: no hang detection */
        }
        else
        {
            fatal("usage: e2sim_runner --dll <firmware.dll> --host <ip:port> [--connect-timeout <ms, 0: forever>]");
        }
    }
    if (g.dll_path[0] == '\0')
    {
        fatal("--dll missing");
    }
    char ip[64];
    const char *colon = strrchr(host, ':');
    if ((colon == NULL) || ((size_t)(colon - host) >= sizeof(ip)))
    {
        fatal("--host: ip:port expected");
    }
    memcpy(ip, host, (size_t)(colon - host));
    ip[colon - host] = '\0';
    uint16_t port = (uint16_t)strtoul(colon + 1, NULL, 10);

    /* absolute path: the DLL is reloaded at each reset */
    char full[MAX_PATH];
    if (GetFullPathNameA(g.dll_path, sizeof(full), full, NULL) != 0)
    {
        snprintf(g.dll_path, sizeof(g.dll_path), "%s", full);
    }

    g.yield_cost = 1000;
    DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &s_main_thread, 0, FALSE,
                    DUPLICATE_SAME_ACCESS);
    if (s_hang_ms != 0u)
    {
        CreateThread(NULL, 0, hang_monitor, NULL, 0, NULL);
    }
    g.sched_fiber = ConvertThreadToFiber(NULL);
    if (g.sched_fiber == NULL)
    {
        fatal("ConvertThreadToFiber failed");
    }
    dll_load();

    if (wire_connect(ip, port, timeout_ms) != 0)
    {
        fatal("cannot connect to the host %s", host);
    }
    wbuf_reset(&g.tx);
    wbuf_u32(&g.tx, WIRE_VERSION);
    wbuf_u8(&g.tx, (uint8_t)sizeof(void *));
    wbuf_u64(&g.tx, (uint64_t)(uintptr_t)g.dll);
    wbuf_u32(&g.tx, GetCurrentProcessId());
    wbuf_str(&g.tx, g.dll_path);
    if (wire_send(MSG_HELLO, &g.tx) != 0)
    {
        fatal("host link lost");
    }

    for (;;)
    {
        uint8_t type;
        if (wire_recv(&type, &g.rx) != 0)
        {
            break; /* host gone */
        }
        if (type == MSG_CONFIG)
        {
            handle_config();
        }
        else if (type == MSG_RUN)
        {
            s_progress++;
            s_in_run = 1;
            handle_run();
            s_in_run = 0;
            if (g.exiting)
            {
                break; /* reset_process: the host starts a new process */
            }
        }
        else if (type == MSG_QUIT)
        {
            break;
        }
        else
        {
            fatal("unexpected message 0x%02x", type);
        }
    }
    mcu_stop();
    wire_close();
    return 0;
}
