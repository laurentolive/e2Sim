/* Fan example - settings saved in NVM with a CRC (MIT) */
#ifndef SETTINGS_H
#define SETTINGS_H

#include <stdbool.h>
#include <stdint.h>

#define SETTINGS_MAGIC 0xFA01u

typedef struct
{
    uint16_t magic;
    uint8_t speedLevel;
    uint8_t reserved;
    uint32_t runMinutes;
    uint16_t wdtCount;
    uint16_t crc; /* CRC-16 of the fields above */
} settings_t;

extern settings_t settings;

bool settings_Load(void); /* false: missing or corrupted, defaults loaded */
void settings_Save(void);

#endif
