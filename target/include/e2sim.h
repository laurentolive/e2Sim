/*
 * e2Sim - target API (MIT)
 *
 * Called by the HAL adapter of a simulated firmware. The firmware is built as a DLL
 * and loaded by e2sim_runner.exe, which implements these functions.
 */
#ifndef E2SIM_H
#define E2SIM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifdef E2SIM_RUNNER
#define E2SIM_API __declspec(dllexport)
#else
#define E2SIM_API __declspec(dllimport)
#endif

#define E2SIM_VERSION 1u

/* port classes: a port is addressed by (class, index of the HAL) */
typedef enum
{
    E2SIM_GPIO = 1,
    E2SIM_ADC,
    E2SIM_PWM,
    E2SIM_CAPTURE,
    E2SIM_VALUE,
    E2SIM_UART,
    E2SIM_SPI,
    E2SIM_I2C,
    E2SIM_BLOCK,
    E2SIM_EVENT,
} e2sim_class_t;

typedef enum
{
    E2SIM_RESET_POWER_ON = 0,
    E2SIM_RESET_SOFT,
    E2SIM_RESET_WDT,
    E2SIM_RESET_HOST,
} e2sim_reset_cause_t;

typedef enum
{
    E2SIM_LOG_DEBUG = 0,
    E2SIM_LOG_INFO,
    E2SIM_LOG_WARNING,
    E2SIM_LOG_ERROR,
} e2sim_log_level_t;

typedef void (*e2sim_isr_t)(void *ctx);
typedef int e2sim_timer_t; /* < 0: invalid */

/* time and execution */
E2SIM_API uint64_t e2sim_time_ns(void);
E2SIM_API void e2sim_yield(void);                       /* every HAL call; no effect in ISR context */
E2SIM_API void e2sim_idle(void);                        /* WFI: jump to the next event; no effect in ISR context */
E2SIM_API void e2sim_reset(e2sim_reset_cause_t cause);  /* fiber: does not return; ISR: reset when the ISR ends */
E2SIM_API e2sim_reset_cause_t e2sim_reset_cause(void);  /* cause of the last reset */

/* ports */
E2SIM_API int32_t e2sim_in(e2sim_class_t c, uint16_t idx);
E2SIM_API void e2sim_out(e2sim_class_t c, uint16_t idx, int32_t v);
E2SIM_API void e2sim_event_out(uint16_t idx);
E2SIM_API size_t e2sim_stream_read(uint16_t idx, uint8_t *buf, size_t max);
E2SIM_API void e2sim_stream_write(uint16_t idx, const uint8_t *buf, size_t len);
E2SIM_API size_t e2sim_xfer(e2sim_class_t c, uint16_t idx, const uint8_t *tx, size_t tx_len,
                            uint8_t *rx, size_t rx_max); /* synchronous, virtual time stopped */
E2SIM_API void *e2sim_block(uint16_t idx, size_t size);

/* interrupts */
E2SIM_API e2sim_timer_t e2sim_timer_start(uint64_t period_ns, bool periodic, e2sim_isr_t isr, void *ctx);
E2SIM_API void e2sim_timer_stop(e2sim_timer_t t);
E2SIM_API void e2sim_on_input(e2sim_class_t c, uint16_t idx, e2sim_isr_t isr, void *ctx); /* EXTI, RX */
E2SIM_API void e2sim_irq_disable(void);
E2SIM_API void e2sim_irq_enable(void);

/* memory of the process: committed and readable (writable) on the whole range. For code that accesses
   addresses received from outside (eScope embedded in the firmware: ESCOPE_ADDR_IS_VALID) */
E2SIM_API bool e2sim_mem_valid(const void *addr, size_t size, bool write);

/* diagnostic */
E2SIM_API void e2sim_log(e2sim_log_level_t level, const char *fmt, ...) __attribute__((format(gnu_printf, 2, 3)));

/* busy wait without HAL call: yield point, empty on target */
#define E2SIM_YIELD() e2sim_yield()

#ifdef __cplusplus
}
#endif

#endif /* E2SIM_H */
