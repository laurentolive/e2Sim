/* Example HAL on e2Sim - LCD: RAM frame buffer copied to the shared block on update (MIT) */
#include <string.h>

#include "halLcd.h"
#include "halE2sim.h"

static uint16_t s_fb[HAL_LCD_WIDTH * HAL_LCD_HEIGHT];
static uint16_t *s_display;

void halLcd_Init(void)
{
    e2sim_yield();
    s_display = e2sim_block(HALSIM_BLOCK_LCD, sizeof(s_fb));
}

uint16_t *halLcd_GetFrameBuffer(void) { return s_fb; }

void halLcd_Update(void)
{
    e2sim_yield();
    if (s_display != NULL)
    {
        memcpy(s_display, s_fb, sizeof(s_fb));
    }
}
