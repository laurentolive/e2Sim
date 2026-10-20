/* Fan example - debug log on the debug UART (MIT) */
#ifndef LOG_H
#define LOG_H

void log_Printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

#endif
