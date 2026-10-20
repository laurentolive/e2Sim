/*******************************************************************************
 *
 *              #####   File : eScopeProtocolV3.c
 *              #####
 *              #####   Function : debug
 *              #####
 *      #############    Abstract — ProtocolV3
 *   ################   --------------------------------------------------------
 *  ######     ######
 *  ######      #####
 *  *##########
 *    ##############
 *         ###########
 *    ##         ######
 *  ######        #####
 *  ######       ######
 *
 ******************************************************************************/

#include "eScopeProtocol.h"
#ifdef ESCOPE_PROTOCOL_V3

#include <string.h>

#define ERR_FLAG   (0x80U)
#define READ_FLAG  (0x40U)
#define WRITE_FLAG (0x20U)

#define ADDR64_FLAG (0x10U) /* read / write command with a 64 bits address */

#if (ESCOPE_PROTOCOL_ADDRESS_SIZE == 8)
    #define ADDR_FLAG ADDR64_FLAG
#else
    #define ADDR_FLAG (0x00U)
#endif

#define CMD_NOP             (0x00U)
#define CMD_DEINIT          (0x01U)
#define CMD_CLEAR           (0x02U)
#define CMD_READ_PERIODIC   (0x03U | READ_FLAG)
#define CMD_READ_APERIODIC  (0x04U | READ_FLAG)
#define CMD_WRITE_APERIODIC (0x05U | WRITE_FLAG)
#define ERR_TXOVF           (0x06U | ERR_FLAG)
#define ERR_CFGOVF          (0x07U | ERR_FLAG)
#define ERR_ADDR            (0x08U | ERR_FLAG) /* payload: address, size */
#define ERR_ADDRSIZE        (0x0AU | ERR_FLAG) /* payload: ESCOPE_PROTOCOL_ADDRESS_SIZE */

#define CMD_SIZE     (2U + ESCOPE_PROTOCOL_ADDRESS_SIZE)
#define CMD_IDX      (0U)
#define CMD_SIZE_IDX (1U)
#define CMD_ADDR_IDX (2U)
#define CMD_DATA_IDX (CMD_SIZE)

#define HEADER_SIZE      (4U)
#define FOOTER_SIZE      (1U)
#define HEADER_SYNC_BYTE (0x55U)
#define FOOTER_SYNC_BYTE (0xAAU)

static void eScopeProtocol_transport_cb(uint32_t u32Event, void* pvCtxt);

/*----------------------------------------------------------------------------*/
void eScopeProtocol_Init(eScopeProtocol_t*          pThis,
                         const eScopeTransportCfg_t* pCfg,
                         eScopeProtocolCfg_t*        psCfg)
{
    memset(pThis, 0, sizeof(eScopeProtocol_t));
    pThis->pu8Cfg = psCfg->pu8Cfg;

    eScopeTransport_Init(&pThis->sTransport, pCfg,
                                eScopeProtocol_transport_cb, pThis);
    eScopeTransport_Read(&pThis->sTransport, &pThis->u8RxByte, 1U);
}

/*----------------------------------------------------------------------------*/
void eScopeProtocol_DeInit(eScopeProtocol_t* pThis)
{
    eScopeTransport_DeInit(&pThis->sTransport);
    memset(pThis, 0, sizeof(eScopeProtocol_t));
}

/*----------------------------------------------------------------------------*/
/* Config buffer layout :
 *   pu8Cfg[0 .. u8CfgSz[        parsed read commands (periodic and one shot)
 *   pu8Cfg[u8CfgSz .. u8RxIdx[  received bytes not parsed yet
 * One shot commands (read / write) are removed once served and the following
 * commands are shifted : the order of the read commands, so the layout of the
 * data frame expected by the PC, is kept.
 * Must be called inside a critical section (shared with the reception).     */
