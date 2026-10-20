/* Fan example - HMI board: HAL resources (MIT) */
#ifndef HALCFG_H
#define HALCFG_H

typedef enum
{
    HAL_GPIO_BTN_POWER = 0,
    HAL_GPIO_BTN_PLUS,
    HAL_GPIO_BTN_MINUS,
    HAL_GPIO_LED,
    HAL_GPIO_SELF_HOLD, /* keeps the power latch closed */
    HAL_GPIO_MOTOR_EN,
    HAL_GPIO_NB
} halGpio_t;

typedef enum
{
    HAL_ADC_VBAT = 0, /* battery through a 15 V full scale divider */
    HAL_ADC_NB
} halAdc_t;

typedef enum
{
    HAL_TIMER_TICK = 0,
    HAL_TIMER_NB
} halTimer_t;

typedef enum
{
    HAL_UART_LINK = 0, /* motor board */
    HAL_UART_DEBUG,
    HAL_UART_NB
} halUart_t;

typedef enum
{
    HAL_SPI_SENSOR = 0, /* temperature sensor */
    HAL_SPI_NB
} halSpi_t;

#define HAL_LCD_WIDTH  128u
#define HAL_LCD_HEIGHT 64u
#define HAL_NVM_SIZE   2048u

#endif
