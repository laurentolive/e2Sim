/*******************************************************************************
 *
 *              #####   File : eScopeProtocol.h
 *              #####
 *              #####   Protocol selector — single compile-time define
 *              #####
 *      #############   Abstract
 *   ################   --------------------------------------------------------
 *  ######     ######
 *  ######      #####   Define exactly ONE symbol in your build system:
 *  *##########
 *    ##############     ESCOPE_PROTOCOL_V1     minimal — fixed chan/data size
 *         ###########   ESCOPE_PROTOCOL_V2     address + data-size per channel
 *    ##         ######  ESCOPE_PROTOCOL_V3     full command set (read/write/clear)
 *  ######        #####  ESCOPE_PROTOCOL_V3ID   V3 variant for ID-based UART driver
 *  ######       ######
 *                        Then include only this file.  The selected header
 *                        exposes eScopeProtocol_t, eScopeProtocolCfg_t, and
 *                        the common API directly — no indirection layer.
 *
 *  Usage:
 *      eScopeProtocol_t        sProto;
 *      eScopeProtocolCfg_t     sProtoCfg = { ... };
 *      eScopeTransportCfg_t    sTransCfg = { ... };
 *
 *      eScopeProtocol_Init(&sProto, &sTransCfg, &sProtoCfg);
 *
 *      // in main loop / timer:
 *      eScopeProtocol_Process(&sProto);
 *      if (eScopeProtocol_isEnd(&sProto)) { ... }
 *
 ******************************************************************************/

#ifndef ESCOPE_PROTOCOL_H_
#define ESCOPE_PROTOCOL_H_

/*******************************************************************************
 * Project configuration — must be provided by each project
 ******************************************************************************/

#include "eScopeDep.h"
#include "eScopeCfg.h"    /* defines ESCOPE_PROTOCOL_xxx and ESCOPE_TRANSPORT_xxx */

/*******************************************************************************
 * Protocol version selection
 ******************************************************************************/

#if defined(ESCOPE_PROTOCOL_V1)
    #include "eScopeProtocolV1.h"

#elif defined(ESCOPE_PROTOCOL_V2)
    #include "eScopeProtocolV2.h"

#elif defined(ESCOPE_PROTOCOL_V3)
    #include "eScopeProtocolV3.h"

#elif defined(ESCOPE_PROTOCOL_V3ID)
    #include "eScopeProtocolV3Id.h"

#else
    #error "Define one of: ESCOPE_PROTOCOL_V1 | ESCOPE_PROTOCOL_V2 | ESCOPE_PROTOCOL_V3 | ESCOPE_PROTOCOL_V3ID"
#endif


void eScopeProtocol_Init   (eScopeProtocol_t*          pThis,
                            const eScopeTransportCfg_t* pCfg,
                            eScopeProtocolCfg_t*        psCfg);
void eScopeProtocol_DeInit (eScopeProtocol_t* pThis);
void eScopeProtocol_Process(eScopeProtocol_t* pThis);
bool eScopeProtocol_isEnd  (eScopeProtocol_t* pThis);
//bool eScopeProtocol_Poll   (eScopeProtocol_t* pThis);
#define eScopeProtocol_Poll(pThis) eScopeTransport_Poll(&((pThis)->sTransport))
#endif /* ESCOPE_PROTOCOL_H_ */
