/*
 * Fan example - HMI board firmware (MIT)
 *
 * Battery fan: power latch (SELF_HOLD), 3 keys, 128x64 display, temperature sensor on SPI,
 * battery on ADC, motor board on UART, settings in NVM, watchdog.
 *   POWER short: fan on / off      POWER long (2 s): save and power off
 *   PLUS / MINUS: speed 1..5
 * The same sources build for the target (HAL of the MCU) and for e2Sim (hal_e2sim).
 */
#include "app.h"
#include "battery.h"
#include "buttons.h"
#include "display.h"
#include "halGpio.h"
#include "halMcu.h"
#include "halNvm.h"
#include "halTimer.h"
#include "halUart.h"
#include "halWdt.h"
#include "link.h"
#include "log.h"
#include "sensor.h"
#include "settings.h"

#define WDT_TIMEOUT_MS     200u
#define BATTERY_PERIOD_MS  100u
#define SENSOR_PERIOD_MS   500u
#define DISPLAY_PERIOD_MS  100u
#define SHUTDOWN_DELAY_MS  200u

static const char *const s_cause[] = {"power on", "soft", "watchdog"};

static void tick_isr(void)
{
    app_ms++;
    buttons_Tick();
}

static void on_button(buttons_id_t id, buttons_evt_t evt)
{
    app.wdtReset = false;
    if (id == BTN_POWER)
    {
        if (evt == BTN_EVT_LONG)
        {
            app.shuttingDown = true;
            log_Printf("power off\n");
        }
        else
        {
            app.running = !app.running;
            log_Printf("fan %s\n", app.running ? "on" : "off");
        }
    }
    else if (app.running && (evt == BTN_EVT_SHORT))
    {
        if ((id == BTN_PLUS) && (app.speedLevel < APP_SPEED_MAX))
        {
            app.speedLevel++;
        }
        else if ((id == BTN_MINUS) && (app.speedLevel > 1u))
        {
            app.speedLevel--;
        }
        settings.speedLevel = app.speedLevel;
        log_Printf("speed %u\n", (unsigned)app.speedLevel);
    }
}

int main(void)
{
    halMcu_Init();
    halGpio_Init();
    halGpio_Write(HAL_GPIO_SELF_HOLD, true); /* keep the power on once the key is released */
    halMcu_resetCause_t cause = halMcu_GetResetCause();

    halUart_Init(HAL_UART_TERMINAL, 115200);
    halNvm_Init();
    bool valid = settings_Load();
    log_Printf("fan_hmi boot (%s), settings %s\n", s_cause[cause], valid ? "ok" : "reset to defaults");
    if (cause == HAL_RESET_WDT)
    {
        settings.wdtCount++;
    }
    if (!valid || (cause == HAL_RESET_WDT))
    {
        settings_Save();
    }
    app_Init(cause, settings.speedLevel);

    buttons_Init();
    halTimer_Start(HAL_TIMER_TICK, 1000u, tick_isr);
    display_Init();
    sensor_Init();
    link_Init();
    halWdt_Init(WDT_TIMEOUT_MS);

    uint32_t tBattery = app_ms, tSensor = app_ms, tDisplay = app_ms, tRun = app_ms, tShutdown = 0;
    battery_Process();
    for (;;)
    {
        uint32_t now = app_ms;
        buttons_id_t id;
        buttons_evt_t evt;
        while (buttons_GetEvent(&id, &evt))
        {
            on_button(id, evt);
        }

        link_Process(now);
        if ((uint32_t)(now - tBattery) >= BATTERY_PERIOD_MS)
        {
            tBattery = now;
            battery_Process();
        }
        if ((uint32_t)(now - tSensor) >= SENSOR_PERIOD_MS)
        {
            tSensor = now;
            sensor_Process();
        }

        /* running time counter, saved every minute */
        if ((uint32_t)(now - tRun) >= 1000u)
        {
            tRun += 1000u;
            if (app.rpmTarget != 0u)
            {
                if (++app.runSeconds >= 60u)
                {
                    app.runSeconds = 0;
                    settings.runMinutes++;
                    settings_Save();
                }
            }
        }

        app_Update();
        if ((uint32_t)(now - tDisplay) >= DISPLAY_PERIOD_MS)
        {
            tDisplay = now;
            display_Refresh();
        }

        if (app.shuttingDown)
        {
            if (tShutdown == 0u)
            {
                tShutdown = now;
                settings_Save();
            }
            else if ((uint32_t)(now - tShutdown) >= SHUTDOWN_DELAY_MS)
            {
                halGpio_Write(HAL_GPIO_SELF_HOLD, false); /* power cut when the key is released */
            }
        }

        halWdt_Refresh();
        halMcu_Idle();
    }
}
