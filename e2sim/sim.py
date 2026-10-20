"""Simulation session: virtual time master, ports, models, scripts (spec §4.3, §7)."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import mmap
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import board as board_mod
from . import png, proto, toolchains
from .instance import Instance
from .model import Model
from .symbols import Symbols


class SimError(Exception):
    pass


class SimTimeout(AssertionError):
    """run_until() condition not met in time (an AssertionError: a failed test, not an error)."""


def _ns(s: float = 0, ms: float = 0, us: float = 0) -> int:
    return round(s * 1e9 + ms * 1e6 + us * 1e3)


class Port:
    """A port seen from the host: sim["NAME"]."""

    def __init__(self, sim: Sim, inst: InstanceState, spec: board_mod.PortSpec, cls: int, idx: int):
        self._sim = sim
        self._inst = inst
        self.spec = spec
        self.name = spec.name
        self.type = spec.type
        self.cls = cls
        self.idx = idx
        self.value = spec.default if spec.dir != "out" else 0
        self.history: list[tuple[int, int]] = []   # (t_ns, value) changes of a firmware output
        self.rx = bytearray()                       # stream: bytes written by the firmware
        self.responder: Callable[[bytes], bytes] | None = None  # xfer without model
        self.mm: mmap.mmap | None = None
        self.listeners: list[Callable] = []         # models bound to this port

    # -- bit / value ---------------------------------------------------
    def get(self) -> int:
        return self.value

    def set(self, v: int):
        if self.spec.dir == "out":
            raise SimError(f"{self.name}: firmware output, cannot be set")
        if self.type not in ("bit", "value"):
            raise SimError(f"{self.name}: {self.type} port, set() needs bit / value")
        self.value = int(v)

    def press(self, ms: float = 100, value: int = 1, s: float = 0):
        """Set the input now, back to its default after the duration."""
        self.set(value)
        self._sim.at(self._sim.now_ns + _ns(s=s, ms=ms), lambda: self.set(self.spec.default))

    def __int__(self): return int(self.value)
    def __index__(self): return int(self.value)
    def __bool__(self): return bool(self.value)
    def __eq__(self, other): return self.value == other if isinstance(other, (int, bool)) else NotImplemented
    def __hash__(self): return hash((self._inst.name, self.name))
    def __repr__(self): return f"<Port {self.name} {self.type} {self.value if self.type in ('bit', 'value') else ''}>"

    # -- stream --------------------------------------------------------
    def write(self, data: bytes | str):
        if self.type != "stream":
            raise SimError(f"{self.name}: not a stream")
        self._inst.stream_tx.append((self.idx, data.encode() if isinstance(data, str) else bytes(data)))

    @property
    def data(self) -> bytes:
        return bytes(self.rx)

    @property
    def text(self) -> str:
        return self.rx.decode("utf-8", "replace")

    def clear(self):
        self.rx.clear()

    # -- event ---------------------------------------------------------
    def fire(self):
        self._inst.events_tx.append(self.idx)

    # -- block ---------------------------------------------------------
    def _block(self) -> mmap.mmap:
        if self.mm is None:
            raise SimError(f"{self.name}: block not created by the firmware yet")
        return self.mm

    def read_block(self, offset: int = 0, size: int | None = None) -> bytes:
        mm = self._block()
        end = len(mm) if size is None else offset + size
        return bytes(mm[offset:end])

    def write_block(self, offset: int, data: bytes):
        """Write in the block between two quanta (fault injection: corrupted NVM...)."""
        self._block()[offset:offset + len(data)] = data

    def rgb(self) -> tuple[bytes, int, int]:
        fb = self.spec.framebuffer
        if not fb:
            raise SimError(f"{self.name}: not a framebuffer")
        w, h, fmt = int(fb["w"]), int(fb["h"]), fb.get("format", "RGB565")
        if fmt != "RGB565":
            raise SimError(f"{self.name}: format {fmt} not supported (RGB565)")
        return png.rgb565_to_rgb(self.read_block(0, w * h * 2), w, h), w, h

    def save_png(self, path: str | Path, scale: int = 1):
        rgb, w, h = self.rgb()
        png.write(path, rgb, w, h, scale)

    def assert_matches(self, ref: str | Path, max_diff_pixels: int = 0):
        """Compare the framebuffer with a reference PNG (relative to the calling file).

        Missing reference or E2SIM_UPDATE_REFS=1: the reference is written (and the test fails if it was
        missing, to be reviewed). On mismatch, <ref>.actual.png is written next to it."""
        ref = Path(ref)
        if not ref.is_absolute():
            ref = Path(inspect.stack()[1].filename).parent / ref
        rgb, w, h = self.rgb()
        if os.environ.get("E2SIM_UPDATE_REFS") == "1" or not ref.is_file():
            missing = not ref.is_file()
            png.write(ref, rgb, w, h)
            if missing:
                raise AssertionError(f"{self.name}: reference {ref} created, check it and run again")
            return
        exp, ew, eh = png.read(ref)
        if (ew, eh) != (w, h):
            raise AssertionError(f"{self.name}: size {w}x{h}, reference {ew}x{eh}")
        diff = sum(1 for i in range(w * h) if rgb[3 * i:3 * i + 3] != exp[3 * i:3 * i + 3])
        if diff > max_diff_pixels:
            actual = ref.with_suffix(".actual.png")
            png.write(actual, rgb, w, h)
            raise AssertionError(f"{self.name}: {diff} pixels differ from {ref.name} (see {actual})")


class InstanceState:
    """Host side of one firmware instance."""

    def __init__(self, sim: Sim, name: str, board: board_mod.Board):
        self.sim = sim
        self.name = name
        self.board = board
        self.inst: Instance | None = None
        self.symbols: Symbols | None = None
        self.ports: dict[str, Port] = {}
        self.by_key: dict[tuple[int, int], Port] = {}
        self.models: list[Model] = []
        self.powered = False
        self.halted = False
        self.resets: list[tuple[int, str]] = []     # (t_ns, cause)
        self.logs: list[tuple[int, str, str]] = []
        self.sent: dict[tuple[int, int], int] = {}  # input values known by the runner
        self.stream_tx: list[tuple[int, bytes]] = []
        self.events_tx: list[int] = []
        self.control: list[bytes] = []              # power / reset records
        self.mem_replies: dict[int, tuple[int, bytes]] = {}
        self._latch_low_since: int | None = None

    def port(self, cls: int, idx: int) -> Port:
        p = self.by_key.get((cls, idx))
        if p is None:  # not declared in board.yaml: created on the fly
            name = f"{proto.CLASS_NAMES.get(cls, cls)}[{idx}]"
            typ = board_mod.DEFAULT_TYPES.get(proto.CLASS_NAMES.get(cls, ""), "value")
            spec = board_mod.PortSpec(name=name, cls=proto.CLASS_NAMES.get(cls, "VALUE"), idx=idx, type=typ, dir="io")
            p = Port(self.sim, self, spec, cls, idx)
            self.ports[name] = p
            self.by_key[(cls, idx)] = p
        return p

    # -- quantum exchange ---------------------------------------------
    def records(self) -> bytes:
        w = proto.Writer()
        for c in self.control:
            w.b += c
        self.control.clear()
        for p in self.ports.values():
            if p.type in ("bit", "value") and p.spec.dir != "out":
                key = (p.cls, p.idx)
                if self.sent.get(key, 0) != p.value:
                    w.u8(proto.REC_IN).u8(p.cls).u16(p.idx).i32(p.value)
                    self.sent[key] = p.value
        for idx, data in self.stream_tx:
            for i in range(0, len(data), 0xFFFF):
                w.u8(proto.REC_STREAM_IN).u16(idx).data(data[i:i + 0xFFFF])
        self.stream_tx.clear()
        for idx in self.events_tx:
            w.u8(proto.REC_EVENT_IN).u16(idx)
        self.events_tx.clear()
        return bytes(w.b)

    def exchange(self, until_ns: int, extra: bytes = b"", quantum_ns: int = 0) -> int:
        """Returns the boundary reached (< until_ns: a long run stopped on an output)."""
        self.sim._run_from = self.sim.now_ns
        done = self.inst.run(until_ns, self.records() + extra, self.sim.now_ns, quantum_ns)
        self.apply(done)
        return done.end if quantum_ns else until_ns

    def _outputs_cleared(self):
        for p in self.ports.values():
            if p.spec.dir != "in" and p.type in ("bit", "value") and p.value != 0 and (p.cls, p.idx) not in self.sent:
                p.value = 0
                p.history.append((self.sim.now_ns, 0))

    def apply(self, done: proto.Done):
        was_powered = self.powered
        for rec in done.records:
            kind = rec[0]
            if kind == "out":
                _, cls, idx, v, t = rec
                p = self.port(cls, idx)
                p.value = v
                p.history.append((t, v))
                self.sim.trace.append((t, self.name, p.name, v))
                self._notify(p, v)
            elif kind == "stream":
                _, idx, t, data = rec
                p = self.port(proto.CLASSES["UART"], idx)
                p.rx += data
                self.sim.trace.append((t, self.name, p.name, data))
                self._notify(p, data)
            elif kind == "event":
                _, idx, t = rec
                p = self.port(proto.CLASSES["EVENT"], idx)
                self.sim.trace.append((t, self.name, p.name, None))
                self._notify(p, None)
            elif kind == "block":
                _, idx, size, name = rec
                p = self.port(proto.CLASSES["BLOCK"], idx)
                if p.mm is None:
                    p.mm = mmap.mmap(-1, size, tagname=name)
            elif kind == "log":
                _, t, level, text = rec
                self.logs.append((t, level, text))
                if level in ("warning", "error"):
                    print(f"[{t / 1e9:.6f} {self.name}] {level}: {text}", file=sys.stderr)
            elif kind == "reset":
                _, cause, t, _base = rec
                self.resets.append((t, cause))
                self.sim.trace.append((t, self.name, "RESET", cause))
                self._outputs_cleared()
                for m in self.models:
                    m.on_reset(cause)
            elif kind == "mem":
                _, mid, status, data = rec
                self.mem_replies[mid] = (status, data)
        self.powered = done.powered
        self.halted = done.halted
        if was_powered and not self.powered:
            self._outputs_cleared()
            self.sim.trace.append((done.now, self.name, "POWER", 0))
        if was_powered != self.powered:
            for m in self.models:
                m.on_power(self.powered)

    def _notify(self, p: Port, v):
        for model, attr in p.listeners:
            fn = getattr(model, f"on_{attr}", None)
            if fn is None and p.type == "stream":
                fn = getattr(model, "on_rx", None)
            if fn is not None:
                fn() if p.type == "event" else fn(v)

    def on_xfer(self, cls: int, idx: int, t: int, tx: bytes) -> tuple[bytes, int]:
        # models see the start of the quantum of the transaction, as in fixed quantum stepping
        sim = self.sim
        if t > sim._run_from:
            sim.now_ns = sim._run_from + (t - sim._run_from) // sim.quantum_ns * sim.quantum_ns
        p = self.port(cls, idx)
        rx = None
        for model, attr in p.listeners:
            fn = getattr(model, f"on_{attr}", None) or getattr(model, "on_xfer", None)
            if fn is not None:
                rx = fn(tx)
                break
        if rx is None and p.responder is not None:
            rx = p.responder(tx)
        if rx is None:
            rx = bytes(len(tx))
        cost = p.spec.cost_ns
        if isinstance(rx, tuple):
            rx, cost = rx
        return bytes(rx), int(cost)

    def power_check(self):
        pw = self.board.power
        if pw.mode != "latch":
            return
        btn = self.ports[pw.button].value != 0
        hold = self.ports[pw.hold].value != 0
        if not self.powered:
            if btn:
                self.request_power(True)
            self._latch_low_since = None
        elif btn or hold:
            self._latch_low_since = None
        elif self._latch_low_since is None:
            self._latch_low_since = self.sim.now_ns
        elif self.sim.now_ns - self._latch_low_since >= pw.hold_ns:
            self.request_power(False)
            self._latch_low_since = None

    def request_power(self, on: bool):
        self.control.append(bytes(proto.Writer().u8(proto.REC_POWER).u8(1 if on else 0).b))
        self.powered = on  # host view, confirmed by the next DONE

    # -- memory ---------------------------------------------------------
    def mem(self, rec: proto.Writer, mid: int) -> tuple[int, bytes]:
        self.exchange(self.sim.now_ns, bytes(rec.b))  # zero time: between two quanta
        return self.mem_replies.pop(mid)


class Sim:
    """One firmware (board.yaml). sim["PORT"], sim.var("expr"), sim.model("Name"), sim.run(s=1)."""

    def __init__(self, board: str | Path, *, toolchain: str | None = None, work_dir: str | Path | None = None,
                 connect: int | None = None, timeout_s: float = 10.0):
        self.board = board_mod.load(board)
        self.toolchain_name = toolchain or os.environ.get("E2SIM_TOOLCHAIN") or self.board.toolchain
        self.work_dir = Path(work_dir) if work_dir else self.board.dir / "out"
        self.connect = connect
        self.timeout_s = timeout_s
        self.now_ns = 0
        self.quantum_ns = self.board.quantum_ns
        self.trace: list[tuple] = []
        self._actions: list[tuple[int, int, Callable]] = []
        self._seq = 0
        self._periodic: list[list] = []   # [next_ns, period_ns, fn]
        self._run_from = 0
        self.max_run_ns = 1_000_000_000   # longest run without host round trip (run())
        self.instances: list[InstanceState] = [InstanceState(self, self.board.name, self.board)]
        self.toolchain: toolchains.Toolchain | None = None
        self.started = False

    # -- life cycle -------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    def _resolve_firmware(self, st: InstanceState) -> tuple[Path, Path, str]:
        b = st.board
        reg = None
        try:
            reg = toolchains.load(start=b.dir)
        except toolchains.ToolchainError:
            if "{toolchain}" in b.firmware or self.toolchain_name:
                raise
        if reg is not None:
            self.toolchain = reg.get(self.toolchain_name, tool="e2sim")
        name = self.toolchain.name if self.toolchain else ""
        dll = (b.dir / b.firmware.format(toolchain=name)).resolve()
        runner = (b.dir / b.runner.format(toolchain=name)).resolve() if b.runner else dll.parent / "e2sim_runner.exe"
        gdb = self.toolchain.tool("gdb") if self.toolchain else "gdb"
        return dll, runner, gdb

    def start(self):
        if self.started:
            return
        for st in self.instances:
            dll, runner, gdb = self._resolve_firmware(st)
            if not dll.is_file():
                raise SimError(f"{st.name}: firmware {dll} not found (build it: make TOOLCHAIN={self.toolchain_name or ''})")
            st.symbols = Symbols(dll, gdb)
            symbolic = sorted({p.idx for p in st.board.ports.values() if isinstance(p.idx, str)})
            consts = st.symbols.constants(symbolic) if symbolic else {}
            blocks_cfg = []
            for spec in st.board.ports.values():
                cls = proto.CLASSES[spec.cls]
                idx = consts[spec.idx] if isinstance(spec.idx, str) else int(spec.idx)
                p = Port(self, st, spec, cls, idx)
                st.ports[spec.name] = p
                st.by_key[(cls, idx)] = p
                if spec.type == "block" and spec.persist:
                    path = self.work_dir / f"{st.name}.{spec.name}.nvm.bin"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    blocks_cfg.append((idx, spec.fill, str(path)))
            st.inst = Instance(st.name, dll, runner, yield_cost_ns=st.board.yield_cost_ns, blocks_cfg=blocks_cfg,
                               timeout_s=self.timeout_s, connect_port=self.connect, log_dir=self.work_dir)
            if self.toolchain and st.inst.pe.arch != self.toolchain.arch:
                raise SimError(f"{dll.name} is {st.inst.pe.arch}, toolchain {self.toolchain.name} is {self.toolchain.arch}")
            st.inst.xfer_handler = st.on_xfer
            self._load_models(st)
            st.inst.start()
        self.started = True
        for st in self.instances:
            for m in st.models:
                m.setup()
            if st.board.power.mode == "auto":
                st.request_power(True)
            st.power_check()
            st.exchange(0)

    def _load_models(self, st: InstanceState):
        if str(st.board.dir) not in sys.path:
            sys.path.insert(0, str(st.board.dir))
        for ms in st.board.models:
            mod_name, _, cls_name = ms.cls.rpartition(".")
            try:
                cls = getattr(importlib.import_module(mod_name), cls_name)
            except (ImportError, AttributeError) as e:
                raise SimError(f"{st.board.file}: model {ms.cls}: {e}") from None
            ports = {attr: st.ports[pname] for attr, pname in ms.ports.items()}
            model = cls(self, st.name, ms.name, ports, ms.params)
            for attr, p in ports.items():
                p.listeners.append((model, attr))
            for fn, period in model._periodic:
                self._periodic.append([period, period, fn])
            st.models.append(model)

    def stop(self):
        for st in self.instances:
            if st.inst is not None:
                st.inst.stop()
            for p in st.ports.values():
                if p.mm is not None:
                    p.mm.close()
                    p.mm = None
        self.started = False

    # -- time -------------------------------------------------------------
    @property
    def now(self) -> float:
        return self.now_ns / 1e9

    def at(self, t_ns: int, fn: Callable):
        """Run fn at the first quantum boundary >= t_ns."""
        self._seq += 1
        self._actions.append((t_ns, self._seq, fn))
        self._actions.sort()

    def step(self):
        """One quantum."""
        self._advance(self.now_ns + self.quantum_ns, long_run=False)

    def _next_host_event(self, limit: int) -> int:
        t = limit
        if self._actions:
            t = min(t, self._actions[0][0])
        for task in self._periodic:
            t = min(t, task[0])
        for st in self.instances:
            if st._latch_low_since is not None:
                t = min(t, st._latch_low_since + st.board.power.hold_ns)
        q = self.quantum_ns
        t = self.now_ns + max(q, -(-(t - self.now_ns) // q) * q)  # next boundary >= t
        return min(t, max(limit, self.now_ns + q))

    def _advance(self, until: int, long_run: bool):
        if not self.started:
            self.start()
        if long_run and len(self.instances) == 1:
            until = self._next_host_event(until)
            until = self.instances[0].exchange(until, quantum_ns=self.quantum_ns)
        else:
            for st in self.instances:
                st.exchange(until)
        self.now_ns = until
        while self._actions and self._actions[0][0] <= self.now_ns:
            self._actions.pop(0)[2]()
        for task in self._periodic:
            while task[0] <= self.now_ns:
                task[0] += task[1]
                task[2]()
        for st in self.instances:
            st.power_check()

    def run(self, s: float = 0, ms: float = 0, us: float = 0, fixed: bool = False):
        """Run for a duration. Several quanta per host round trip, stopped on any firmware output and at
        every host event: same result as quantum by quantum (fixed=True), faster."""
        end = self.now_ns + _ns(s, ms, us)
        while self.now_ns < end:
            if fixed:
                self.step()
            else:
                self._advance(min(end, self.now_ns + self.max_run_ns), long_run=True)

    def run_until(self, cond: Callable[[], bool], timeout_s: float = 10.0, desc: str = "") -> float:
        """Run until cond() is true; returns the virtual time spent (s); SimTimeout after timeout_s."""
        start = self.now_ns
        end = start + _ns(timeout_s)
        while not cond():
            if self.now_ns >= end:
                raise SimTimeout(f"condition {desc or getattr(cond, '__name__', '')} not met in {timeout_s} s "
                                 f"(t = {self.now:.6f} s)")
            self.step()
        return (self.now_ns - start) / 1e9

    def run_realtime(self, speed: float = 1.0, duration_s: float | None = None):
        wall0, virt0 = time.perf_counter(), self.now_ns
        while duration_s is None or self.now_ns - virt0 < _ns(duration_s):
            self.step()
            ahead = (self.now_ns - virt0) / 1e9 / speed - (time.perf_counter() - wall0)
            if ahead > 0.002:
                time.sleep(ahead)

    # -- access -------------------------------------------------------------
    def _single(self) -> InstanceState:
        return self.instances[0]

    def __getitem__(self, name: str) -> Port:
        if not self.started:
            self.start()
        st = self._single()
        try:
            return st.ports[name]
        except KeyError:
            raise KeyError(f"port {name} unknown ({', '.join(st.ports)})") from None

    def model(self, name: str) -> Model:
        if not self.started:
            self.start()
        for st in self.instances:
            for m in st.models:
                if m.name == name:
                    return m
        raise KeyError(f"model {name} unknown")

    @property
    def powered(self) -> bool:
        return self._single().powered

    @property
    def resets(self) -> list[tuple[int, str]]:
        return self._single().resets

    @property
    def logs(self):
        return self._single().logs

    def power_on(self):
        self._single().request_power(True)

    def power_off(self):
        self._single().request_power(False)

    def reset(self, cause: str = "host"):
        self._single().control.append(bytes(proto.Writer().u8(proto.REC_RESET_IN).u8(proto.RESET_CODES[cause]).b))

    # -- firmware variables (spec §7.2) -------------------------------------
    def var(self, expr: str) -> Any:
        st = self._single()
        if not self.started:
            self.start()
        info = st.symbols.var(expr)
        mid = st.inst.next_mem_id()
        status, data = st.mem(proto.Writer().u8(proto.REC_MEM_READ).u32(mid).u64(st.inst.relocate(info.addr))
                              .u32(info.size), mid)
        if status != proto.MEM_OK:
            raise SimError(f"{expr}: address refused by the firmware process")
        return _decode(info, data)

    def set_var(self, expr: str, value: Any):
        st = self._single()
        info = st.symbols.var(expr)
        data = _encode(info, value)
        mid = st.inst.next_mem_id()
        status, _ = st.mem(proto.Writer().u8(proto.REC_MEM_WRITE).u32(mid).u64(st.inst.relocate(info.addr))
                           .data(data), mid)
        if status != proto.MEM_OK:
            raise SimError(f"{expr}: address refused by the firmware process")

    def trace_digest(self) -> str:
        """Hash of every output, stream, reset and power event: equal runs give equal digests."""
        return hashlib.sha256(repr(self.trace).encode()).hexdigest()


def _decode(info, data: bytes) -> Any:
    if info.kind == "float":
        return struct.unpack("<f" if info.size == 4 else "<d", data)[0]
    if info.kind in ("int", "enum", "bool", "ptr"):
        v = int.from_bytes(data, "little", signed=info.signed)
        return bool(v) if info.kind == "bool" else v
    return data


def _encode(info, value: Any) -> bytes:
    if info.kind == "float":
        return struct.pack("<f" if info.size == 4 else "<d", float(value))
    if info.kind in ("int", "enum", "bool", "ptr"):
        return int(value).to_bytes(info.size, "little", signed=info.signed)
    data = bytes(value)
    if len(data) != info.size:
        raise SimError(f"{info.expr}: {info.size} bytes expected")
    return data
