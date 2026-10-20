/* Example HAL - UART, buffered (MIT) */
#ifndef HALUART_H
#define HALUART_H

#include <stddef.h>
#include <stdint.h>
#include "halCfg.h"

void halUart_Init(halUart_t uart, uint32_t baudrate);
void halUart_Write(halUart_t uart, const uint8_t *data, size_t len);
size_t halUart_Read(halUart_t uart, uint8_t *data, size_t max); /* non blocking */

#endif
