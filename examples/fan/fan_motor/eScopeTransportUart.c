/*
 * Fan example - eScope UART transport on the example HAL (MIT)
 *
 * Polling transport: eScopeTransport_Poll() reads the bytes buffered by the HAL and gives them one by one to
 * the protocol. Same code on the target and on e2Sim.
 */
#include <stddef.h>

#include "eScopeTransport.h"
#include "halUart.h"

static uint8_t *s_rxBuf; /* where the protocol wants the next byte */

void eScopeTransport_Init(eScopeTransport_t *pThis, const eScopeTransportCfg_t *pCfg,
                          void (*pfCB)(uint32_t event, void *pvCtxt), void *pvCtxt)
{
    pThis->u8Id = pCfg->u8Id;
    pThis->pfCB = pfCB;
    pThis->pvCtxt = pvCtxt;
    halUart_Init((halUart_t)pThis->u8Id, ESCOPE_PROTOCOL_BAUDRATE);
}

void eScopeTransport_DeInit(eScopeTransport_t *pThis)
{
    pThis->pfCB = NULL;
    s_rxBuf = NULL;
}

void eScopeTransport_Read(eScopeTransport_t *pThis, uint8_t *pBuf, uint8_t u8Len)
{
    (void)pThis;
    (void)u8Len; /* the protocol reads one byte at a time */
    s_rxBuf = pBuf;
}

void eScopeTransport_Write(eScopeTransport_t *pThis, const uint8_t *pData, uint16_t u16Len)
{
    halUart_Write((halUart_t)pThis->u8Id, pData, u16Len);
}

void eScopeTransportUart_Poll(eScopeTransportUart_t *pThis)
{
    uint8_t b;
    while ((s_rxBuf != NULL) && (pThis->pfCB != NULL) && (halUart_Read((halUart_t)pThis->u8Id, &b, 1) == 1u))
    {
        uint8_t *dst = s_rxBuf;
        s_rxBuf = NULL;
        *dst = b;
        pThis->pfCB(ESCOPE_TRANSPORT_EVT_RX, pThis->pvCtxt); /* calls eScopeTransport_Read() for the next byte */
    }
}
