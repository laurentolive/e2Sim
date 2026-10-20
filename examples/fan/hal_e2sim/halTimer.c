/* Example HAL on e2Sim - timers (MIT) */
#include "halTimer.h"
#include "halE2sim.h"

static e2sim_timer_t s_timer[HAL_TIMER_NB];
static halTimer_cb_t s_cb[HAL_TIMER_NB];

static void timer_isr(void *ctx)
{
    halTimer_cb_t cb = s_cb[(uintptr_t)ctx];
    if (cb != NULL)
    {
        cb();
    }
}

void halTimer_Start(halTimer_t id, uint32_t period_us, halTimer_cb_t cb)
{
    e2sim_yield();
    halTimer_Stop(id);
    s_cb[id] = cb;
    s_timer[id] = e2sim_timer_start((uint64_t)period_us * 1000u, true, timer_isr, (void *)(uintptr_t)id);
}

void halTimer_Stop(halTimer_t id)
{
    e2sim_yield();
    if (s_cb[id] != NULL)
    {
        e2sim_timer_stop(s_timer[id]);
        s_cb[id] = NULL;
    }
}

uint32_t halTimer_GetUs(void)
{
    e2sim_yield();
    return (uint32_t)(e2sim_time_ns() / 1000u);
}
