"""Battery seen by the HMI ADC: raw ADC points, 15 V full scale (HAL data level, no physics)."""

import e2sim

FULL_SCALE_V = 15.0
ADC_MAX = 4095


class Battery(e2sim.Model):
    adc = e2sim.Value()
    voltage_V = e2sim.Param(12.0, "battery voltage")

    def setup(self):
        self.step()

    @e2sim.every(ms=10)
    def step(self):
        self.adc.set(max(0, min(ADC_MAX, round(self.voltage_V / FULL_SCALE_V * ADC_MAX))))