static void eScopeProtocol_Remove(eScopeProtocol_t* pThis, uint32_t u32Idx, uint32_t u32Len)
{
    uint32_t u32End = u32Idx + u32Len;

    memmove(&pThis->pu8Cfg[u32Idx], &pThis->pu8Cfg[u32End], pThis->u8RxIdx - u32End);
    pThis->u8RxIdx = (uint8_t)(pThis->u8RxIdx - u32Len);
    memset(&pThis->pu8Cfg[pThis->u8RxIdx], 0, u32Len);
}

/*----------------------------------------------------------------------------*/
/* drop the received bytes not parsed yet                                     */
static void eScopeProtocol_RxDrop(eScopeProtocol_t* pThis)
{
    CRITICAL_SECTION_ALLOC();

    CRITICAL_SECTION_ENTER();
    memset(&pThis->pu8Cfg[pThis->u8CfgSz], 0, pThis->u8RxIdx - pThis->u8CfgSz);
    pThis->u8RxIdx = pThis->u8CfgSz;
    CRITICAL_SECTION_EXIT();
}

/*----------------------------------------------------------------------------*/
/* error reported to the PC until the next CMD_CLEAR, with its payload        */
static void eScopeProtocol_Error(eScopeProtocol_t* pThis, uint8_t u8Err,
                                 const uint8_t* pu8Data, uint8_t u8Sz)
{
    if (u8Sz != 0U) memcpy(pThis->tu8Err, pu8Data, u8Sz);
    pThis->u8ErrSz = u8Sz;
    eScopeProtocol_RxDrop(pThis);
    pThis->pu8Cfg[0] = u8Err;
}

/*----------------------------------------------------------------------------*/
/* address of a command : little-endian, ESCOPE_PROTOCOL_ADDRESS_SIZE bytes   */
static uint8_t* eScopeProtocol_Address(const uint8_t* pu8Cmd)
{
    eScopeAddr_t addr = 0U;
    uint32_t     u32Idx;

    for (u32Idx = ESCOPE_PROTOCOL_ADDRESS_SIZE; u32Idx > 0U; u32Idx--)
    {
        addr = (eScopeAddr_t)((addr << 8U) | pu8Cmd[CMD_ADDR_IDX + u32Idx - 1U]);
    }
    return ESCOPE_ADDR_TO_PTR(addr);
}

/*----------------------------------------------------------------------------*/
/* access of a complete command checked : ERR_ADDR (address, size) if refused */
static bool eScopeProtocol_AddressCheck(eScopeProtocol_t* pThis, const uint8_t* pu8Cmd)
{
    uint8_t tu8Err[ESCOPE_PROTOCOL_ADDRESS_SIZE + 1U];

    if (ESCOPE_ADDR_IS_VALID(eScopeProtocol_Address(pu8Cmd), pu8Cmd[CMD_SIZE_IDX])) return true;

    memcpy(tu8Err, &pu8Cmd[CMD_ADDR_IDX], ESCOPE_PROTOCOL_ADDRESS_SIZE);
    tu8Err[ESCOPE_PROTOCOL_ADDRESS_SIZE] = pu8Cmd[CMD_SIZE_IDX];
    eScopeProtocol_Error(pThis, ERR_ADDR, tu8Err, (uint8_t)sizeof(tu8Err));
    return false;
}

