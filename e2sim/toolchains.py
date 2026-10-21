"""Toolchains of e2Sim (e2sim_toolchains.yaml, spec §10.1): own configuration file, independent of the other tools."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ENV_VAR = "E2SIM_TOOLCHAINS"
FILE_NAME = "e2sim_toolchains.yaml"
USER_DIR = Path.home() / ".e2sim"


class ToolchainError(Exception):
    pass


@dataclass
class Toolchain:
    name: str
    arch: str
    prefix: str
    path: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # added to every compile / link (e.g. -m32)

    def tool(self, name: str) -> str:
        """Full path of a tool of the chain (gcc, objcopy, gdb...)."""
        p = self.prefix + name
        if os.name == "nt" and not p.lower().endswith(".exe"):
            p += ".exe"
        return p

    @property
    def ptr_size(self) -> int:
        return 8 if self.arch in ("x86_64", "amd64", "aarch64") else 4


@dataclass
class Registry:
    file: Path
    python: str | None
    toolchains: dict[str, Toolchain]
    default: str | None

    def get(self, name: str | None = None) -> Toolchain:
        """Toolchain by name, else the default of the file."""
        name = name or self.default
        if not name:
            raise ToolchainError(f"{self.file}: no toolchain given and no 'default:'")
        try:
            return self.toolchains[name]
        except KeyError:
            known = ", ".join(sorted(self.toolchains)) or "none"
            raise ToolchainError(f"{self.file}: unknown toolchain '{name}' (known: {known})") from None

    def by_arch(self, arch: str) -> Toolchain:
        """A toolchain of the given architecture, the default first."""
        for t in sorted(self.toolchains.values(), key=lambda t: t.name != self.default):
            if t.arch == arch:
                return t
        raise ToolchainError(f"{self.file}: no toolchain for arch {arch}")


def find_file(start: Path | None = None) -> Path:
    """E2SIM_TOOLCHAINS, then e2sim_toolchains.yaml in start and its parents, then ~/.e2sim/."""
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env)
        if not p.is_file():
            raise ToolchainError(f"{ENV_VAR}={env}: file not found")
        return p
    d = (start or Path.cwd()).resolve()
    for parent in (d, *d.parents):
        p = parent / FILE_NAME
        if p.is_file():
            return p
    p = USER_DIR / FILE_NAME
    if p.is_file():
        return p
    raise ToolchainError(
        f"{FILE_NAME} not found: set {ENV_VAR}, or create it in the project or in {USER_DIR} "
        f"(see {FILE_NAME}.example)"
    )


def load(file: Path | None = None, start: Path | None = None) -> Registry:
    file = file or find_file(start)
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ToolchainError(f"{file}: {e}") from None
    chains = {}
    for name, d in (data.get("toolchains") or {}).items():
        if "prefix" not in d:
            raise ToolchainError(f"{file}: toolchain '{name}': 'prefix' missing")
        chains[name] = Toolchain(name=name, arch=d.get("arch", "x86_64"), prefix=str(d["prefix"]),
                                 path=[str(p) for p in d.get("path") or []],
                                 flags=[str(f) for f in d.get("flags") or []])
    return Registry(file=file, python=data.get("python"), toolchains=chains, default=data.get("default"))


def make_fragment(tc: Toolchain, registry: Registry) -> str:
    """Make fragment included by the makefiles."""
    lines = [
        f"# generated from {registry.file.as_posix()} - do not edit",
        f"E2SIM_TC := {tc.name}",
        f"E2SIM_ARCH := {tc.arch}",
        f"E2SIM_PTR_SIZE := {tc.ptr_size}",
        f"CC := {tc.tool('gcc')}",
        f"CXX := {tc.tool('g++')}",
        f"AR := {tc.tool('ar')}",
        f"OBJCOPY := {tc.tool('objcopy')}",
        f"GDB := {tc.tool('gdb')}",
        f"E2SIM_ARCH_FLAGS := {' '.join(tc.flags)}",
        # absolute: the toolchain PATH below may hide the system Python
        f"E2SIM_PY := {Path(registry.python or sys.executable).as_posix()}",
    ]
    if tc.path:
        sep = ";" if os.name == "nt" else ":"
        lines.append(f"export PATH := {sep.join(tc.path)}{sep}$(PATH)")
    return "\n".join(lines) + "\n"
