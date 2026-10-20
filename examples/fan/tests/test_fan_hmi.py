"""Fan HMI on e2Sim: system tests of the firmware (spec §16.3, V0 scope)."""

import e2sim
from fan_helpers import boot, fan_on, key, toggles

APP_FAULT_LINK, APP_FAULT_TEMP, APP_FAULT_BAT, APP_FAULT_SENSOR, APP_FAULT_MOTOR = 1, 2, 4, 8, 16


@e2sim.requirement("FAN-HMI-01")
def test_t01_power_latch_and_keys(sim):
    assert not sim.powered
    boot(sim)
    assert sim.powered and sim["LED"] == 1
    sim.run(s=1)
    assert sim.powered, "power must stay on once the key is released"

    fan_on(sim)
    assert sim["MOTOR_EN"] == 1
    key(sim, "BTN_PLUS")
    key(sim, "BTN_PLUS")
    assert sim.var("app.speedLevel") == 3
    key(sim, "BTN_MINUS")
    assert sim.var("app.speedLevel") == 2

    key(sim, "BTN_PLUS", ms=10)  # bounce shorter than the debounce time: ignored
    assert sim.var("app.speedLevel") == 2


@e2sim.requirement("FAN-HMI-02")
def test_t02_display(sim):
    boot(sim)
    fan_on(sim)
    sim.run(s=2)
    sim["LCD"].assert_matches("ref/running_speed1.png")
    # the LCD controller reset (busy wait on the HAL counter) delays the first frame to the motor board
    first = next(t for t, inst, port, _ in sim.trace if port == "UART_LINK")
    boot_t = sim.resets[0][0]
    assert first - boot_t >= 20_000_000 + 100_000_000


@e2sim.requirement("FAN-HMI-03")
def test_t03_motor_link(sim):
    boot(sim)
    fan_on(sim)
    key(sim, "BTN_PLUS")
    key(sim, "BTN_PLUS")
    board = sim.model("MotorBoard")
    sim.run(s=3)
    assert board.target == 1200
    assert abs(sim.var("app.rpmMeasured") - 1200) < 20

    board.no_answer = True
    sim.run(s=1)
    assert sim.var("app.fault") & APP_FAULT_LINK
    t = sim.now_ns
    sim.run(s=1)
    assert toggles(sim["LED"], t) >= 3, "LED blinks at 2 Hz on fault"
    sim["LCD"].assert_matches("ref/link_lost.png")

    board.no_answer = False
    board.corrupt_crc = True
    sim.run(s=1)
    assert sim.var("app.fault") & APP_FAULT_LINK, "frames with a bad CRC are rejected"

    board.corrupt_crc = False
    board.faults = 2
    sim.run(s=0.5)
    assert sim.var("app.fault") & APP_FAULT_MOTOR
    assert sim["MOTOR_EN"] == 0


@e2sim.requirement("FAN-HMI-04")
def test_t04_settings_and_power_off(sim):
    boot(sim)
    fan_on(sim)
    for _ in range(3):
        key(sim, "BTN_PLUS")
    assert sim.var("app.speedLevel") == 4

    sim["BTN_POWER"].press(s=2.5)  # long press: save and release the latch
    sim.run(s=2.4)
    assert sim.var("app.shuttingDown")
    assert sim.powered, "still powered while the key is pressed"
    sim.run(s=0.5)
    assert not sim.powered

    boot(sim)
    assert sim.var("settings.speedLevel") == 4
    assert "settings ok" in sim["UART_DEBUG"].text

    # corrupted EEPROM: defaults at the next boot
    sim["BTN_POWER"].press(s=2.5)
    sim.run(s=3)
    assert not sim.powered
    sim["EEPROM"].write_block(2, b"\x07")
    sim["UART_DEBUG"].clear()
    boot(sim)
    assert "reset to defaults" in sim["UART_DEBUG"].text
    assert sim.var("app.speedLevel") == 1


@e2sim.requirement("FAN-HMI-05")
def test_t05_sensor_and_battery(sim):
    sensor, battery = sim.model("TempSensor"), sim.model("Battery")
    boot(sim)
    fan_on(sim)
    assert sim.var("app.temp_dC") == 250

    sensor.temp_C = 70.0
    sim.run(s=1)
    assert sim.var("app.fault") & APP_FAULT_TEMP
    assert sim["MOTOR_EN"] == 0 and sim.var("app.rpmTarget") == 0
    sensor.temp_C = 40.0
    sim.run(s=1)
    assert not sim.var("app.fault") & APP_FAULT_TEMP
    assert sim["MOTOR_EN"] == 1

    battery.voltage_V = 9.2
    sim.run(s=0.5)
    assert sim.var("app.batPercent") < 10
    assert sim.var("app.fault") & APP_FAULT_BAT


@e2sim.requirement("FAN-HMI-05")
def test_t05_sensor_missing(sim):
    sim.model("TempSensor").no_answer = True
    boot(sim)
    assert sim.var("app.fault") & APP_FAULT_SENSOR


@e2sim.requirement("FAN-HMI-06")
def test_t06_watchdog(sim):
    boot(sim)
    sensor = sim.model("TempSensor")
    sensor.stuck_busy = True  # the firmware waits for the sensor without timeout
    sim.run_until(lambda: any(cause == "wdt" for _, cause in sim.resets), timeout_s=2, desc="watchdog reset")
    sensor.stuck_busy = False
    sim.run(s=1)
    assert sim.powered, "the firmware takes the power latch again after the reset"
    assert sim.var("app.wdtReset")
    assert sim.var("settings.wdtCount") >= 1
    assert "boot (watchdog)" in sim["UART_DEBUG"].text
    sim["LCD"].assert_matches("ref/wdt_reset.png")


def scenario(sim):
    boot(sim)
    fan_on(sim)
    key(sim, "BTN_PLUS")
    sim.model("TempSensor").temp_C = 65.0
    sim.run(s=2)
    sim.model("TempSensor").temp_C = 30.0
    sim.run(s=30)


@e2sim.requirement("E2SIM-DETERMINISM")
def test_t00_determinism(e2sim_board, e2sim_toolchain, tmp_path, monkeypatch):
    """Same scenario: same trace, run after run, and with long runs as quantum by quantum."""
    results = []
    for i, fixed in enumerate((False, False, True)):
        with e2sim.Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path / str(i)) as sim:
            if fixed:
                run = sim.run
                monkeypatch.setattr(sim, "run", lambda **kw: run(fixed=True, **kw))
            scenario(sim)
            results.append((sim.trace_digest(), sim["LCD"].read_block(), sim.now_ns))
    assert results[0] == results[1]
    assert results[0] == results[2], "long runs must give the quantum by quantum result"


@e2sim.requirement("E2SIM-FORCE-01")
def test_t16_force_an_input_driven_by_a_model(sim):
    """A host override wins over the model (broken divider: 0 ADC point), release gives the input back."""
    boot(sim)
    pct = sim.var("app.batPercent")
    sim["VBAT_ADC"].force(0)
    sim.run(s=0.5)
    assert sim.var("app.batPercent") == 0 and sim.var("app.fault") & APP_FAULT_BAT
    assert sim.model("Battery").voltage_V == 12.0, "the model still runs, its value is overridden"
    sim["VBAT_ADC"].release()
    sim.run(s=0.5)
    assert sim.var("app.batPercent") == pct and not sim.var("app.fault") & APP_FAULT_BAT
    try:
        sim["LED"].force(1)
        raise AssertionError("an output cannot be forced")
    except e2sim.SimError:
        pass
