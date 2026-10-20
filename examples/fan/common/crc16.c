/* Fan example - CRC-16/CCITT-FALSE (MIT) */
#include "crc16.h"

uint16_t crc16(const void *data, size_t len)
{
    const uint8_t *p = data;
    uint16_t crc = 0xFFFFu;
    for (size_t i = 0; i < len; i++)
    {
        crc ^= (uint16_t)((uint16_t)p[i] << 8);
        for (int b = 0; b < 8; b++)
        {
            crc = (uint16_t)((crc & 0x8000u) ? ((unsigned)crc << 1) ^ 0x1021u : ((unsigned)crc << 1));
        }
    }
    return crc;
}
