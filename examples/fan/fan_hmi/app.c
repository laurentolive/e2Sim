/* Fan example - HMI application (MIT) */
#include "app.h"
#include "halGpio.h"

app_t app;
volatile uint32_t app_ms;

static const uint16_t s_rpm[APP_SPEED_MAX + 1u] = {0, 600, 900, 1200, 1500, 1800};

void app_Init(halMcu_resetCause_t cause, uint8_t speedLevel)
{
    app.wdtReset = (cause == HAL_RESET_WDT);
    app.speedLevel = speedLevel;
    app.running = false;
    app.temp_dC = 0;
}

void app_Update(void)
{
    bool stop = (app.fault & (APP_FAULT_TEMP | APP_FAULT_MOTOR)) != 0u;
    app.rpmTarget = (app.running && !stop && !app.shuttingDown) ? s_rpm[app.speedLevel] : 0u;
    halGpio_Write(HAL_GPIO_MOTOR_EN, app.rpmTarget != 0u);
    /* status LED: on, blinking at 2 Hz on fault */
    bool led = (app.fault == 0u) || (((app_ms / 250u) & 1u) == 0u);
    halGpio_Write(HAL_GPIO_LED, led && !app.shuttingDown);
}
