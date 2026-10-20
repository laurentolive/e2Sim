/* Fan example - link with the motor board (MIT) */
#ifndef LINK_H
#define LINK_H

#include <stdint.h>

#define LINK_PERIOD_MS  100u /* set point sent every period */
#define LINK_TIMEOUT_MS 500u /* APP_FAULT_LINK without status */

void link_Init(void);
void link_Process(uint32_t now_ms);

#endif
