"""TS-01 temperature sensor (fictitious) answering the SPI transactions of the HMI."""

import e2sim

REG_STATUS, REG_TEMP, REG_ID = 0x00, 0x01, 0x0F
SENSOR_ID = 0x5A


class TempSensor(e2sim.Model):
    spi = e2sim.Xfer()
    temp_C = e2sim.Param(25.0, "measured temperature")
    stuck_busy = e2sim.Param(False, "fault: conversion never ends")
    no_answer = e2sim.Param(False, "fault: sensor missing (bus reads 0xFF)")

    def on_spi(self, tx: bytes) -> bytes:
        if self.no_answer or len(tx) < 3:
            return bytes([0xFF] * len(tx))
        reg = tx[0] & 0x7F
        if reg == REG_ID:
            value = SENSOR_ID << 8
        elif reg == REG_STATUS:
            value = 0x0100 if self.stuck_busy else 0
        elif reg == REG_TEMP:
            value = round(self.temp_C * 10) & 0xFFFF
        else:
            value = 0
        return bytes([0, value >> 8, value & 0xFF])
