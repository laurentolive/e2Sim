/* Example HAL - input capture: period between two edges (MIT) */
#ifndef HALCAPTURE_H
#define HALCAPTURE_H

#include <stdint.h>
#include "halCfg.h"

void halCapture_Init(halCapture_t ch);
uint32_t halCapture_GetPeriodUs(halCapture_t ch); /* 0: no edge (input stopped) */

#endif
