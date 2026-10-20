/* Example HAL on e2Sim - MCU core (MIT) */
#include "halMcu.h"
#include "halE2sim.h"

/* referenced so that the block enum is in the DWARF of the firmware (board.yaml idx) */
const halSim_block_t halSim_blocks[] = {HALSIM_BLOCK_LCD, HALSIM_BLOCK_NVM};

void halMcu_Init(void) { e2sim_yield(); }

halMcu_resetCause_t halMcu_GetResetCause(void)
{
    e2sim_yield();
    switch (e2sim_reset_cause())
    {
    case E2SIM_RESET_WDT:
        return HAL_RESET_WDT;
    case E2SIM_RESET_SOFT:
    case E2SIM_RESET_HOST:
        return HAL_RESET_SOFT;
    default:
        return HAL_RESET_POWER_ON;
    }
}

void halMcu_Reset(void) { e2sim_reset(E2SIM_RESET_SOFT); }

void halMcu_Idle(void) { e2sim_idle(); }

void halMcu_IrqDisable(void) { e2sim_irq_disable(); }

void halMcu_IrqEnable(void) { e2sim_irq_enable(); }
