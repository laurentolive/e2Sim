/* Example HAL on e2Sim - SPI: synchronous transaction answered by a model (MIT) */
#include "halSpi.h"
#include "halE2sim.h"

void halSpi_Init(halSpi_t bus)
{
    (void)bus;
    e2sim_yield();
}

void halSpi_Transfer(halSpi_t bus, const uint8_t *tx, uint8_t *rx, size_t len)
{
    e2sim_yield();
    size_t n = e2sim_xfer(E2SIM_SPI, (uint16_t)bus, tx, len, rx, len);
    for (; n < len; n++)
    {
        rx[n] = 0xFFu; /* no answer: bus pulled up */
    }
}
