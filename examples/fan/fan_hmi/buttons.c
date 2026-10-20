/* Fan example - buttons (MIT) */
#include "buttons.h"
#include "halGpio.h"
#include "halMcu.h"

#define QUEUE_SIZE 8u

typedef struct
{
    bool stable;     /* debounced state */
    bool armed;      /* false: pressed at boot, wait for a release */
    uint16_t count;  /* ms the raw state differs from the stable one */
    uint32_t heldMs;
    bool longSent;
} button_t;

static const halGpio_t s_pin[BTN_NB] = {HAL_GPIO_BTN_POWER, HAL_GPIO_BTN_PLUS, HAL_GPIO_BTN_MINUS};
static button_t s_btn[BTN_NB];
static uint8_t s_queue[QUEUE_SIZE];
static uint8_t s_head;
static uint8_t s_tail;

static void push(buttons_id_t id, buttons_evt_t evt)
{
    uint8_t next = (uint8_t)((s_head + 1u) % QUEUE_SIZE);
    if (next != s_tail)
    {
        s_queue[s_head] = (uint8_t)((id << 4) | evt);
        s_head = next;
    }
}

void buttons_Init(void)
{
    for (unsigned i = 0; i < BTN_NB; i++)
    {
        s_btn[i].stable = halGpio_Read(s_pin[i]);
        s_btn[i].armed = !s_btn[i].stable;
    }
}

void buttons_Tick(void)
{
    for (unsigned i = 0; i < BTN_NB; i++)
    {
        button_t *b = &s_btn[i];
        bool raw = halGpio_Read(s_pin[i]);
        if (raw != b->stable)
        {
            if (++b->count >= BUTTONS_DEBOUNCE_MS)
            {
                b->stable = raw;
                b->count = 0;
                if (raw)
                {
                    b->heldMs = 0;
                    b->longSent = false;
                }
                else
                {
                    if (b->armed && !b->longSent)
                    {
                        push((buttons_id_t)i, BTN_EVT_SHORT);
                    }
                    b->armed = true;
                }
            }
        }
        else
        {
            b->count = 0;
        }
        if (b->stable && b->armed && !b->longSent && (++b->heldMs >= BUTTONS_LONG_MS))
        {
            b->longSent = true;
            push((buttons_id_t)i, BTN_EVT_LONG);
        }
    }
}

bool buttons_GetEvent(buttons_id_t *id, buttons_evt_t *evt)
{
    bool found = false;
    halMcu_IrqDisable();
    if (s_tail != s_head)
    {
        *id = (buttons_id_t)(s_queue[s_tail] >> 4);
        *evt = (buttons_evt_t)(s_queue[s_tail] & 0x0Fu);
        s_tail = (uint8_t)((s_tail + 1u) % QUEUE_SIZE);
        found = true;
    }
    halMcu_IrqEnable();
    return found;
}
