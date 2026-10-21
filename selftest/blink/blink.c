/* e2Sim self-test firmware: timer ISR, GPIO, idle, stream, xfer, block, reset */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "e2sim.h"

volatile uint32_t ticks;
uint32_t loops;
int32_t initialized = 1234;     /* .data: restored at reset */
uint32_t boots;                 /* .bss: cleared at reset */

volatile uint32_t spin;

/* bug on purpose: busy loop without any HAL call (no yield point), found by the hang monitor */
static void __attribute__((noinline)) hang_here(void)
{
    for (;;)
    {
        spin++;
    }
}

static int table[4];

static void __attribute__((noinline)) overflow_here(int n)
{
    table[3 + n] = n; /* out of bounds for n >= 1 */
}

static void tick(void *ctx)
{
    (void)ctx;
    ticks++;
    e2sim_out(E2SIM_GPIO, 1, (int32_t)((ticks / 500u) & 1u));
}

int main(void)
{
    boots++;
    e2sim_timer_start(1000000u, true, tick, NULL);
    uint8_t *blk = e2sim_block(0, 16);
    blk[0]++;
    char msg[64];
    int n = snprintf(msg, sizeof(msg), "boot %u cause %d data %d\n", (unsigned)boots, (int)e2sim_reset_cause(), (int)initialized);
    e2sim_stream_write(0, (const uint8_t *)msg, (size_t)n);
    initialized = 99;
    for (;;)
    {
        loops++;
        if (e2sim_in(E2SIM_GPIO, 2) != 0)
        {
            uint8_t tx[2] = {0x55, 0xAA}, rx[2] = {0};
            e2sim_xfer(E2SIM_SPI, 0, tx, 2, rx, 2);
            e2sim_out(E2SIM_VALUE, 0, rx[0] | (rx[1] << 8));
        }
        if (e2sim_in(E2SIM_GPIO, 4) != 0)
        {
            hang_here();
        }
        if (e2sim_in(E2SIM_GPIO, 5) != 0)
        {
            overflow_here(e2sim_in(E2SIM_GPIO, 5)); /* bug on purpose: found by AddressSanitizer */
        }
        if (e2sim_in(E2SIM_GPIO, 3) != 0)
        {
            e2sim_reset(E2SIM_RESET_SOFT);
        }
        e2sim_idle();
    }
}
