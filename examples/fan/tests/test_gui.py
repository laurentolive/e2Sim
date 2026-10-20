"""Web GUI: the JSON API that the page (and any tool) uses (spec §7.3)."""

import json
import threading
import time
import urllib.request

import e2sim
from e2sim.gui import Gui


def call(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read()


def wait(port, cond, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = json.loads(call(port, "/api/state"))
        if s.get("instances") and cond(s):
            return s
        time.sleep(0.05)
    raise AssertionError("state not reached")


@e2sim.requirement("E2SIM-GUI-01")
def test_gui_api(e2sim_board, e2sim_toolchain, tmp_path):
    sim = e2sim.Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path)
    gui = Gui(sim, port=0)
    th = threading.Thread(target=gui.serve, kwargs={"duration_s": 30}, daemon=True)
    th.start()
    try:
        while gui.httpd is None:
            time.sleep(0.01)
        port = gui.port
        assert b"<title>e2Sim</title>" in call(port, "/")
        layout = json.loads(call(port, "/api/layout"))
        inst = layout["instances"][0]
        names = {p["name"]: p for p in inst["ports"]}
        assert names["LCD"]["fb"] == {"w": 128, "h": 64}
        assert names["VBAT_ADC"]["model"] == "Battery"
        assert [m["name"] for m in inst["models"]] == ["Battery", "TempSensor", "MotorBoard"]
        skin = inst["skin"]
        assert (skin["w"], skin["h"]) == (400, 520)
        assert {w["port"] for w in skin["widgets"]} == {"LCD", "BTN_MINUS", "BTN_POWER", "BTN_PLUS", "LED"}
        assert call(port, skin["url"]).startswith(b"<svg"), "image of the product served"

        call(port, "/api/cmd", {"op": "speed", "value": 0})
        call(port, "/api/cmd", {"op": "press", "port": "BTN_POWER", "ms": 300})
        s = wait(port, lambda s: s["instances"][0]["powered"] and s["instances"][0]["values"]["SELF_HOLD"] == 1)
        assert s["running"]
        wait(port, lambda s: "LCD" in s["instances"][0]["fb"] and "fan_hmi boot" in s["instances"][0]["streams"]["UART_DEBUG"])

        call(port, "/api/cmd", {"op": "param", "model": "TempSensor", "name": "temp_C", "value": "70"})
        wait(port, lambda s: s["instances"][0]["models"]["TempSensor"]["temp_C"] == 70.0)

        call(port, "/api/cmd", {"op": "pause"})
        t0 = wait(port, lambda s: not s["running"])["t"]
        time.sleep(0.1)
        assert json.loads(call(port, "/api/state"))["t"] == t0, "paused"
        call(port, "/api/cmd", {"op": "step"})
        s = wait(port, lambda s: not s["running"] and s["t"] > t0)
        assert abs(s["t"] - t0 - layout["quantum_ms"] / 1000) < 1e-9, "one quantum"

        try:
            call(port, "/api/cmd", {"op": "set", "port": "LED", "value": 1})
            raise AssertionError("an output cannot be set")
        except urllib.error.HTTPError as e:
            assert e.code == 400
        call(port, "/api/cmd", {"op": "quit"})
        th.join(10)
        assert not th.is_alive()
    finally:
        sim.stop()
