/* Example HAL - non volatile memory (EEPROM like) (MIT) */
#ifndef HALNVM_H
#define HALNVM_H

#include <stddef.h>
#include <stdint.h>

void halNvm_Init(void);
size_t halNvm_Size(void);
void halNvm_Read(uint32_t addr, void *data, size_t len);
void halNvm_Write(uint32_t addr, const void *data, size_t len);

#endif
