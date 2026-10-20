/* Fan example - debug log (MIT) */
#include <stdarg.h>
#include <stdio.h>

#include "app.h"
#include "halUart.h"
#include "log.h"

void log_Printf(const char *fmt, ...)
{
    char line[96];
    int n = snprintf(line, sizeof(line), "[%7lu] ", (unsigned long)app_ms);
    va_list ap;
    va_start(ap, fmt);
    int m = vsnprintf(&line[n], sizeof(line) - (size_t)n, fmt, ap);
    va_end(ap);
    if (m > 0)
    {
        n += m;
    }
    if (n > (int)sizeof(line) - 1)
    {
        n = (int)sizeof(line) - 1;
    }
    halUart_Write(HAL_UART_DEBUG, (const uint8_t *)line, (size_t)n);
}
