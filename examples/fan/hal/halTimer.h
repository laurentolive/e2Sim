/* Example HAL - timers (MIT) */
#ifndef HALTIMER_H
#define HALTIMER_H

#include <stdint.h>
#include "halCfg.h"

typedef void (*halTimer_cb_t)(void);

void halTimer_Start(halTimer_t id, uint32_t period_us, halTimer_cb_t cb); /* periodic, cb in interrupt */
void halTimer_Stop(halTimer_t id);
uint32_t halTimer_GetUs(void); /* free running microsecond counter */

#endif
