/*
 * Fan example - HMI <-> motor board protocol (MIT)
 *
 * Frame: SOF(0xA5) CMD LEN PAYLOAD[LEN] CRC8 (poly 0x07, over CMD..PAYLOAD)
 *   CMD_SET    HMI -> motor: u16 rpm target (LE), u8 enable
 *   CMD_STATUS motor -> HMI: u16 rpm measured (LE), u8 faults (FANPROTO_FAULT_xxx)
 */
#ifndef FANPROTO_H
#define FANPROTO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FANPROTO_SOF         0xA5u
#define FANPROTO_CMD_SET     0x01u
#define FANPROTO_CMD_STATUS  0x81u
#define FANPROTO_MAX_PAYLOAD 8u
#define FANPROTO_MAX_FRAME   (FANPROTO_MAX_PAYLOAD + 4u)

#define FANPROTO_FAULT_OVERCURRENT 0x01u
#define FANPROTO_FAULT_BLOCKED     0x02u

typedef struct
{
    uint8_t cmd;
    uint8_t len;
    uint8_t payload[FANPROTO_MAX_PAYLOAD];
} fanProto_frame_t;

typedef struct
{
    uint8_t state;
    uint8_t pos;
    uint8_t crc;
    fanProto_frame_t frame;
    uint32_t errors; /* bad CRC or length */
} fanProto_parser_t;

uint8_t fanProto_Crc8(uint8_t crc, const uint8_t *data, size_t len);
size_t fanProto_Encode(uint8_t cmd, const uint8_t *payload, uint8_t len, uint8_t *out);
void fanProto_ParserInit(fanProto_parser_t *p);
bool fanProto_Parse(fanProto_parser_t *p, uint8_t byte); /* true: p->frame complete and valid */

#endif
