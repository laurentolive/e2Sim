/*
 * e2Sim - host <-> runner wire protocol (MIT)
 *
 * TCP, little-endian. Message: [u32 len][u8 type][payload (len - 1 bytes)].
 * Strings: [u16 len][bytes]. Must match e2sim/proto.py.
 */
#ifndef E2SIM_WIRE_H
#define E2SIM_WIRE_H

#include <stddef.h>
#include <stdint.h>

#define WIRE_VERSION 1u

/* runner -> host */
#define MSG_HELLO     0x01 /* u32 version, u8 ptr_size, u64 module_base, u32 pid, str dll */
#define MSG_DONE      0x02 /* u64 now, u8 powered, u8 halted, records..., REC_END */
#define MSG_XFER_REQ  0x03 /* u8 cls, u16 idx, u64 t, u16 n, bytes */

/* host -> runner */
#define MSG_CONFIG     0x81 /* u64 yield_cost_ns, u16 nblocks, {u16 idx, u8 fill, str path}... */
#define MSG_RUN        0x82 /* u64 until, records..., REC_END */
#define MSG_XFER_REPLY 0x83 /* u64 cost_ns, u16 n, bytes */
#define MSG_QUIT       0x84

#define REC_END 0x00

/* records in MSG_DONE */
#define REC_OUT    0x10 /* u8 cls, u16 idx, i32 v, u64 t */
#define REC_STREAM 0x11 /* u16 idx, u64 t, u16 n, bytes */
#define REC_EVENT  0x12 /* u16 idx, u64 t */
#define REC_BLOCK  0x13 /* u16 idx, u32 size, str mapping name */
#define REC_LOG    0x14 /* u64 t, u8 level, str text */
#define REC_RESET  0x15 /* u8 cause, u64 t, u64 module_base */
#define REC_MEM    0x16 /* u32 id, u8 status, u16 n, bytes */

/* records in MSG_RUN */
#define REC_IN        0x20 /* u8 cls, u16 idx, i32 v */
#define REC_STREAM_IN 0x21 /* u16 idx, u16 n, bytes */
#define REC_EVENT_IN  0x22 /* u16 idx */
#define REC_RESET_IN  0x23 /* u8 cause */
#define REC_POWER     0x24 /* u8 on */
#define REC_MEM_READ  0x25 /* u32 id, u64 addr, u32 size */
#define REC_MEM_WRITE 0x26 /* u32 id, u64 addr, u16 n, bytes */

#define MEM_OK      0
#define MEM_INVALID 1

typedef struct
{
    uint8_t *p;
    size_t n;
    size_t cap;
} wbuf_t;

typedef struct
{
    const uint8_t *p;
    size_t n;
    size_t pos;
    int error;
} rbuf_t;

void wbuf_reset(wbuf_t *b);
void wbuf_u8(wbuf_t *b, uint8_t v);
void wbuf_u16(wbuf_t *b, uint16_t v);
void wbuf_u32(wbuf_t *b, uint32_t v);
void wbuf_u64(wbuf_t *b, uint64_t v);
void wbuf_bytes(wbuf_t *b, const void *data, size_t n);
void wbuf_str(wbuf_t *b, const char *s);

uint8_t rbuf_u8(rbuf_t *r);
uint16_t rbuf_u16(rbuf_t *r);
uint32_t rbuf_u32(rbuf_t *r);
uint64_t rbuf_u64(rbuf_t *r);
const uint8_t *rbuf_bytes(rbuf_t *r, size_t n);
size_t rbuf_str(rbuf_t *r, char *out, size_t max);

int wire_connect(const char *host, uint16_t port, uint32_t timeout_ms); /* 0: ok */
int wire_send(uint8_t type, const wbuf_t *payload);                    /* 0: ok */
int wire_recv(uint8_t *type, wbuf_t *payload);                         /* 0: ok */
void wire_close(void);

#endif /* E2SIM_WIRE_H */
