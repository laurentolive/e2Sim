/* Example HAL on e2Sim - PWM: the port carries the duty in per mille (MIT) */
#include "halPwm.h"
#include "halE2sim.h"

void halPwm_Init(halPwm_t ch)
{
    e2sim_yield();
    e2sim_out(E2SIM_PWM, (uint16_t)ch, 0);
}

void halPwm_SetDuty(halPwm_t ch, uint16_t permille)
{
    e2sim_yield();
    e2sim_out(E2SIM_PWM, (uint16_t)ch, (permille > HAL_PWM_MAX) ? (int32_t)HAL_PWM_MAX : (int32_t)permille);
}
