/*
 * eScope configuration - firmware simulated on e2Sim (MIT)
 *
 * PC variant of the eScopeCfg.h of a firmware that embeds eScope (spec §9.3): the same firmware code, only this
 * file changes. Protocol V3 on a UART of the board, relayed to TCP by e2Sim (tcp: in board.yaml).
 *   - address size = pointer size of the build (4 in i686, 8 in x86_64): eScope device "Addresses";
 *   - addresses received = link addresses (symbols of the firmware), relocated by e2sim_addr_to_ptr();
 *   - an address outside the process memory is refused (ERR_ADDR) instead of crashing the simulation.
 */
#ifndef ESCOPE_CFG_H_
#define ESCOPE_CFG_H_

#include <stdbool.h>
#include <stdint.h>

#include "e2sim.h"

#define ESCOPE_PROTOCOL_V3
#define ESCOPE_TRANSPORT_UART
#define ESCOPE_PROTOCOL_BAUDRATE 115200U /* not limiting: the simulated UART has no baudrate */

#define ESCOPE_PROTOCOL_CHAN_MAX      (16U)
#if defined(__x86_64__)
#define ESCOPE_PROTOCOL_ADDRESS_SIZE  (8U) /* pointer size of the build */
#else
#define ESCOPE_PROTOCOL_ADDRESS_SIZE  (4U)
#endif
#define ESCOPE_PROTOCOL_DATASIZE_SIZE (2U)
#define ESCOPE_PROTOCOL_TX_SIZE       (250U)

/* link address (symbols of the firmware) -> address in the process (DLL / .so loaded anywhere) */
#define ESCOPE_ADDR_TO_PTR(addr) ((uint8_t *)e2sim_addr_to_ptr((uint64_t)(addr)))
#define ESCOPE_ADDR_IS_VALID(ptr, size) e2sim_mem_valid((ptr), (size), false)

#endif /* ESCOPE_CFG_H_ */
