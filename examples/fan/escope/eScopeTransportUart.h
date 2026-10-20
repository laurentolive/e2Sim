/*******************************************************************************
 *
 *              #####   File : eScopeTransportUart.h
 *              #####
 *              #####   Generic hwUart transport — concrete types
 *              #####
 *      #############   Do not include directly — include eScopeTransport.h
 *   ################   with ESCOPE_TRANSPORT_UART defined.
 *  ######     ######
 *  ######      #####   This header defines the types for a generic hwUart-based
 *  *##########         transport (hwUart driver identified by an integer ID).
 *    ##############    The project supplies the implementation (one .c file):
 *         ###########  eScopeTransport_Init/DeInit/Read/Write and
 *    ##         ######  eScopeTransportUart_Poll, mapping u8Id to its own driver
 *  ######        #####  (HAL handle, FSP instance, hwUart …).
 *  ######       ######  See stm32/NUCLEO_C051C8/Core/Src/eScopeTransportUart.c.
 *
 ******************************************************************************/

#ifndef ESCOPE_TRANSPORT_UART_H_
#define ESCOPE_TRANSPORT_UART_H_

#include <stdint.h>

/*******************************************************************************
 * Generic UART transport types (hwUart ID-based driver)
 ******************************************************************************/

typedef struct {
    uint8_t u8Id;   /* hwUart driver instance ID passed to hwUart_Init() */
} eScopeTransportUart_Cfg_t;

typedef struct {
    uint8_t  u8Id;
    void   (*pfCB)(uint32_t event, void* pvCtxt);
    void    *pvCtxt;
} eScopeTransportUart_t;

/*******************************************************************************
 * Poll — called by eScopeTransport_Poll() before eScopeProtocol_Process().
 * Polling drivers deliver the pending read here; interrupt-driven drivers
 * implement it as an empty function.
 ******************************************************************************/

void eScopeTransportUart_Poll(eScopeTransportUart_t* pThis);

#endif /* ESCOPE_TRANSPORT_UART_H_ */
