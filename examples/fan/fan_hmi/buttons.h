/* Fan example - buttons: debounce, short and long press, from the 1 ms tick (MIT) */
#ifndef BUTTONS_H
#define BUTTONS_H

#include <stdbool.h>
#include <stdint.h>

typedef enum
{
    BTN_POWER = 0,
    BTN_PLUS,
    BTN_MINUS,
    BTN_NB
} buttons_id_t;

typedef enum
{
    BTN_EVT_SHORT = 0, /* released before BUTTONS_LONG_MS */
    BTN_EVT_LONG,      /* held BUTTONS_LONG_MS */
} buttons_evt_t;

#define BUTTONS_DEBOUNCE_MS 20u
#define BUTTONS_LONG_MS     2000u

void buttons_Init(void);
void buttons_Tick(void); /* interrupt context */
bool buttons_GetEvent(buttons_id_t *id, buttons_evt_t *evt);

#endif
