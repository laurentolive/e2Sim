"""Fan motor seen by the motor board: PWM duty in, tachometer period, current ADC, comparator event out."""

import e2sim

ADC_MAX, CURRENT_FULL_MA, PULSES_PER_REV = 4095, 5000, 2


class Motor(e2sim.Model):
    pwm = e2sim.Value()       # duty per mille, firmware output
    tacho = e2sim.Value()     # capture: period in us between two pulses (0: stopped)
    current = e2sim.Value()   # ADC points
    comparator = e2sim.Event()

    max_rpm = e2sim.Param(2400.0, "speed at full duty, nominal load")
    time_constant_s = e2sim.Param(0.2)
    load = e2sim.Param(1.0, "load factor (1 nominal, > 1 heavier)")
    blocked = e2sim.Param(False, "fault: rotor blocked")
    comparator_mA = e2sim.Param(3000, "hardware overcurrent threshold")
    stall_mA = e2sim.Param(4000, "current at full duty, rotor blocked")

    def setup(self):
        self.rpm = 0.0
        self.current_mA = 0.0
        self._over = False

    @e2sim.every(ms=1)
    def step(self):
        duty = self.pwm.get() / 1000.0
        target = 0.0 if self.blocked else duty * self.max_rpm / self.load
        self.rpm += (target - self.rpm) * min(1.0, 0.001 / self.time_constant_s)
        # current: stall current when blocked, else rises with duty and load
        self.current_mA = duty * (self.stall_mA if self.blocked else 150.0 + 1200.0 * self.load * duty)
        self.current.set(min(ADC_MAX, round(self.current_mA * ADC_MAX / CURRENT_FULL_MA)))
        self.tacho.set(round(60e6 / (self.rpm * PULSES_PER_REV)) if self.rpm > 30 else 0)
        over = self.current_mA > self.comparator_mA
        if over and not self._over:
            self.comparator.fire()
        self._over = over
