/*
 * Example HAL on e2Sim - adapter configuration (MIT)
 *
 * Model of an e2Sim adapter: every function of the HAL is implemented on e2sim.h, and starts with
 * e2sim_yield() (yield point, spec §4.1). No product logic here: the environment is in the Python models.
 */
#ifndef HALE2SIM_H
#define HALE2SIM_H

#include "e2sim.h"

/* memory blocks shared with the host (board.yaml: class BLOCK, idx HALSIM_BLOCK_xxx) */
typedef enum
{
    HALSIM_BLOCK_LCD = 0,
    HALSIM_BLOCK_NVM = 1,
} halSim_block_t;

#endif
