"""Fan example - demonstration of e2Sim, chapter by chapter (spec §16.4).

The GUI runs the two firmwares (sim/system.yaml); the story drives them through the public JSON API of the
GUI, as a user or a tool would, and checks each chapter. Guide: demo/DEMO.md.

    python demo/demo.py                 interactive: Enter between chapters, real time (open the GUI page)
    python demo/demo.py --auto          chapters chained after a pause
    python demo/demo.py --check         as fast as possible, no browser: the demo as a test (make demo-check)
Options: --toolchain host64, --port 8080, --record out/demo.e2simrec (chapter 11 replays it).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from e2sim.gui import Gui  # noqa: E402
from e2sim.sim import Sim, replay  # noqa: E402

SYSTEM = HERE.parent / "sim" / "system.yaml"
FAULT_TEMP, FAULT_BAT, FAULT_MOTOR = 2, 4, 16
FAULT_OVERCURRENT = 1


class DemoError(AssertionError):
    pass


class Api:
    """Client of the GUI JSON API."""

    def __init__(self, port: int, fast: bool):
        self.url = f"http://127.0.0.1:{port}"
        self.fast = fast

    def cmd(self, **c) -> dict:
        req = urllib.request.Request(self.url + "/api/cmd", data=json.dumps(c).encode())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise DemoError(f"{c}: {e.read().decode()}") from None

    def state(self) -> dict:
        return self.cmd(op="state")

    def inst(self, name: str) -> dict:
        return next(i for i in self.state()["instances"] if i["name"] == name)

    def var(self, expr: str):
        return self.cmd(op="var", expr=expr)["value"]

    def press(self, port: str, ms: float = 100):
        self.cmd(op="press", port=port, ms=ms)
        self.run_for(ms / 1000 + 0.2)

    def param(self, model: str, name: str, value):
        self.cmd(op="param", model=model, name=name, value=value)

    def run_for(self, seconds: float):
        """Wait for seconds of virtual time."""
        t0 = self.state()["t"]
        self.wait(lambda: self.state()["t"] >= t0 + seconds, f"{seconds} s of virtual time", wall_s=60 + seconds * 5)

    def wait(self, cond, what: str, wall_s: float = 60):
        end = time.monotonic() + wall_s
        while not cond():
            if time.monotonic() > end:
                raise DemoError(f"not reached: {what}")
            time.sleep(0.01 if self.fast else 0.05)


def check(cond: bool, what: str):
    if not cond:
        raise DemoError(what)
    print(f"    ok: {what}")


# -- chapters ------------------------------------------------------------------------------------------------
def ch_power_on(api: Api):
    api.press("hmi.BTN_POWER", 300)
    api.wait(lambda: api.inst("hmi")["values"]["SELF_HOLD"] == 1, "SELF_HOLD")
    api.run_for(1)
    check(api.inst("hmi")["powered"], "the HMI holds its power latch once POWER is released")
    check("fan_hmi boot" in api.inst("hmi")["streams"]["UART_DEBUG"], "boot message on the debug UART")


def ch_two_firmwares(api: Api):
    api.press("hmi.BTN_POWER")
    for _ in range(4):
        api.press("hmi.BTN_PLUS")
        api.run_for(1.5)
    api.run_for(1)
    rpm = api.var("motor:motor.rpmMeas")
    check(abs(rpm - 1800) < 60, f"level 5: the motor firmware regulates at {rpm} rpm (1800)")
    check(abs(api.var("hmi:app.rpmMeasured") - rpm) < 60, "the HMI shows the speed measured by the motor board")
    api.press("hmi.BTN_MINUS")
    api.press("hmi.BTN_MINUS")
    api.run_for(2)


def ch_observe(api: Api):
    layout = json.loads(urllib.request.urlopen(api.url + "/api/layout").read())
    for i in layout["instances"]:
        print(f"    eScope endpoint {i['name']}: TCP:127.0.0.1,{i['escope']} ({i['arch']})")
        for p in i["ports"]:
            if p.get("tcp"):
                print(f"    TCP relay {i['name']}.{p['name']}: TCP:127.0.0.1,{p['tcp']}")
    lvl, rpm, duty = api.var("hmi:app.speedLevel"), api.var("motor:motor.rpmMeas"), api.var("motor:motor.duty")
    print(f"    sim.var: hmi app.speedLevel = {lvl}, motor motor.rpmMeas = {rpm}, motor.duty = {duty}")
    check(lvl == 3, "firmware variables read by symbol, without code in the firmware")


def ch_model(api: Api):
    duty = api.var("motor:motor.duty")
    api.param("motor.Motor", "load", 1.5)
    api.run_for(2)
    duty2 = api.var("motor:motor.duty")
    check(duty2 > duty + 100, f"heavier load: the PI raises the duty {duty} -> {duty2} per mille")
    api.param("motor.Motor", "load", 1.0)
    api.run_for(1.5)


def ch_spi_sensor(api: Api):
    api.param("hmi.TempSensor", "temp_C", 70.0)
    api.wait(lambda: api.var("hmi:app.fault") & FAULT_TEMP, "OVER TEMP")
    api.run_for(0.5)
    check(api.inst("motor")["values"]["PWM_MOTOR"] == 0, "70 degC: OVER TEMP, motor stopped")
    api.param("hmi.TempSensor", "temp_C", 25.0)
    api.wait(lambda: not api.var("hmi:app.fault") & FAULT_TEMP, "temperature fault cleared")
    api.run_for(1.5)
    check(api.inst("motor")["values"]["PWM_MOTOR"] > 0, "back to 25 degC: the fan restarts")


def ch_battery(api: Api):
    api.param("hmi.Battery", "voltage_V", 9.2)
    api.wait(lambda: api.var("hmi:app.fault") & FAULT_BAT, "BAT LOW")
    check(api.var("hmi:app.batPercent") < 10, "9.2 V: BAT LOW on the display")
    api.run_for(1)
    api.param("hmi.Battery", "voltage_V", 12.0)
    api.wait(lambda: not api.var("hmi:app.fault") & FAULT_BAT, "battery fault cleared")


def ch_interrupt(api: Api):
    api.param("motor.Motor", "comparator_mA", 1500)
    api.param("motor.Motor", "blocked", True)
    api.wait(lambda: api.var("motor:motor.faults") & FAULT_OVERCURRENT, "comparator interrupt")
    check(api.inst("motor")["values"]["PWM_MOTOR"] == 0, "rotor blocked: the comparator interrupt cuts the PWM")
    api.wait(lambda: api.var("hmi:app.fault") & FAULT_MOTOR, "MOTOR FAULT on the HMI")
    print("    ok: MOTOR FAULT reported to the HMI")
    api.param("motor.Motor", "blocked", False)
    api.param("motor.Motor", "comparator_mA", 3000)
    api.wait(lambda: api.var("motor:motor.rpmMeas") > 1000, "restart after the fault", wall_s=90)
    check(True, "fault cleared through ENABLE, the fan restarts")


def ch_watchdog(api: Api):
    resets = len(api.inst("hmi")["resets"])
    api.param("hmi.TempSensor", "stuck_busy", True)
    api.wait(lambda: any(c == "wdt" for _, c in api.inst("hmi")["resets"][-1:]) and len(api.inst("hmi")["resets"]) > resets,
             "watchdog reset")
    api.param("hmi.TempSensor", "stuck_busy", False)
    api.run_for(1)
    check(api.var("hmi:app.wdtReset") == 1, "sensor stuck: reset by the watchdog in the same process, WDT RESET")
    check(api.var("hmi:settings.wdtCount") >= 1, "watchdog resets counted in NVM")
    api.press("hmi.BTN_POWER")  # acknowledge, fan on again
    api.run_for(1)


def ch_fast(api: Api):
    m0 = api.var("hmi:settings.runMinutes")
    api.cmd(op="speed", value=0)
    api.wait(lambda: api.var("hmi:settings.runMinutes") >= m0 + 1, "one more running minute", wall_s=180)
    if not api.fast:
        api.cmd(op="speed", value=1)
    check(True, f"accelerated time: running minutes {m0} -> {api.var('hmi:settings.runMinutes')} saved in NVM")


def ch_power_off(api: Api):
    lvl = api.var("hmi:settings.speedLevel")
    api.press("hmi.BTN_POWER", 2500)
    api.wait(lambda: not api.inst("hmi")["powered"], "power off")
    check(True, "long press: settings saved, power latch released")
    api.run_for(1)
    api.press("hmi.BTN_POWER", 300)
    api.wait(lambda: api.inst("hmi")["powered"], "power on")
    api.run_for(1)
    check(api.var("hmi:settings.speedLevel") == lvl, f"power on again: speed {lvl} found in the NVM")


CHAPTERS = [
    ("Power on", "POWER pressed: the firmware starts, unchanged, and holds its power latch", ch_power_on),
    ("Two firmwares", "HMI and motor board linked: speeds 1 to 5, regulation, display", ch_two_firmwares),
    ("Observe", "eScope on every firmware without code, embedded eScope, sim.var()", ch_observe),
    ("The model answers", "motor load x1.5: the PI of the motor firmware raises the duty", ch_model),
    ("SPI sensor", "70 degC from the sensor model: OVER TEMP, motor stopped", ch_spi_sensor),
    ("Battery", "9.2 V on the ADC: BAT LOW", ch_battery),
    ("External interrupt", "rotor blocked: the comparator interrupt cuts the PWM at once", ch_interrupt),
    ("Watchdog", "sensor stuck busy: watchdog reset in the same process", ch_watchdog),
    ("Accelerated time", "max speed: running minutes saved in NVM", ch_fast),
    ("Power off", "long press: save, power off; on again: settings found", ch_power_off),
]


def story(api: Api, gui: Gui, mode: str, errors: list):
    try:
        api.cmd(op="speed", value=0 if mode == "check" else 1)
        for n, (title, text, fn) in enumerate(CHAPTERS, 1):
            caption = f"{n}. {title} - {text}"
            print(f"\n== {caption}")
            api.cmd(op="note", text=caption)
            if mode == "interactive":
                input("   Enter to run the chapter... ")
            fn(api)
            if mode == "auto":
                api.run_for(2)
        api.cmd(op="note", text="End of the demo - 11. the recording is replayed in the console")
        print("\n== demo done")
        if mode == "interactive":
            input("   Enter to stop the simulation and replay the recording... ")
    except Exception as e:  # noqa: BLE001 - reported by main
        errors.append(e)
    finally:
        try:
            api.cmd(op="quit")
        except Exception:  # noqa: BLE001
            gui._quit.set()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto", action="store_true", help="chain the chapters")
    ap.add_argument("--check", action="store_true", help="as fast as possible, no browser, checks only")
    ap.add_argument("--toolchain")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--record", default=str(HERE.parent / "out" / "demo.e2simrec"))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    mode = "check" if args.check else "auto" if args.auto else "interactive"

    work = HERE.parent / "out" / "demo"
    sim = Sim(SYSTEM, toolchain=args.toolchain, work_dir=work, record=args.record)
    gui = Gui(sim, port=0 if mode == "check" else args.port)
    errors: list = []

    def start_story():
        while gui.httpd is None:
            time.sleep(0.01)
        print(f"e2sim demo: GUI on http://127.0.0.1:{gui.port}/")
        story(Api(gui.port, fast=mode == "check"), gui, mode, errors)

    threading.Thread(target=start_story, daemon=True).start()
    try:
        gui.serve(open_browser=mode != "check" and not args.no_browser)
    finally:
        sim.stop()
    if errors:
        print(f"\ne2sim demo: FAILED: {errors[0]}", file=sys.stderr)
        return 1

    print("\n== 11. Replay: the recording sent again to the firmwares, without models nor script")
    _, same = replay(args.record, toolchain=args.toolchain, work_dir=HERE.parent / "out" / "demo_replay")
    print("    ok: same outputs as recorded" if same else "    FAILED: outputs differ")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
