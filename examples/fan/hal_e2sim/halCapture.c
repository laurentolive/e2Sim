/* Example HAL on e2Sim - input capture: the port carries the measured period in us (MIT) */
#include "halCapture.h"
#include "halE2sim.h"

void halCapture_Init(halCapture_t ch)
{
    (void)ch;
    e2sim_yield();
}

uint32_t halCapture_GetPeriodUs(halCapture_t ch)
{
    e2sim_yield();
    int32_t v = e2sim_in(E2SIM_CAPTURE, (uint16_t)ch);
    return (v > 0) ? (uint32_t)v : 0u;
}
