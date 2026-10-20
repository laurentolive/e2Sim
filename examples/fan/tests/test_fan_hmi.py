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


@e2sim.requirement("E2SIM-RESET-02")
def test_t17_reset_process(e2sim_board, e2sim_toolchain, tmp_path):
    """reset: process: a watchdog reset ends the runner, a new process boots at the same virtual time."""
    from e2sim.sim import replay

    rec = tmp_path / "proc.e2simrec"
    with e2sim.Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path / "w", reset_mode="process",
                   record=rec) as sim:
        boot(sim)
        st = sim.instance()
        pid = st.inst.pid
        sim.model("TempSensor").stuck_busy = True
        sim.run_until(lambda: any(c == "wdt" for _, c in sim.resets), timeout_s=2, desc="watchdog reset")
        sim.model("TempSensor").stuck_busy = False
        sim.run(s=1)
        assert st.inst.pid != pid and st.inst.restarts == 1, "new runner process"
        assert sim.powered and sim.var("app.wdtReset"), "the firmware boots again in the new process"
        assert sim.var("settings.wdtCount") == 1, "NVM file kept across the processes"
        assert "boot (watchdog)" in sim["UART_DEBUG"].text
        sim["LCD"].assert_matches("ref/wdt_reset.png")
    _, same = replay(rec, work_dir=tmp_path / "replay")
    assert same, "a process reset replays identically"


def _with_baud(e2sim_board, e2sim_toolchain, tmp_path, port, baud):
    sim = e2sim.Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path)
    sim.board.ports[port].baud = baud
    return sim


@e2sim.requirement("E2SIM-BAUD-01")
def test_t18_stream_line_rate(e2sim_board, e2sim_toolchain, tmp_path):
    """baud: the bytes of the firmware arrive at the line rate (10 bits per byte)."""
    with _with_baud(e2sim_board, e2sim_toolchain, tmp_path, "UART_DEBUG", 9600) as sim:
        sim["BTN_POWER"].press(ms=300)
        sim.run_until(lambda: sim["SELF_HOLD"] == 1, timeout_s=1)
        boot_line = next(d for t, i, p, d in sim.trace if p == "UART_DEBUG")
        t0 = next(t for t, i, p, d in sim.trace if p == "UART_DEBUG")
        sim.run_until(lambda: len(sim["UART_DEBUG"].data) >= len(boot_line), timeout_s=1)
        elapsed = sim.now_ns - t0
        expected = len(boot_line) * 10 / 9600 * 1e9
        assert expected <= elapsed <= expected + 2e6, f"{len(boot_line)} bytes at 9600 baud: {elapsed / 1e6:.1f} ms"


@e2sim.requirement("E2SIM-BAUD-02")
def test_t18_link_saturated(e2sim_board, e2sim_toolchain, tmp_path):
    """300 baud cannot carry a 7 byte frame every 100 ms: the bytes pile up on the line, the delay grows."""
    backlog = {}
    for baud in (300, 9600):
        with _with_baud(e2sim_board, e2sim_toolchain, tmp_path / str(baud), "UART_LINK", baud) as sim:
            boot(sim)
            fan_on(sim)
            sim.run(s=1)
            first = len(sim["UART_LINK"].rx_q)
            sim.run(s=2)
            backlog[baud] = (first, len(sim["UART_LINK"].rx_q))
    assert backlog[300][1] > backlog[300][0] + 30, f"300 baud: backlog grows {backlog[300]}"
    assert backlog[9600][1] <= 7, f"9600 baud: no backlog {backlog[9600]}"


@e2sim.requirement("E2SIM-BOARD-01")
def test_t19_board_index_by_macro(sim):
    """board.yaml names a port by a #define of the firmware (HAL_UART_TERMINAL), resolved from the DWARF (-g3)."""
    port = sim["UART_DEBUG"]
    assert port.spec.idx == "HAL_UART_TERMINAL" and port.idx == 1
    boot(sim)
    assert "fan_hmi boot" in port.text
    try:
        sim.instance().symbols.constants(["HAL_NOT_DEFINED"])
        raise AssertionError("an unknown name is an error")
    except e2sim.symbols.SymbolError as e:
        assert "HAL_NOT_DEFINED" in str(e)
