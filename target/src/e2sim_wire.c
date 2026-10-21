/*
 * e2Sim - host <-> runner wire protocol (MIT)
 */
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
typedef int wire_len_t;
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
typedef int SOCKET;
#define INVALID_SOCKET (-1)
#define closesocket close
typedef size_t wire_len_t;
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "e2sim_wire.h"

static SOCKET s_sock = INVALID_SOCKET;

#ifdef _WIN32
/* shared memory transport (after CONFIG): [u32 len][u8 type][payload] in a view per direction, one event each */
static uint8_t *s_h2r;
static uint8_t *s_r2h;
static HANDLE s_ev_h2r;
static HANDLE s_ev_r2h;
static HANDLE s_host_process;

int wire_use_shm(const char *name, uint32_t host_pid)
{
    char n[128];
    snprintf(n, sizeof(n), "%s_map", name);
    HANDLE map = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, n);
    if (map == NULL)
    {
        return -1;
    }
    uint8_t *view = MapViewOfFile(map, FILE_MAP_ALL_ACCESS, 0, 0, 2u * WIRE_SHM_SIZE);
    snprintf(n, sizeof(n), "%s_h2r", name);
    s_ev_h2r = OpenEventA(SYNCHRONIZE | EVENT_MODIFY_STATE, FALSE, n);
    snprintf(n, sizeof(n), "%s_r2h", name);
    s_ev_r2h = OpenEventA(SYNCHRONIZE | EVENT_MODIFY_STATE, FALSE, n);
    s_host_process = OpenProcess(SYNCHRONIZE, FALSE, host_pid);
    if ((view == NULL) || (s_ev_h2r == NULL) || (s_ev_r2h == NULL) || (s_host_process == NULL))
    {
        return -1;
    }
    s_h2r = view;
    s_r2h = view + WIRE_SHM_SIZE;
    return 0;
}

static int shm_send(uint8_t type, const wbuf_t *payload)
{
    uint32_t len = (uint32_t)payload->n + 1u;
    if (len + 4u > WIRE_SHM_SIZE)
    {
        return -1;
    }
    memcpy(&s_r2h[0], &len, 4);
    s_r2h[4] = type;
    if (payload->n != 0u)
    {
        memcpy(&s_r2h[5], payload->p, payload->n);
    }
    return SetEvent(s_ev_r2h) ? 0 : -1;
}

static int shm_recv(uint8_t *type, wbuf_t *payload)
{
    HANDLE h[2] = {s_ev_h2r, s_host_process};
    if (WaitForMultipleObjects(2, h, FALSE, INFINITE) != WAIT_OBJECT_0)
    {
        return -1; /* host process gone */
    }
    uint32_t len;
    memcpy(&len, &s_h2r[0], 4);
    if ((len == 0u) || (len + 4u > WIRE_SHM_SIZE))
    {
        return -1;
    }
    *type = s_h2r[4];
    wbuf_reset(payload);
    wbuf_bytes(payload, &s_h2r[5], len - 1u);
    return 0;
}
#else
/* POSIX: TCP only (the host does not ask for the shared memory) */
static uint8_t *s_h2r;
static uint8_t *s_r2h;

int wire_use_shm(const char *name, uint32_t host_pid)
{
    (void)name;
    (void)host_pid;
    return -1;
}

static int shm_send(uint8_t type, const wbuf_t *payload)
{
    (void)type;
    (void)payload;
    return -1;
}

static int shm_recv(uint8_t *type, wbuf_t *payload)
{
    (void)type;
    (void)payload;
    return -1;
}

static uint32_t GetTickCount(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)((uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u);
}

static void Sleep(uint32_t ms) { usleep(ms * 1000u); }
#endif

/*----------------------------------------------------------------------------*/
static void wbuf_reserve(wbuf_t *b, size_t extra)
{
    if (b->n + extra <= b->cap)
    {
        return;
    }
    size_t cap = (b->cap != 0u) ? b->cap : 256u;
    while (cap < b->n + extra)
    {
        cap *= 2u;
    }
    uint8_t *p = realloc(b->p, cap);
    if (p == NULL)
    {
        abort();
    }
    b->p = p;
    b->cap = cap;
}

void wbuf_reset(wbuf_t *b) { b->n = 0; }

void wbuf_u8(wbuf_t *b, uint8_t v)
{
    wbuf_reserve(b, 1);
    b->p[b->n++] = v;
}

void wbuf_u16(wbuf_t *b, uint16_t v)
{
    wbuf_u8(b, (uint8_t)v);
    wbuf_u8(b, (uint8_t)(v >> 8));
}

void wbuf_u32(wbuf_t *b, uint32_t v)
{
    wbuf_u16(b, (uint16_t)v);
    wbuf_u16(b, (uint16_t)(v >> 16));
}

void wbuf_u64(wbuf_t *b, uint64_t v)
{
    wbuf_u32(b, (uint32_t)v);
    wbuf_u32(b, (uint32_t)(v >> 32));
}

void wbuf_bytes(wbuf_t *b, const void *data, size_t n)
{
    wbuf_reserve(b, n);
    if (n != 0u)
    {
        memcpy(&b->p[b->n], data, n);
    }
    b->n += n;
}

