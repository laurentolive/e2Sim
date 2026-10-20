/* Example HAL - PWM outputs (MIT) */
#ifndef HALPWM_H
#define HALPWM_H

#include <stdint.h>
#include "halCfg.h"

#define HAL_PWM_MAX 1000u /* duty in per mille */

void halPwm_Init(halPwm_t ch);
void halPwm_SetDuty(halPwm_t ch, uint16_t permille);

#endif
