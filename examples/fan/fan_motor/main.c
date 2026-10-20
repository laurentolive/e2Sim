/*
 * Fan example - motor board firmware (MIT)
 *
 * Speed regulation (PI on the tachometer), set point and status exchanged with the HMI board,
 * protections: hardware current comparator (interrupt), software overcurrent, blocked rotor.
 * Faults are latched until ENABLE falls.
 */
#include <stdbool.h>
#include <stdint.h>

#include "fanProto.h"
#include "halAdc.h"
#include "halCapture.h"
#include "halExti.h"
#include "halGpio.h"
#include "halMcu.h"
#include "halPwm.h"
#include "halTimer.h"
#include "halUart.h"
#include "halWdt.h"

#define CONTROL_PERIOD_MS   10u
#define PULSES_PER_REV      2u
#define CURRENT_FULL_MA     5000u
#define OVERCURRENT_MA      2000u
#define OVERCURRENT_MS      50u
#define BLOCKED_DUTY        300u
#define BLOCKED_RPM         100u
#define BLOCKED_MS          500u
#define WDT_TIMEOUT_MS      100u

typedef struct
{
    uint16_t rpmCmd;   /* set point received */
    bool enableCmd;
    uint16_t rpmMeas;
    uint16_t current_mA;
    uint16_t duty;     /* per mille */
    int32_t integ;     /* PI integral, per mille x 100 */
    uint8_t faults;    /* FANPROTO_FAULT_xxx, latched */
    uint32_t overMs;
    uint32_t blockedMs;
} motor_t;

motor_t motor;
volatile uint32_t motor_ms;

static fanProto_parser_t s_parser;

static void tick_isr(void) { motor_ms++; }

/* hardware comparator: cut the bridge at once, without waiting for the control loop */
static void overcurrent_isr(void)
{
    halPwm_SetDuty(HAL_PWM_MOTOR, 0);
    motor.duty = 0;
    motor.faults |= FANPROTO_FAULT_OVERCURRENT;
}

static void send_status(void)
{
    uint8_t payload[3] = {(uint8_t)motor.rpmMeas, (uint8_t)(motor.rpmMeas >> 8), motor.faults};
    uint8_t frame[FANPROTO_MAX_FRAME];
    size_t len = fanProto_Encode(FANPROTO_CMD_STATUS, payload, sizeof(payload), frame);
    halUart_Write(HAL_UART_LINK, frame, len);
}

static void link_process(void)
{
    uint8_t buf[32];
    size_t n;
    while ((n = halUart_Read(HAL_UART_LINK, buf, sizeof(buf))) != 0u)
    {
        for (size_t i = 0; i < n; i++)
        {
            if (fanProto_Parse(&s_parser, buf[i]) && (s_parser.frame.cmd == FANPROTO_CMD_SET) &&
                (s_parser.frame.len == 3u))
            {
                motor.rpmCmd = (uint16_t)(s_parser.frame.payload[0] | (s_parser.frame.payload[1] << 8));
                motor.enableCmd = s_parser.frame.payload[2] != 0u;
                send_status();
            }
        }
    }
}

static void control(void)
{
    uint32_t period = halCapture_GetPeriodUs(HAL_CAPTURE_TACHO);
    motor.rpmMeas = (period != 0u) ? (uint16_t)(60000000u / (period * PULSES_PER_REV)) : 0u;
    motor.current_mA = (uint16_t)((uint32_t)halAdc_Read(HAL_ADC_CURRENT) * CURRENT_FULL_MA / HAL_ADC_MAX);

    bool enablePin = halGpio_Read(HAL_GPIO_ENABLE);
    if (!enablePin)
    {
        motor.faults = 0; /* faults cleared by the HMI through ENABLE */
    }

    /* software protections */
    motor.overMs = (motor.current_mA > OVERCURRENT_MA) ? motor.overMs + CONTROL_PERIOD_MS : 0u;
    if (motor.overMs >= OVERCURRENT_MS)
    {
        motor.faults |= FANPROTO_FAULT_OVERCURRENT;
    }
    motor.blockedMs = ((motor.duty > BLOCKED_DUTY) && (motor.rpmMeas < BLOCKED_RPM)) ? motor.blockedMs + CONTROL_PERIOD_MS : 0u;
    if (motor.blockedMs >= BLOCKED_MS)
    {
        motor.faults |= FANPROTO_FAULT_BLOCKED;
    }

    if (!enablePin || !motor.enableCmd || (motor.rpmCmd == 0u) || (motor.faults != 0u))
    {
        motor.duty = 0;
        motor.integ = 0;
    }
    else
    {
        int32_t err = (int32_t)motor.rpmCmd - (int32_t)motor.rpmMeas;
        motor.integ += err * 2; /* Ki = 0.02 per mille / rpm / period */
        if (motor.integ < 0)
        {
            motor.integ = 0;
        }
        else if (motor.integ > (int32_t)HAL_PWM_MAX * 100)
        {
            motor.integ = (int32_t)HAL_PWM_MAX * 100;
        }
        int32_t duty = err / 5 + motor.integ / 100; /* Kp = 0.2 per mille / rpm */
        motor.duty = (uint16_t)((duty < 0) ? 0 : (duty > (int32_t)HAL_PWM_MAX) ? (int32_t)HAL_PWM_MAX : duty);
    }
    halPwm_SetDuty(HAL_PWM_MOTOR, motor.duty);
}

int main(void)
{
    halMcu_Init();
    halGpio_Init();
    halPwm_Init(HAL_PWM_MOTOR);
    halCapture_Init(HAL_CAPTURE_TACHO);
    halAdc_Init();
    halUart_Init(HAL_UART_LINK, 115200);
    fanProto_ParserInit(&s_parser);
    halExti_Init(HAL_EXTI_OVERCURRENT, overcurrent_isr);
    halTimer_Start(HAL_TIMER_TICK, 1000u, tick_isr);
    halWdt_Init(WDT_TIMEOUT_MS);

    uint32_t tControl = motor_ms;
    for (;;)
    {
        uint32_t now = motor_ms;
        link_process();
        if ((uint32_t)(now - tControl) >= CONTROL_PERIOD_MS)
        {
            tControl = now;
            control();
        }
        bool led = (motor.faults == 0u) ? (motor.duty != 0u) : (((now / 100u) & 1u) != 0u);
        halGpio_Write(HAL_GPIO_LED, led);
        halWdt_Refresh();
        halMcu_Idle();
    }
}
