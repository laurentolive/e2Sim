"""Fan: both boards simulated (system.yaml), and endurance in accelerated time (spec §16.3)."""

from pathlib import Path

import pytest

import e2sim

SYSTEM = Path(__file__).parent.parent / "sim" / "system.yaml"
APP_FAULT_MOTOR = 16
FAULT_OVERCURRENT, FAULT_BLOCKED = 1, 2


@pytest.fixture
def system(e2sim_toolchain, tmp_path):
    with e2sim.Sim(SYSTEM, toolchain=e2sim_toolchain, work_dir=tmp_path) as s:
        yield s


def press(sim, port, ms=100):
    sim[port].press(ms=ms)
    sim.run(ms=ms + 200)


def start_fan(sim, level):
    press(sim, "hmi.BTN_POWER", 300)
    sim.run(s=0.5)
    press(sim, "hmi.BTN_POWER")
    for _ in range(level - 1):
        press(sim, "hmi.BTN_PLUS")


@e2sim.requirement("FAN-SYS-01")
def test_t09_two_firmwares(system):
    sim = system
    assert [m.name for m in sim.instance("hmi").models] == ["Battery", "TempSensor"], \
        "the MotorBoard model is replaced by the fan_motor firmware"
    start_fan(sim, 1)
    for level, rpm in ((1, 600), (2, 900), (3, 1200), (4, 1500), (5, 1800)):
        if level > 1:
            press(sim, "hmi.BTN_PLUS")
        sim.run(s=2)
        assert sim.var("motor:motor.rpmCmd") == rpm
        assert abs(sim.var("motor:motor.rpmMeas") - rpm) <= rpm * 0.03, f"speed regulated at level {level}"
        assert abs(sim.var("hmi:app.rpmMeasured") - rpm) <= rpm * 0.03, "measured speed reported to the HMI"
    sim["hmi.LCD"].assert_matches("ref/system_speed5.png")


@e2sim.requirement("FAN-MOT-01")
def test_t07_pwm_to_model(system):
    sim = system
    start_fan(sim, 3)
    sim.run(s=2)
    duty = sim["motor.PWM_MOTOR"].value
    assert 450 <= duty <= 550, "PI output: about half duty for 1200 rpm at nominal load"
    sim.model("motor.Motor").load = 1.5
    sim.run(s=2)
    assert sim["motor.PWM_MOTOR"].value > duty + 150, "heavier load: more duty for the same speed"
    assert abs(sim.var("motor:motor.rpmMeas") - 1200) <= 40


@e2sim.requirement("FAN-MOT-02")
def test_t08_overcurrent_interrupt(system):
    sim = system
    start_fan(sim, 3)
    sim.run(s=1)
    motor = sim.model("motor.Motor")
    motor.comparator_mA = 1500  # below the software protection (2 A, 50 ms): the comparator acts first
    fired = []
    fire = motor.comparator.fire
    motor.comparator.fire = lambda: (fired.append(sim.now_ns), fire())
    motor.blocked = True
    seen = set()
    sim.run_until(lambda: fired, timeout_s=3, desc="comparator")
    t = fired[0]
    sim.run(ms=5)
    # the interrupt cuts the PWM in the quantum the event is delivered, without waiting for the 10 ms loop
    cut = [tc for tc, v in sim["motor.PWM_MOTOR"].history if v == 0 and tc >= t]
    assert cut and cut[0] - t <= 1_000_000
    assert sim.var("motor:motor.faults") & FAULT_OVERCURRENT
    sim.run_until(lambda: seen.add(sim.var("hmi:app.fault")) or any(f & APP_FAULT_MOTOR for f in seen),
                  timeout_s=1, desc="motor fault on the HMI")


@e2sim.requirement("FAN-MOT-03")
def test_t08_blocked_rotor(system):
    sim = system
    start_fan(sim, 2)
    sim.run(s=1)
    motor = sim.model("motor.Motor")
    motor.stall_mA = 1800  # stall current below both current protections: only the speed detection acts
    motor.blocked = True
    sim.run_until(lambda: sim.var("motor:motor.faults") & FAULT_BLOCKED, timeout_s=2, desc="blocked rotor")
    assert sim["motor.PWM_MOTOR"].value == 0


@e2sim.requirement("E2SIM-DETERMINISM")
def test_t09_system_determinism(e2sim_toolchain, tmp_path):
    digests = []
    for i in range(2):
        with e2sim.Sim(SYSTEM, toolchain=e2sim_toolchain, work_dir=tmp_path / str(i)) as sim:
            start_fan(sim, 2)
            sim.model("motor.Motor").load = 1.3
            sim.run(s=2)
            digests.append(sim.trace_digest())
    assert digests[0] == digests[1]


@e2sim.requirement("FAN-HMI-07")
def test_t10_running_time_counter(sim):
    """Endurance in accelerated time: the running time counter, saved every minute."""
    start = sim.now
    press(sim, "BTN_POWER", 300)
    press(sim, "BTN_POWER")
    sim.run(s=10 * 60)
    assert sim.var("settings.runMinutes") == 10
    assert sim.now - start >= 600
