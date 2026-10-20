/* Example HAL on e2Sim - ADC: the port carries raw ADC points (MIT) */
#include "halAdc.h"
#include "halE2sim.h"

void halAdc_Init(void) { e2sim_yield(); }

uint16_t halAdc_Read(halAdc_t channel)
{
    e2sim_yield();
    int32_t v = e2sim_in(E2SIM_ADC, (uint16_t)channel);
    if (v < 0)
    {
        v = 0;
    }
    return (uint16_t)((v > (int32_t)HAL_ADC_MAX) ? HAL_ADC_MAX : (uint32_t)v);
}
