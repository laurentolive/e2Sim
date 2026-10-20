/* Fan example - temperature sensor (MIT) */
#include "app.h"
#include "halSpi.h"
#include "sensor.h"

static void read_reg(uint8_t reg, uint8_t value[2])
{
    uint8_t tx[3] = {(uint8_t)(0x80u | reg), 0, 0};
    uint8_t rx[3];
    halSpi_Transfer(HAL_SPI_SENSOR, tx, rx, sizeof(tx));
    value[0] = rx[1];
    value[1] = rx[2];
}

void sensor_Init(void)
{
    uint8_t v[2];
    read_reg(TS_REG_ID, v);
    if (v[0] != TS_ID)
    {
        app.fault |= APP_FAULT_SENSOR;
    }
}

void sensor_Process(void)
{
    uint8_t v[2];
    if (app.fault & APP_FAULT_SENSOR)
    {
        return;
    }
    /* wait for the end of conversion. No timeout on purpose: a sensor stuck busy hangs the loop and
       the watchdog resets the MCU (fault found in simulation, test T06) */
    do
    {
        read_reg(TS_REG_STATUS, v);
    } while (v[0] & TS_STATUS_BUSY);
    read_reg(TS_REG_TEMP, v);
    app.temp_dC = (int16_t)(((uint16_t)v[0] << 8) | v[1]);
    if (app.temp_dC >= SENSOR_OVERTEMP_DC)
    {
        app.fault |= APP_FAULT_TEMP;
    }
    else if (app.temp_dC < SENSOR_RECOVER_DC)
    {
        app.fault &= ~APP_FAULT_TEMP;
    }
}
