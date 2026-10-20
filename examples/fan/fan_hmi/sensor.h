/*
 * Fan example - temperature sensor TS-01 (fictitious) on SPI (MIT)
 * Transaction of 3 bytes: tx[0] = 0x80 | register, rx[1..2] = value (big endian).
 */
#ifndef SENSOR_H
#define SENSOR_H

#define TS_REG_STATUS  0x00u /* rx[1] bit 0: conversion running */
#define TS_REG_TEMP    0x01u /* int16, 0.1 degC */
#define TS_REG_ID      0x0Fu /* rx[1] = TS_ID */
#define TS_ID          0x5Au
#define TS_STATUS_BUSY 0x01u

#define SENSOR_OVERTEMP_DC 600 /* 60.0 degC: motor stopped */
#define SENSOR_RECOVER_DC  550

void sensor_Init(void);    /* APP_FAULT_SENSOR if not identified */
void sensor_Process(void); /* updates app.temp_dC, APP_FAULT_TEMP */

#endif