/*----------------------------------------------------------------------------*/
/* parse all the received commands, called once the line is quiet            */
static void eScopeProtocol_Parse(eScopeProtocol_t* pThis)
{
    CRITICAL_SECTION_ALLOC();

    while (pThis->u8CfgSz < pThis->u8RxIdx)
    {
        uint8_t* pu8Rx    = &pThis->pu8Cfg[pThis->u8CfgSz];
        uint32_t u32Avail = (uint32_t)pThis->u8RxIdx - pThis->u8CfgSz;
        bool     bFull    = (pThis->u8RxIdx >= ESCOPE_PROTOCOL_EEPROM_SIZE);
        bool     bTimeout = (pThis->u8Time >= ESCOPE_PROTOCOL_RX_TIMEOUT);
        uint8_t  u8Cmd    = pu8Rx[CMD_IDX];

        if ((u8Cmd & (READ_FLAG | WRITE_FLAG)) != 0U) /* read / write : address size of the PC checked */
        {
            static const uint8_t cu8AddrSize = ESCOPE_PROTOCOL_ADDRESS_SIZE;

            if ((u8Cmd & ADDR64_FLAG) != ADDR_FLAG)
            {
                eScopeProtocol_Error(pThis, ERR_ADDRSIZE, &cu8AddrSize, 1U);
                return;
            }
            u8Cmd = (uint8_t)(u8Cmd & ~ADDR64_FLAG);
        }

        switch (u8Cmd)
        {
        case CMD_DEINIT:
            pThis->pu8Cfg = NULL;
            return;

        case CMD_CLEAR: /* new configuration, anything received with it is dropped */
            CRITICAL_SECTION_ENTER();
            memset(&pThis->pu8Cfg[0], 0, ESCOPE_PROTOCOL_EEPROM_SIZE);
            pThis->u8TxSz = 0U; pThis->u8CfgSz = 0U; pThis->u8RxIdx = 0U;
            pThis->u8ErrSz = 0U;
            CRITICAL_SECTION_EXIT();
            return;

        case CMD_READ_APERIODIC:
        case CMD_READ_PERIODIC:
            if (u32Avail < CMD_SIZE) /* command not complete */
            {
                if (bFull)         eScopeProtocol_Error(pThis, ERR_CFGOVF, NULL, 0U);
                else if (bTimeout) eScopeProtocol_RxDrop(pThis);
                return;
            }
            if ((pThis->u8TxSz + pu8Rx[CMD_SIZE_IDX]) >
                (sizeof(pThis->tu8Tx) - HEADER_SIZE - FOOTER_SIZE))
            {
                eScopeProtocol_Error(pThis, ERR_TXOVF, NULL, 0U);
                return;
            }
            if (!eScopeProtocol_AddressCheck(pThis, pu8Rx)) return;
            pu8Rx[CMD_IDX] = u8Cmd; /* stored without ADDR64_FLAG */
            pThis->u8TxSz  = (uint8_t)(pThis->u8TxSz  + pu8Rx[CMD_SIZE_IDX]);
            pThis->u8CfgSz = (uint8_t)(pThis->u8CfgSz + CMD_SIZE);
            break;

        case CMD_WRITE_APERIODIC:
        {
            uint32_t u32Len = CMD_SIZE;

            if (u32Avail >= CMD_SIZE) u32Len += pu8Rx[CMD_SIZE_IDX];
            if (u32Avail < u32Len) /* command not complete, dropped if it cannot fit */
            {
                if (bFull || bTimeout) eScopeProtocol_RxDrop(pThis);
                return;
            }
            if (!eScopeProtocol_AddressCheck(pThis, pu8Rx)) return;
            {
                uint8_t* pu8Address    = eScopeProtocol_Address(pu8Rx);
                uint8_t* pu8AddressEnd = pu8Address + pu8Rx[CMD_SIZE_IDX];
                uint8_t* pu8Src        = &pu8Rx[CMD_DATA_IDX];

                while (pu8Address < pu8AddressEnd) *pu8Address++ = *pu8Src++;
            }
            /* write is one shot : remove it */
            CRITICAL_SECTION_ENTER();
            eScopeProtocol_Remove(pThis, pThis->u8CfgSz, u32Len);
            CRITICAL_SECTION_EXIT();
            break;
        }

        default: /* NOP or unknown command : resynchronise on next reception */
            eScopeProtocol_RxDrop(pThis);
            return;
        }
    }
}

