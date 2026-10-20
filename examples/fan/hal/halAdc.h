/* Example HAL - ADC, 12 bits (MIT) */
#ifndef HALADC_H
#define HALADC_H

#include <stdint.h>
#include "halCfg.h"

#define HAL_ADC_MAX 4095u

void halAdc_Init(void);
uint16_t halAdc_Read(halAdc_t channel);

#endif
