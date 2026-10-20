/* Example HAL - SPI master, full duplex (MIT) */
#ifndef HALSPI_H
#define HALSPI_H

#include <stddef.h>
#include <stdint.h>
#include "halCfg.h"

void halSpi_Init(halSpi_t bus);
void halSpi_Transfer(halSpi_t bus, const uint8_t *tx, uint8_t *rx, size_t len); /* returns with rx filled */

#endif
