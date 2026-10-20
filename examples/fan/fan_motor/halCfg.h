/* Fan example - motor board: HAL resources (MIT) */
#ifndef HALCFG_H
#define HALCFG_H

typedef enum
{
    HAL_GPIO_ENABLE = 0, /* from the HMI board */
    HAL_GPIO_LED,
    HAL_GPIO_NB
} halGpio_t;

typedef enum
{
    HAL_ADC_CURRENT = 0, /* motor current, 5 A full scale */
    HAL_ADC_NB
} halAdc_t;

typedef enum
{
    HAL_PWM_MOTOR = 0,
    HAL_PWM_NB
} halPwm_t;

typedef enum
{
    HAL_CAPTURE_TACHO = 0, /* 2 pulses per revolution */
    HAL_CAPTURE_NB
} halCapture_t;

typedef enum
{
    HAL_EXTI_OVERCURRENT = 0, /* hardware current comparator */
    HAL_EXTI_NB
} halExti_t;

typedef enum
{
    HAL_TIMER_TICK = 0,
    HAL_TIMER_NB
} halTimer_t;

typedef enum
{
    HAL_UART_LINK = 0, /* HMI board */
    HAL_UART_SCOPE,    /* eScope */
    HAL_UART_NB
} halUart_t;

#endif
