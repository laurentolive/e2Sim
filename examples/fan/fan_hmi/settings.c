/* Fan example - settings (MIT) */
#include <stddef.h>

#include "crc16.h"
#include "halNvm.h"
#include "settings.h"

settings_t settings;

static uint16_t compute_crc(const settings_t *s) { return crc16(s, offsetof(settings_t, crc)); }

bool settings_Load(void)
{
    halNvm_Read(0, &settings, sizeof(settings));
    if ((settings.magic == SETTINGS_MAGIC) && (settings.crc == compute_crc(&settings)) &&
        (settings.speedLevel >= 1u) && (settings.speedLevel <= 5u))
    {
        return true;
    }
    settings.magic = SETTINGS_MAGIC;
    settings.speedLevel = 1;
    settings.reserved = 0;
    settings.runMinutes = 0;
    settings.wdtCount = 0;
    return false;
}

void settings_Save(void)
{
    settings.crc = compute_crc(&settings);
    halNvm_Write(0, &settings, sizeof(settings));
}
