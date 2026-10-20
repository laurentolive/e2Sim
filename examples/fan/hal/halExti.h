/* Example HAL - external interrupt lines (MIT) */
#ifndef HALEXTI_H
#define HALEXTI_H

#include "halCfg.h"

typedef void (*halExti_cb_t)(void);

void halExti_Init(halExti_t line, halExti_cb_t cb); /* cb in interrupt context, on each edge */

#endif
