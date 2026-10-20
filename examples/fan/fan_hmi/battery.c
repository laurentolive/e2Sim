/* Fan example - battery measurement (MIT) */
#include "app.h"
#include "battery.h"
#include "halAdc.h"

void battery_Process(void)
{
    uint32_t mv = (uint32_t)halAdc_Read(HAL_ADC_VBAT) * BATTERY_FULL_SCALE_MV / HAL_ADC_MAX;
    app.vbat_mV = (uint16_t)mv;
    uint32_t pct = 0;
    if (mv > BATTERY_EMPTY_MV)
    {
        pct = (mv - BATTERY_EMPTY_MV) * 100u / (BATTERY_FULL_MV - BATTERY_EMPTY_MV);
    }
    app.batPercent = (uint8_t)((pct > 100u) ? 100u : pct);
    if (app.batPercent < BATTERY_LOW_PERCENT)
    {
        app.fault |= APP_FAULT_BAT;
    }
    else
    {
        app.fault &= ~APP_FAULT_BAT;
    }
}
