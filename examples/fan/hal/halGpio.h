/* Example HAL - GPIO (MIT). Pins: halGpio_t in halCfg.h of the board. */
#ifndef HALGPIO_H
#define HALGPIO_H

#include <stdbool.h>
#include "halCfg.h"

void halGpio_Init(void);
bool halGpio_Read(halGpio_t pin);
void halGpio_Write(halGpio_t pin, bool level);

#endif
