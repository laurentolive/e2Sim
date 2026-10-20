/* Fan example - HMI <-> motor board protocol (MIT) */
#include "fanProto.h"

enum
{
    ST_SOF = 0,
    ST_CMD,
    ST_LEN,
    ST_PAYLOAD,
    ST_CRC,
};

uint8_t fanProto_Crc8(uint8_t crc, const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++)
    {
        crc ^= data[i];
        for (int b = 0; b < 8; b++)
        {
            crc = (uint8_t)((crc & 0x80u) ? ((unsigned)crc << 1) ^ 0x07u : ((unsigned)crc << 1));
        }
    }
    return crc;
}

size_t fanProto_Encode(uint8_t cmd, const uint8_t *payload, uint8_t len, uint8_t *out)
{
    if (len > FANPROTO_MAX_PAYLOAD)
    {
        return 0;
    }
    out[0] = FANPROTO_SOF;
    out[1] = cmd;
    out[2] = len;
    for (uint8_t i = 0; i < len; i++)
    {
        out[3u + i] = payload[i];
    }
    out[3u + len] = fanProto_Crc8(0, &out[1], 2u + len);
    return 4u + len;
}

void fanProto_ParserInit(fanProto_parser_t *p)
{
    p->state = ST_SOF;
    p->errors = 0;
}

bool fanProto_Parse(fanProto_parser_t *p, uint8_t byte)
{
    switch (p->state)
    {
    case ST_SOF:
        if (byte == FANPROTO_SOF)
        {
            p->state = ST_CMD;
        }
        break;
    case ST_CMD:
        p->frame.cmd = byte;
        p->crc = fanProto_Crc8(0, &byte, 1);
        p->state = ST_LEN;
        break;
    case ST_LEN:
        if (byte > FANPROTO_MAX_PAYLOAD)
        {
            p->errors++;
            p->state = ST_SOF;
            break;
        }
        p->frame.len = byte;
        p->crc = fanProto_Crc8(p->crc, &byte, 1);
        p->pos = 0;
        p->state = (byte == 0u) ? ST_CRC : ST_PAYLOAD;
        break;
    case ST_PAYLOAD:
        p->frame.payload[p->pos++] = byte;
        p->crc = fanProto_Crc8(p->crc, &byte, 1);
        if (p->pos >= p->frame.len)
        {
            p->state = ST_CRC;
        }
        break;
    default: /* ST_CRC */
        p->state = ST_SOF;
        if (byte == p->crc)
        {
            return true;
        }
        p->errors++;
        break;
    }
    return false;
}
