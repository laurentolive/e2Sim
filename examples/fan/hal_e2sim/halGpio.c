/* Example HAL on e2Sim - GPIO (MIT) */
#include "halGpio.h"
#include "halE2sim.h"

void halGpio_Init(void) { e2sim_yield(); }

bool halGpio_Read(halGpio_t pin)
{
    e2sim_yield();
    return e2sim_in(E2SIM_GPIO, (uint16_t)pin) != 0;
}

void halGpio_Write(halGpio_t pin, bool level)
{
    e2sim_yield();
    e2sim_out(E2SIM_GPIO, (uint16_t)pin, level ? 1 : 0);
}
