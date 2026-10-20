/* Example HAL - MCU core: reset, idle, critical sections (MIT) */
#ifndef HALMCU_H
#define HALMCU_H

typedef enum
{
    HAL_RESET_POWER_ON = 0,
    HAL_RESET_SOFT,
    HAL_RESET_WDT,
} halMcu_resetCause_t;

void halMcu_Init(void);
halMcu_resetCause_t halMcu_GetResetCause(void);
void halMcu_Reset(void);
void halMcu_Idle(void); /* wait for interrupt */
void halMcu_IrqDisable(void);
void halMcu_IrqEnable(void);

#endif
