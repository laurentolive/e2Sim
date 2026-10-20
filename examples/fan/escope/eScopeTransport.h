/*******************************************************************************
 *
 *              #####   File : eScopeTransport.h
 *              #####
 *              #####   Transport selector — single compile-time define
 *              #####
 *      #############   Abstract
 *   ################   --------------------------------------------------------
 *  ######     ######
 *  ######      #####   Define exactly ONE symbol in your build system:
 *  *##########
 *    ##############     
 *         ###########   
 *    ##         ######  
 *  ######        #####  ESCOPE_TRANSPORT_UART          Generic hwUart driver
 *  ######       ######  ESCOPE_TRANSPORT_TCP           TCP (stub)
 *                       ESCOPE_TRANSPORT_RTT           SEGGER RTT
 *
 *                        This header resolves eScopeTransport_t and
 *                        eScopeTransportCfg_t to the selected concrete types,
 *                        and declares the common API implemented by the
 *                        matching translation unit.
 *
 ******************************************************************************/

#ifndef ESCOPE_TRANSPORT_H_
#define ESCOPE_TRANSPORT_H_

#include <stdint.h>
#include <stdbool.h>
#include "eScopeCfg.h"    /* project-supplied — defines ESCOPE_TRANSPORT_xxx   */
#include "eScopeDep.h"    /* Dependency-supplied — defines mcu/compiler   */

/*******************************************************************************
 * Concrete transport + platform selection
 ******************************************************************************/

#if defined(ESCOPE_TRANSPORT_UART)
    #include "eScopeTransportUart.h"
    typedef eScopeTransportUart_t            eScopeTransport_t;
    typedef eScopeTransportUart_Cfg_t        eScopeTransportCfg_t;

#elif defined(ESCOPE_TRANSPORT_TCP)
    #include "eScopeTransportTcp.h"
    typedef eScopeTransportTcp_t             eScopeTransport_t;
    typedef eScopeTransportTcp_Cfg_t         eScopeTransportCfg_t;

#elif defined(ESCOPE_TRANSPORT_RTT)
    #include "eScopeTransportRtt.h"
    typedef eScopeTransportRtt_t             eScopeTransport_t;
    typedef eScopeTransportRtt_Cfg_t         eScopeTransportCfg_t;

#else
    #error "Define one of: ESCOPE_TRANSPORT_UART | ESCOPE_TRANSPORT_TCP | ESCOPE_TRANSPORT_RTT"
#endif

/*******************************************************************************
 * Baudrate check — required for all UART transports, defined in eScopeCfg.h
 ******************************************************************************/

#if defined(ESCOPE_TRANSPORT_UART)
    #ifndef ESCOPE_PROTOCOL_BAUDRATE
        #error "ESCOPE_PROTOCOL_BAUDRATE must be defined in eScopeCfg.h (e.g. 115200U)"
    #endif
#endif

/*******************************************************************************
 * Common event codes (identical across all transport implementations)
 ******************************************************************************/

#define ESCOPE_TRANSPORT_EVT_RX (0U)   /* one or more bytes received  */
#define ESCOPE_TRANSPORT_EVT_TX (1U)   /* transmission complete        */

/*******************************************************************************
 * Common API — implemented by the selected translation unit
 * pfCB/pvCtxt are stored in the handle, NOT in the cfg.
 ******************************************************************************/

void eScopeTransport_Init  (eScopeTransport_t*        pThis,
                            const eScopeTransportCfg_t* pCfg,
                            void (*pfCB)(uint32_t event, void* pvCtxt),
                            void*                     pvCtxt);
void eScopeTransport_DeInit(eScopeTransport_t* pThis);
void eScopeTransport_Read  (eScopeTransport_t* pThis, uint8_t* pBuf, uint8_t u8Len);
void eScopeTransport_Write (eScopeTransport_t* pThis, const uint8_t* pData, uint16_t u16Len);

/*******************************************************************************
 * eScopeTransport_Poll — call once per main-loop iteration before Process().
 *
 * Polling transports (RTT, Arduino) drain their RX source here and fire the
 * pending callback.  Interrupt-driven transports expand to a no-op.
 *
 *  while (1) {
 *      eScopeTransport_Poll(&sTransport);
 *      eScopeProtocol_Process(&sProto);
 *  }
 ******************************************************************************/

#if defined(ESCOPE_TRANSPORT_RTT)
    #define eScopeTransport_Poll(pThis)  eScopeTransportRtt_Poll(pThis)
#elif defined(ESCOPE_TRANSPORT_UART)
    #define eScopeTransport_Poll(pThis)  eScopeTransportUart_Poll(pThis)
#else
    #define eScopeTransport_Poll(pThis)  ((void)(pThis))
#endif

#endif /* ESCOPE_TRANSPORT_H_ */