void wbuf_str(wbuf_t *b, const char *s)
{
    size_t n = strlen(s);
    if (n > 0xFFFFu)
    {
        n = 0xFFFFu;
    }
    wbuf_u16(b, (uint16_t)n);
    wbuf_bytes(b, s, n);
}

/*----------------------------------------------------------------------------*/
const uint8_t *rbuf_bytes(rbuf_t *r, size_t n)
{
    if (r->error || (r->pos + n > r->n))
    {
        r->error = 1;
        return NULL;
    }
    const uint8_t *p = &r->p[r->pos];
    r->pos += n;
    return p;
}

uint8_t rbuf_u8(rbuf_t *r)
{
    const uint8_t *p = rbuf_bytes(r, 1);
    return (p != NULL) ? p[0] : 0u;
}

uint16_t rbuf_u16(rbuf_t *r)
{
    uint16_t lo = rbuf_u8(r);
    return (uint16_t)(lo | ((uint16_t)rbuf_u8(r) << 8));
}

uint32_t rbuf_u32(rbuf_t *r)
{
    uint32_t lo = rbuf_u16(r);
    return lo | ((uint32_t)rbuf_u16(r) << 16);
}

uint64_t rbuf_u64(rbuf_t *r)
{
    uint64_t lo = rbuf_u32(r);
    return lo | ((uint64_t)rbuf_u32(r) << 32);
}

size_t rbuf_str(rbuf_t *r, char *out, size_t max)
{
    size_t n = rbuf_u16(r);
    const uint8_t *p = rbuf_bytes(r, n);
    size_t copy = 0;
    if ((p != NULL) && (max != 0u))
    {
        copy = (n < max - 1u) ? n : max - 1u;
        memcpy(out, p, copy);
    }
    if (max != 0u)
    {
        out[copy] = '\0';
    }
    return copy;
}

/*----------------------------------------------------------------------------*/
int wire_connect(const char *host, uint16_t port, uint32_t timeout_ms)
{
#ifdef _WIN32
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
    {
        return -1;
    }
#endif
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1)
    {
        return -1;
    }

    /* the host may start listening after the runner (launch from a debugger) */
    uint32_t start = GetTickCount();
    for (;;)
    {
        s_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (s_sock == INVALID_SOCKET)
        {
            return -1;
        }
        if (connect(s_sock, (struct sockaddr *)&addr, sizeof(addr)) == 0)
        {
            break;
        }
        closesocket(s_sock);
        s_sock = INVALID_SOCKET;
        if ((timeout_ms != 0u) && ((GetTickCount() - start) > timeout_ms))
        {
            return -1;
        }
        Sleep(100);
    }
    int nodelay = 1;
    setsockopt(s_sock, IPPROTO_TCP, TCP_NODELAY, (const char *)&nodelay, sizeof(nodelay));
    return 0;
}

static int send_all(const uint8_t *p, size_t n)
{
    while (n != 0u)
    {
        int chunk = (n > 0x10000u) ? 0x10000 : (int)n;
        int sent = (int)send(s_sock, (const char *)p, (wire_len_t)chunk, 0);
        if (sent <= 0)
        {
            return -1;
        }
        p += sent;
        n -= (size_t)sent;
    }
    return 0;
}

static int recv_all(uint8_t *p, size_t n)
{
    while (n != 0u)
    {
        int chunk = (n > 0x10000u) ? 0x10000 : (int)n;
        int got = (int)recv(s_sock, (char *)p, (wire_len_t)chunk, 0);
        if (got <= 0)
        {
            return -1;
        }
        p += got;
        n -= (size_t)got;
    }
    return 0;
}

int wire_send(uint8_t type, const wbuf_t *payload)
{
    if (s_r2h != NULL)
    {
        return shm_send(type, payload);
    }
    uint32_t len = (uint32_t)payload->n + 1u;
    uint8_t hdr[5] = {(uint8_t)len, (uint8_t)(len >> 8), (uint8_t)(len >> 16), (uint8_t)(len >> 24), type};
    if (send_all(hdr, sizeof(hdr)) != 0)
    {
        return -1;
    }
    return send_all(payload->p, payload->n);
}

int wire_recv(uint8_t *type, wbuf_t *payload)
{
    if (s_h2r != NULL)
    {
        return shm_recv(type, payload);
    }
    uint8_t hdr[5];
    if (recv_all(hdr, sizeof(hdr)) != 0)
    {
        return -1;
    }
    uint32_t len = (uint32_t)hdr[0] | ((uint32_t)hdr[1] << 8) | ((uint32_t)hdr[2] << 16) | ((uint32_t)hdr[3] << 24);
    if (len == 0u)
    {
        return -1;
    }
    *type = hdr[4];
    wbuf_reset(payload);
    wbuf_reserve(payload, len - 1u);
    if (recv_all(payload->p, len - 1u) != 0)
    {
        return -1;
    }
    payload->n = len - 1u;
    return 0;
}

void wire_close(void)
{
    if (s_sock != INVALID_SOCKET)
    {
        closesocket(s_sock);
        s_sock = INVALID_SOCKET;
    }
#ifdef _WIN32
    WSACleanup();
#endif
}
