/* Example HAL on e2Sim - external interrupt: event port (MIT) */
#include "halExti.h"
#include "halE2sim.h"

static halExti_cb_t s_cb[HAL_EXTI_NB];

static void exti_isr(void *ctx)
{
    halExti_cb_t cb = s_cb[(uintptr_t)ctx];
    if (cb != NULL)
    {
        cb();
    }
}

void halExti_Init(halExti_t line, halExti_cb_t cb)
{
    e2sim_yield();
    s_cb[line] = cb;
    e2sim_on_input(E2SIM_EVENT, (uint16_t)line, exti_isr, (void *)(uintptr_t)line);
}
