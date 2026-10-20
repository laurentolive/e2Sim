/* Fan example - HMI application state (MIT) */
#ifndef APP_H
#define APP_H

#include <stdbool.h>
#include <stdint.h>

#include "halMcu.h"

#define APP_SPEED_MAX 5u

#define APP_FAULT_LINK   0x01u /* no status from the motor board */
#define APP_FAULT_TEMP   0x02u /* over temperature: motor stopped */
#define APP_FAULT_BAT    0x04u /* battery low */
#define APP_FAULT_SENSOR 0x08u /* temperature sensor not identified */
#define APP_FAULT_MOTOR  0x10u /* fault reported by the motor board */

typedef struct
{
    bool running;
    bool shuttingDown;
    bool wdtReset;       /* last reset by the watchdog, shown until a key is pressed */
    uint8_t speedLevel;  /* 1..APP_SPEED_MAX */
    uint16_t rpmTarget;
    uint16_t rpmMeasured;
    uint8_t motorFaults;
    uint16_t vbat_mV;
    uint8_t batPercent;
    int16_t temp_dC;     /* 0.1 degC */
    uint32_t fault;      /* APP_FAULT_xxx */
    uint32_t runSeconds; /* in the current minute */
} app_t;

extern app_t app;
extern volatile uint32_t app_ms; /* incremented by the 1 ms tick */

void app_Init(halMcu_resetCause_t cause, uint8_t speedLevel);
void app_Update(void); /* outputs from the state */

#endif
