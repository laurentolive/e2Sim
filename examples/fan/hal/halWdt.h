/* Example HAL - watchdog (MIT) */
#ifndef HALWDT_H
#define HALWDT_H

#include <stdint.h>

void halWdt_Init(uint32_t timeout_ms);
void halWdt_Refresh(void);

#endif
