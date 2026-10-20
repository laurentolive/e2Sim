"""Local web GUI generated from board.yaml / system.yaml (spec §7.3).

HTTP on 127.0.0.1, stdlib only. The page polls GET /api/state and sends POST /api/cmd; the same JSON API
drives the simulation from any tool. The simulation runs in the thread that calls Gui.serve(): commands are
applied at quantum boundaries.
"""

from __future__ import annotations

import base64
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .model import Param
from .sim import Sim, SimError

WEB = Path(__file__).parent / "web"
STREAM_TAIL = 8192


class Gui:
    def __init__(self, sim: Sim, port: int = 8080):
        self.sim = sim
        self.port = port
        self.running = True
        self.speed = 1.0          # virtual / wall; 0: as fast as possible
        self.commands: queue.Queue = queue.Queue()
        self._state = b"{}"
        self._lock = threading.Lock()
        self._quit = threading.Event()
        self.httpd: ThreadingHTTPServer | None = None
        self.license = ""          # shown in the banner, no licence dialog in the page (spec §17.4)

    # -- description of the page -------------------------------------------
    def layout(self) -> dict:
        out = {"instances": [], "quantum_ms": self.sim.quantum_ns / 1e6}
        for st in self.sim.instances:
            widgets = {w.get("port"): w for w in st.board.gui.get("widgets", []) if w.get("port")}
            ports = []
            for p in st.ports.values():
                spec = p.spec
                d = {"name": p.name, "type": p.type, "dir": spec.dir}
                if spec.framebuffer:
                    d["fb"] = {"w": int(spec.framebuffer["w"]), "h": int(spec.framebuffer["h"])}
                if p.name in widgets:
                    d["widget"] = widgets[p.name]
                if p.relay is not None:
                    d["tcp"] = p.relay.port
                if p.listeners:
                    d["model"] = p.listeners[0][0].name  # driven by a model: shown, not edited
                ports.append(d)
            models = []
            for m in st.models:
                params = []
                for cls in type(m).__mro__:
                    for k, v in vars(cls).items():
                        if isinstance(v, Param) and k not in [x["name"] for x in params]:
                            params.append({"name": k, "doc": v.doc, "kind": type(getattr(m, k)).__name__})
                models.append({"name": m.name, "params": params})
            out["instances"].append({"name": st.name, "board": st.board.name, "ports": ports, "models": models,
                                     "escope": st.escope.port if st.escope else None,
                                     "arch": f"{st.inst.ptr_size * 8} bits"})
        return out

    def snapshot(self) -> dict:
        insts = []
        for st in self.sim.instances:
            values, streams, fbs = {}, {}, {}
            for p in st.ports.values():
                if p.type in ("bit", "value"):
                    values[p.name] = p.value
                elif p.type == "stream":
                    streams[p.name] = p.rx[-STREAM_TAIL:].decode("utf-8", "replace")
                elif p.type == "block" and p.spec.framebuffer and p.mm is not None:
                    fbs[p.name] = base64.b64encode(p.read_block()).decode()
            models = {m.name: {k: v for k, v in m.params.items()} for m in st.models}
            insts.append({"name": st.name, "powered": st.powered, "resets": [[t, c] for t, c in st.resets[-5:]],
                          "values": values, "streams": streams, "fb": fbs, "models": models,
                          "logs": [[t, lv, tx] for t, lv, tx in st.logs[-20:]]})
        return {"t": self.sim.now, "running": self.running, "speed": self.speed, "instances": insts,
                "license": self.license}

    # -- commands -------------------------------------------------------------
    def apply(self, cmd: dict):
        op = cmd.get("op")
        sim = self.sim
        if op == "run":
            self.running = True
        elif op == "pause":
            self.running = False
        elif op == "step":
            self.running = False
            sim.step()
        elif op == "speed":
            self.speed = float(cmd["value"])
        elif op == "set":
            sim[cmd["port"]].set(int(cmd["value"]))
        elif op == "press":
            sim[cmd["port"]].press(ms=float(cmd.get("ms", 100)))
        elif op == "write":
            sim[cmd["port"]].write(cmd["text"])
        elif op == "clear":
            sim[cmd["port"]].clear()
        elif op == "param":
            model = sim.model(cmd["model"])
            cur = getattr(model, cmd["name"])
            v = cmd["value"]
            if isinstance(cur, bool):
                v = bool(v)
            elif isinstance(cur, int):
                v = int(float(v))
            elif isinstance(cur, float):
                v = float(v)
            setattr(model, cmd["name"], v)
        elif op == "power":
            st = sim.instance(cmd["instance"])
            st.power_on() if cmd.get("on", True) else st.power_off()
        elif op == "reset":
            sim.instance(cmd["instance"]).reset("host")
        elif op == "quit":
            self._quit.set()
        else:
            raise SimError(f"unknown command {op!r}")

    # -- loop -------------------------------------------------------------------
    def serve(self, open_browser: bool = False, duration_s: float | None = None):
        """Serve the page and run the simulation in this thread until quit (Ctrl+C or {"op": "quit"})."""
        gui = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, body: bytes, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
                elif self.path == "/api/layout":
                    self._send(200, gui._layout)
                elif self.path == "/api/state":
                    with gui._lock:
                        self._send(200, gui._state)
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                if self.path != "/api/cmd":
                    self._send(404, b"{}")
                    return
                try:
                    cmd = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                except json.JSONDecodeError:
                    self._send(400, b'{"error": "json expected"}')
                    return
                done = threading.Event()
                result = {}
                gui.commands.put((cmd, done, result))
                done.wait(5)
                self._send(200 if "error" not in result else 400, json.dumps(result).encode())

        self.sim.start()
        self._layout = json.dumps(self.layout()).encode()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        if open_browser:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{self.port}/")
        try:
            self._loop(duration_s)
        finally:
            self.httpd.shutdown()
            self.httpd.server_close()

    def _loop(self, duration_s):
        wall0 = time.perf_counter()
        last_state = 0.0
        virt_ref, wall_ref, speed_ref = self.sim.now_ns, wall0, None
        while not self._quit.is_set():
            if duration_s is not None and time.perf_counter() - wall0 > duration_s:
                break
            while True:
                try:
                    cmd, done, result = self.commands.get_nowait()
                except queue.Empty:
                    break
                try:
                    self.apply(cmd)
                    result["ok"] = True
                except (SimError, KeyError, ValueError, TypeError) as e:
                    result["error"] = str(e)
                done.set()
            now = time.perf_counter()
            if self.running:
                if speed_ref != self.speed:
                    virt_ref, wall_ref, speed_ref = self.sim.now_ns, now, self.speed
                if self.speed <= 0:
                    self.sim.run(ms=50)
                else:
                    target = virt_ref + (now - wall_ref) * self.speed * 1e9
                    ahead = self.sim.now_ns - target
                    if ahead > 0:
                        time.sleep(min(0.02, ahead / 1e9 / self.speed))
                    else:
                        self.sim.run(ms=min(50.0, max(self.sim.quantum_ns / 1e6, -ahead / 1e6)))
            else:
                speed_ref = None
                time.sleep(0.01)
            if now - last_state > 0.05:
                last_state = now
                state = json.dumps(self.snapshot()).encode()
                with self._lock:
                    self._state = state
