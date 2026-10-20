/* Example HAL - colour LCD, RGB565 frame buffer in RAM (MIT) */
#ifndef HALLCD_H
#define HALLCD_H

#include <stdint.h>
#include "halCfg.h"

void halLcd_Init(void);              /* controller reset: needs HAL_LCD_RESET_US before use */
uint16_t *halLcd_GetFrameBuffer(void); /* HAL_LCD_WIDTH x HAL_LCD_HEIGHT pixels */
void halLcd_Update(void);            /* send the frame buffer to the display */

#define HAL_LCD_RESET_US 20000u

#endif
