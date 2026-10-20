/* Example HAL on e2Sim - watchdog: one shot timer in virtual time, reset on expiry (MIT) */
#include "halWdt.h"
#include "halE2sim.h"

static e2sim_timer_t s_timer = -1;
static uint64_t s_timeout_ns;

static void wdt_isr(void *ctx)
{
    (void)ctx;
    e2sim_log(E2SIM_LOG_WARNING, "watchdog expired");
    e2sim_reset(E2SIM_RESET_WDT);
}

void halWdt_Init(uint32_t timeout_ms)
{
    e2sim_yield();
    s_timeout_ns = (uint64_t)timeout_ms * 1000000u;
    s_timer = e2sim_timer_start(s_timeout_ns, false, wdt_isr, NULL);
}

void halWdt_Refresh(void)
{
    e2sim_yield();
    if (s_timer >= 0)
    {
        e2sim_timer_stop(s_timer);
        s_timer = e2sim_timer_start(s_timeout_ns, false, wdt_isr, NULL);
    }
}
