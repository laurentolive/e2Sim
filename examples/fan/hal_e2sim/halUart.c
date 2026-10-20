/* Example HAL on e2Sim - UART: stream ports (MIT) */
#include "halUart.h"
#include "halE2sim.h"

void halUart_Init(halUart_t uart, uint32_t baudrate)
{
    (void)uart;
    (void)baudrate;
    e2sim_yield();
}

void halUart_Write(halUart_t uart, const uint8_t *data, size_t len)
{
    e2sim_yield();
    e2sim_stream_write((uint16_t)uart, data, len);
}

size_t halUart_Read(halUart_t uart, uint8_t *data, size_t max)
{
    e2sim_yield();
    return e2sim_stream_read((uint16_t)uart, data, max);
}
