/*
 * e2Sim - runner: operating system layer, Linux / POSIX (MIT)
 *
 * Fibers: ucontext (with the AddressSanitizer fiber annotations), firmware: dlopen of a .so, blocks: mmap of a
 * file (/dev/shm for the anonymous ones), memory checks: /proc/self/maps, hang stack: signal to the main thread.
 */
#ifndef _WIN32

#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <link.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

#include "e2sim_os.h"

#if defined(__SANITIZE_ADDRESS__)
#include <sanitizer/common_interface_defs.h>
#define ASAN_FIBERS 1
#endif

typedef struct
{
    ucontext_t uc;
    void *stack;
    size_t size;
    void *fake; /* ASan fake stack of the fiber while switched out */
} fiber_t;

static ucontext_t s_sched_uc;
static fiber_t *s_current;
static os_fiber_fn_t s_fn;
#ifdef ASAN_FIBERS
static void *s_sched_fake;
static const void *s_sched_bottom;
static size_t s_sched_size;
#endif

/*----------------------------------------------------------------------------*/
void os_fiber_init(void) {}

static void fiber_entry(void)
{
#ifdef ASAN_FIBERS
    __sanitizer_finish_switch_fiber(NULL, &s_sched_bottom, &s_sched_size);
#endif
    s_fn();
}

void *os_fiber_create(size_t stack_size, os_fiber_fn_t fn)
{
    fiber_t *f = calloc(1, sizeof(*f));
    if (f == NULL)
    {
        return NULL;
    }
    f->size = stack_size;
    f->stack = mmap(NULL, stack_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
    if (f->stack == MAP_FAILED)
    {
        free(f);
        return NULL;
    }
    getcontext(&f->uc);
    f->uc.uc_stack.ss_sp = f->stack;
    f->uc.uc_stack.ss_size = stack_size;
    f->uc.uc_link = &s_sched_uc;
    s_fn = fn;
    makecontext(&f->uc, fiber_entry, 0);
    return f;
}

void os_fiber_to_app(void *fiber)
{
    fiber_t *f = fiber;
    s_current = f;
#ifdef ASAN_FIBERS
    __sanitizer_start_switch_fiber(&s_sched_fake, f->stack, f->size);
#endif
    swapcontext(&s_sched_uc, &f->uc);
#ifdef ASAN_FIBERS
    __sanitizer_finish_switch_fiber(s_sched_fake, NULL, NULL);
#endif
}

void os_fiber_to_sched(void)
{
    fiber_t *f = s_current;
#ifdef ASAN_FIBERS
    __sanitizer_start_switch_fiber(&f->fake, s_sched_bottom, s_sched_size);
#endif
    swapcontext(&f->uc, &s_sched_uc);
#ifdef ASAN_FIBERS
    __sanitizer_finish_switch_fiber(f->fake, &s_sched_bottom, &s_sched_size);
#endif
}

void os_fiber_delete(void *fiber)
{
    fiber_t *f = fiber;
    if (f == NULL)
    {
        return;
    }
    if (s_current == f)
    {
        s_current = NULL;
    }
    munmap(f->stack, f->size);
    free(f);
}

/*----------------------------------------------------------------------------*/
void *os_lib_load(const char *path, char *err, size_t err_size)
{
    void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (h == NULL)
    {
        snprintf(err, err_size, "%s", dlerror());
    }
    return h;
}

void *os_lib_sym(void *lib, const char *name) { return dlsym(lib, name); }

void os_lib_unload(void *lib) { dlclose(lib); }

uint64_t os_lib_base(void *lib)
{
    struct link_map *lm = NULL;
    if (dlinfo(lib, RTLD_DI_LINKMAP, &lm) != 0 || lm == NULL)
    {
        return 0;
    }
    return (uint64_t)lm->l_addr;
}

uint64_t os_lib_link_base(void *lib)
{
    (void)lib;
    return 0; /* shared object linked at 0: l_addr is the relocation */
}

/*----------------------------------------------------------------------------*/
typedef struct
{
    char path[OS_PATH_MAX];
    bool anonymous;
} posix_block_t;

void *os_block_map(uint16_t idx, const char *path, size_t size, char *name, size_t name_size, bool *fresh,
                   void **handle)
{
    posix_block_t *b = calloc(1, sizeof(*b));
    if (b == NULL)
    {
        return NULL;
    }
    b->anonymous = (path == NULL) || (path[0] == '\0');
    if (b->anonymous)
    {
        snprintf(b->path, sizeof(b->path), "/dev/shm/e2sim_%u_%u", (unsigned)getpid(), idx);
    }
    else
    {
        snprintf(b->path, sizeof(b->path), "%s", path);
    }
    int fd = open(b->path, O_RDWR | O_CREAT, 0644);
    if (fd < 0)
    {
        free(b);
        return NULL;
    }
    struct stat st;
    fstat(fd, &st);
    *fresh = b->anonymous || ((size_t)st.st_size < size);
    if ((size_t)st.st_size < size && ftruncate(fd, (off_t)size) != 0)
    {
        close(fd);
        free(b);
        return NULL;
    }
    void *view = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (view == MAP_FAILED)
    {
        free(b);
        return NULL;
    }
    snprintf(name, name_size, "%s", b->path); /* the host maps the same file */
    *handle = b;
    return view;
}

void os_block_flush(void *view, size_t size, void *handle)
{
    if ((handle != NULL) && !((posix_block_t *)handle)->anonymous)
    {
        msync(view, size, MS_SYNC);
    }
}

void os_block_release(void *handle)
{
    posix_block_t *b = handle;
    if ((b != NULL) && b->anonymous)
    {
        unlink(b->path);
    }
}

/*----------------------------------------------------------------------------*/
bool os_mem_valid(uintptr_t addr, size_t size, bool write)
{
    uintptr_t end = addr + size;
    if ((size == 0u) || (end < addr))
    {
        return false;
    }
    FILE *f = fopen("/proc/self/maps", "r");
    if (f == NULL)
    {
        return false;
    }
    char line[512];
    uintptr_t covered = addr;
    while ((covered < end) && fgets(line, sizeof(line), f))
    {
        unsigned long lo, hi;
        char perms[5];
        if (sscanf(line, "%lx-%lx %4s", &lo, &hi, perms) != 3)
        {
            continue;
        }
        if ((covered >= lo) && (covered < hi))
        {
            if ((perms[0] != 'r') || (write && (perms[1] != 'w')))
            {
                break;
            }
            covered = hi;
        }
    }
    fclose(f);
    return covered >= end;
}

uint32_t os_pid(void) { return (uint32_t)getpid(); }

void os_full_path(char *path, size_t size)
{
    char full[OS_PATH_MAX];
    if (realpath(path, full) != NULL)
    {
        snprintf(path, size, "%s", full);
    }
}

uint32_t os_tick_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)((uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u);
}

