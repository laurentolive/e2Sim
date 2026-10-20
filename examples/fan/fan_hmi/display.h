/* Fan example - display: 128x64 RGB565 (MIT) */
#ifndef DISPLAY_H
#define DISPLAY_H

void display_Init(void);    /* waits for the LCD controller reset */
void display_Refresh(void); /* draws the application state */

#endif
