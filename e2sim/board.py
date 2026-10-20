"""board.yaml: ports, models, power, GUI of one firmware (spec §6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .proto import CLASSES

PORT_TYPES = ("bit", "value", "stream", "xfer", "block", "event")
DEFAULT_TYPES = {"GPIO": "bit", "ADC": "value", "PWM": "value", "CAPTURE": "value", "VALUE": "value",
                 "UART": "stream", "SPI": "xfer", "I2C": "xfer", "BLOCK": "block", "EVENT": "event"}


class BoardError(Exception):
    pass


@dataclass
class PortSpec:
    name: str
    cls: str
    idx: int | str          # str: HAL symbol resolved from the DWARF of the firmware
    type: str
    dir: str = "in"         # in / out / io
    default: int = 0
    framebuffer: dict | None = None
    size: int | None = None
    persist: bool = False
    fill: int = 0xFF
    cost_ns: int = 0
    tcp: int | None = None  # stream relayed to a local TCP server (spec §9.3)


@dataclass
class ModelSpec:
    cls: str
    name: str
    ports: dict[str, str]
    params: dict[str, Any]


@dataclass
class PowerSpec:
    mode: str = "auto"      # auto: on at start; latch: button OR hold output; manual: sim.power_on()
    button: str | None = None
    hold: str | None = None
    hold_ns: int = 10_000_000  # latch kept this long without button nor hold (MCU reset)


@dataclass
class Board:
    file: Path
    name: str
    firmware: str           # may contain {toolchain}
    runner: str | None
    toolchain: str | None
    quantum_ns: int
    yield_cost_ns: int
    reset: str
    power: PowerSpec
    ports: dict[str, PortSpec] = field(default_factory=dict)
    models: list[ModelSpec] = field(default_factory=list)
    gui: dict = field(default_factory=dict)
    escope: dict = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return self.file.parent


def _err(file, msg):
    raise BoardError(f"{file}: {msg}")


def load(path: str | Path) -> Board:
    file = Path(path).resolve()
    try:
        d = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise BoardError(f"{file}: {e}") from None
    if "firmware" not in d:
        _err(file, "'firmware' missing")

    ports = {}
    for name, p in (d.get("ports") or {}).items():
        p = p or {}
        cls = str(p.get("class", "")).upper()
        if cls not in CLASSES:
            _err(file, f"port {name}: class {cls or '?'} unknown ({', '.join(CLASSES)})")
        if "idx" not in p:
            _err(file, f"port {name}: 'idx' missing")
        typ = p.get("type", DEFAULT_TYPES[cls])
        if typ not in PORT_TYPES:
            _err(file, f"port {name}: type {typ} unknown ({', '.join(PORT_TYPES)})")
        if typ == "block" and not p.get("size") and not p.get("framebuffer"):
            _err(file, f"port {name}: block needs 'size' or 'framebuffer'")
        ports[name] = PortSpec(name=name, cls=cls, idx=p["idx"], type=typ, dir=p.get("dir", "in"),
                               default=int(p.get("default", 0)), framebuffer=p.get("framebuffer"),
                               size=p.get("size"), persist=bool(p.get("persist", False)),
                               fill=int(p.get("fill", 0xFF)), cost_ns=int(p.get("cost_ns", 0)),
                               tcp=int(p["tcp"]) if p.get("tcp") is not None else None)

    models = []
    for m in d.get("models") or []:
        if "class" not in m:
            _err(file, "model without 'class'")
        for k, port in (m.get("ports") or {}).items():
            if port not in ports:
                _err(file, f"model {m['class']}: port {port} unknown")
        models.append(ModelSpec(cls=m["class"], name=m.get("name", m["class"].rsplit(".", 1)[-1]),
                                ports=m.get("ports") or {}, params=m.get("params") or {}))

    pw = d.get("power") or {}
    power = PowerSpec(mode=pw.get("mode", "auto"), button=pw.get("button"), hold=pw.get("hold"),
                      hold_ns=round(float(pw.get("hold_ms", 10)) * 1e6))
    if power.mode not in ("auto", "latch", "manual"):
        _err(file, f"power.mode {power.mode} unknown (auto, latch, manual)")
    if power.mode == "latch":
        for k in ("button", "hold"):
            if getattr(power, k) not in ports:
                _err(file, f"power.{k}: port expected")

    reset = d.get("reset", "in_process")
    if reset != "in_process":
        _err(file, f"reset: {reset} not supported yet (in_process)")

    cpu = d.get("cpu") or {}
    return Board(file=file, name=d.get("name", file.stem), firmware=d["firmware"], runner=d.get("runner"),
                 toolchain=d.get("toolchain"), quantum_ns=round(float(d.get("quantum_ms", 1)) * 1e6),
                 yield_cost_ns=int(cpu.get("yield_cost_ns", 1000)), reset=reset, power=power, ports=ports,
                 models=models, gui=d.get("gui") or {}, escope=d.get("escope") or {})


@dataclass
class System:
    file: Path
    instances: list[tuple[str, Board]]
    links: list[tuple[tuple[str, str], tuple[str, str]]]


def load_system(path: str | Path) -> System:
    """system.yaml (several boards and their links, spec §8), or a board.yaml alone."""
    file = Path(path).resolve()
    try:
        d = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise BoardError(f"{file}: {e}") from None
    if "instances" not in d:
        b = load(file)
        return System(file=file, instances=[(b.name, b)], links=[])
    instances = []
    for name, spec in (d.get("instances") or {}).items():
        if "." in name or ":" in name:
            _err(file, f"instance {name}: '.' and ':' not allowed in a name")
        if not spec or "board" not in spec:
            _err(file, f"instance {name}: 'board' missing")
        instances.append((name, load(file.parent / spec["board"])))
    if not instances:
        _err(file, "no instance")
    boards = dict(instances)
    links = []
    for link in d.get("links") or []:
        if len(link) != 2:
            _err(file, f"link {link}: [instance.PORT, instance.PORT] expected")
        ends = []
        for end in link:
            inst, _, port = str(end).partition(".")
            if inst not in boards or port not in boards[inst].ports:
                _err(file, f"link {link}: {end} unknown")
            ends.append((inst, port))
        links.append(tuple(ends))
    return System(file=file, instances=instances, links=links)