void os_sleep_ms(uint32_t ms)
{
    struct timespec ts = {(time_t)(ms / 1000u), (long)(ms % 1000u) * 1000000L};
    nanosleep(&ts, NULL);
}

bool os_debugger_present(void)
{
    FILE *f = fopen("/proc/self/status", "r");
    if (f == NULL)
    {
        return false;
    }
    char line[256];
    int pid = 0;
    while (fgets(line, sizeof(line), f))
    {
        if (sscanf(line, "TracerPid: %d", &pid) == 1)
        {
            break;
        }
    }
    fclose(f);
    return pid != 0;
}

static void *thread_entry(void *arg)
{
    void (*fn)(void);
    memcpy(&fn, &arg, sizeof(fn));
    fn();
    return NULL;
}

void os_thread_start(void (*fn)(void))
{
    pthread_t t;
    void *arg;
    memcpy(&arg, &fn, sizeof(arg));
    pthread_create(&t, NULL, thread_entry, arg);
    pthread_detach(t);
}

/* stack of the main thread: captured by a signal handler on it (frame pointers: -O0 builds) */
static pthread_t s_main;
static volatile sig_atomic_t s_captured;
static uint64_t s_pcs[32];
static unsigned s_n;

static bool in_fiber_stack(uintptr_t fp)
{
    fiber_t *f = s_current;
    return (f != NULL) && (fp >= (uintptr_t)f->stack) && (fp + 2u * sizeof(void *) <= (uintptr_t)f->stack + f->size);
}

static void capture(int sig, siginfo_t *info, void *uctx)
{
    (void)sig;
    (void)info;
    ucontext_t *uc = uctx;
#if defined(__x86_64__)
    uintptr_t pc = (uintptr_t)uc->uc_mcontext.gregs[REG_RIP];
    uintptr_t fp = (uintptr_t)uc->uc_mcontext.gregs[REG_RBP];
#else
    uintptr_t pc = (uintptr_t)uc->uc_mcontext.gregs[REG_EIP];
    uintptr_t fp = (uintptr_t)uc->uc_mcontext.gregs[REG_EBP];
#endif
    unsigned n = 0;
    s_pcs[n++] = pc;
    while ((n < 32u) && in_fiber_stack(fp)) /* only inside the fiber stack: safe to read */
    {
        uintptr_t ret = ((uintptr_t *)fp)[1];
        uintptr_t next = ((uintptr_t *)fp)[0];
        if (ret == 0u)
        {
            break;
        }
        s_pcs[n++] = ret - 1u;
        if (next <= fp)
        {
            break;
        }
        fp = next;
    }
    s_n = n;
    s_captured = 1;
}

void os_main_thread_init(void)
{
    s_main = pthread_self();
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = capture;
    sa.sa_flags = SA_SIGINFO | SA_RESTART;
    sigaction(SIGUSR2, &sa, NULL);
}

unsigned os_main_stack(uint64_t *pcs, unsigned max_frames)
{
    s_captured = 0;
    pthread_kill(s_main, SIGUSR2);
    for (int i = 0; (i < 200) && !s_captured; i++)
    {
        os_sleep_ms(5);
    }
    unsigned n = s_captured ? s_n : 0u;
    if (n > max_frames)
    {
        n = max_frames;
    }
    memcpy(pcs, s_pcs, n * sizeof(uint64_t));
    return n;
}

void os_exit_now(int code) { _exit(code); }

#endif /* !_WIN32 */