/*----------------------------------------------------------------------------*/
void eScopeProtocol_Process(eScopeProtocol_t* pThis)
{
    CRITICAL_SECTION_ALLOC();

    if (!pThis->pu8Cfg) return;

    if ((pThis->u8RxIdx > pThis->u8CfgSz) && (pThis->u8Time != 0U))
    {
        eScopeProtocol_Parse(pThis);
        if (!pThis->pu8Cfg) return;
    }

    if (pThis->pu8Cfg[0] & ERR_FLAG)
    {
        pThis->tu8Tx[0] = HEADER_SYNC_BYTE;
        pThis->tu8Tx[1] = pThis->u8FrameCnt++;
        pThis->tu8Tx[2] = pThis->u8ErrSz;
        pThis->tu8Tx[3] = pThis->pu8Cfg[0];
        memcpy(&pThis->tu8Tx[HEADER_SIZE], pThis->tu8Err, pThis->u8ErrSz);
        pThis->tu8Tx[HEADER_SIZE + pThis->u8ErrSz] = FOOTER_SYNC_BYTE;
        eScopeTransport_Write(&pThis->sTransport, pThis->tu8Tx,
                              (uint16_t)(pThis->u8ErrSz + HEADER_SIZE + FOOTER_SIZE));
    }
    else if (pThis->u8CfgSz)
    {
        uint8_t* pu8Tx = (uint8_t*)&pThis->tu8Tx[HEADER_SIZE];
        uint32_t u32Idx;

        pThis->tu8Tx[0] = HEADER_SYNC_BYTE;
        pThis->tu8Tx[1] = pThis->u8FrameCnt++;
        pThis->tu8Tx[2] = pThis->u8TxSz;
        pThis->tu8Tx[3] = CMD_READ_PERIODIC;

        for (u32Idx = 0U; u32Idx < pThis->u8CfgSz; u32Idx += CMD_SIZE)
        {
            uint8_t* pu8Cfg     = &pThis->pu8Cfg[u32Idx];
            uint8_t* pu8Address    = eScopeProtocol_Address(pu8Cfg);
            uint8_t* pu8AddressEnd = pu8Address + pu8Cfg[CMD_SIZE_IDX];

            while (pu8Address < pu8AddressEnd) *pu8Tx++ = *pu8Address++;
        }
        *pu8Tx = FOOTER_SYNC_BYTE;
        eScopeTransport_Write(&pThis->sTransport, pThis->tu8Tx,
                              pThis->u8TxSz + HEADER_SIZE + FOOTER_SIZE);

        /* one shot reads are served : remove them */
        CRITICAL_SECTION_ENTER();
        u32Idx = 0U;
        while (u32Idx < pThis->u8CfgSz)
        {
            if (pThis->pu8Cfg[u32Idx + CMD_IDX] == CMD_READ_APERIODIC)
            {
                pThis->u8TxSz  = (uint8_t)(pThis->u8TxSz - pThis->pu8Cfg[u32Idx + CMD_SIZE_IDX]);
                pThis->u8CfgSz = (uint8_t)(pThis->u8CfgSz - CMD_SIZE);
                eScopeProtocol_Remove(pThis, u32Idx, CMD_SIZE);
            }
            else
            {
                u32Idx += CMD_SIZE;
            }
        }
        CRITICAL_SECTION_EXIT();
    }

    CRITICAL_SECTION_ENTER();
    if (pThis->u8Time != 0xFFU) pThis->u8Time++;
    CRITICAL_SECTION_EXIT();
}

/*----------------------------------------------------------------------------*/
bool eScopeProtocol_isEnd(eScopeProtocol_t* pThis)
{
    return (pThis->pu8Cfg == NULL);
}

/*----------------------------------------------------------------------------*/
static void eScopeProtocol_transport_cb(uint32_t u32Event, void* pvCtxt)
{
    eScopeProtocol_t* pThis = (eScopeProtocol_t*)pvCtxt;
    CRITICAL_SECTION_ALLOC();

    if (u32Event != ESCOPE_TRANSPORT_EVT_RX) return;

    CRITICAL_SECTION_ENTER();
    if ((pThis->pu8Cfg) && (pThis->u8RxIdx < ESCOPE_PROTOCOL_EEPROM_SIZE))
    {
        pThis->pu8Cfg[pThis->u8RxIdx] = pThis->u8RxByte;
        pThis->u8RxIdx++;
    }
    pThis->u8Time = 0U;
    CRITICAL_SECTION_EXIT();
    eScopeTransport_Read(&pThis->sTransport, &pThis->u8RxByte, 1U);
}

#endif /* ESCOPE_PROTOCOL_V3 */
