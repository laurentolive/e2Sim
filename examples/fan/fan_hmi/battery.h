/* Fan example - battery measurement (MIT) */
#ifndef BATTERY_H
#define BATTERY_H

#define BATTERY_FULL_SCALE_MV 15000u
#define BATTERY_EMPTY_MV      9000u
#define BATTERY_FULL_MV       12600u
#define BATTERY_LOW_PERCENT   10u

void battery_Process(void); /* updates app.vbat_mV, app.batPercent, APP_FAULT_BAT */

#endif
