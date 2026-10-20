"""Toolchain registry shared with e2Unit (toolchains.yaml, spec §10.1)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ENV_VAR = "ESQ_TOOLCHAINS"
FILE_NAME = "toolchains.yaml"


class ToolchainError(Exception):
    pass


@dataclass
class Toolchain:
    name: str
    kind: str
    arch: str
    prefix: str
    path: list[str] = field(default_factory=list)
    python: str | None = None

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
    defaults: dict[str, str]

    def get(self, name: str | None = None, tool: str = "e2sim") -> Toolchain:
        """Toolchain by name, else the registry default of the tool."""
        if not name:
            name = self.defaults.get(tool)
            if not name:
                raise ToolchainError(f"{self.file}: no default toolchain for '{tool}' (defaults: {tool}: <name>)")
        try:
            return self.toolchains[name]
        except KeyError:
            known = ", ".join(sorted(self.toolchains)) or "none"
            raise ToolchainError(f"{self.file}: unknown toolchain '{name}' (known: {known})") from None

    def by_arch(self, arch: str, kind: str = "host") -> Toolchain:
        """First toolchain of the given architecture, the e2sim default first."""
        default = self.defaults.get("e2sim")
        candidates = sorted(self.toolchains.values(), key=lambda t: t.name != default)
        for t in candidates:
            if t.kind == kind and t.arch == arch:
                return t
        raise ToolchainError(f"{self.file}: no '{kind}' toolchain for arch {arch}")


def find_file(start: Path | None = None) -> Path:
    """ESQ_TOOLCHAINS, then toolchains.yaml in start and its parents, then ~/.esquaresoft/."""
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
    p = Path.home() / ".esquaresoft" / FILE_NAME
    if p.is_file():
        return p
    raise ToolchainError(
        f"{FILE_NAME} not found: set {ENV_VAR}, or create it in the project or in ~/.esquaresoft/ "
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
        chains[name] = Toolchain(
            name=name,
            kind=d.get("kind", "host"),
            arch=d.get("arch", "x86_64" if d.get("kind", "host") == "host" else "arm"),
            prefix=str(d["prefix"]),
            path=[str(p) for p in d.get("path") or []],
            python=d.get("python"),
        )
    return Registry(file=file, python=data.get("python"), toolchains=chains, defaults=data.get("defaults") or {})


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
        # absolute: the toolchain PATH below may hide the system Python
        f"E2SIM_PY := {Path(registry.python or sys.executable).as_posix()}",
    ]
    if tc.python:
        lines.append(f"TC_PY := {tc.python}")
    if tc.path:
        sep = ";" if os.name == "nt" else ":"
        lines.append(f"export PATH := {sep.join(tc.path)}{sep}$(PATH)")
    return "\n".join(lines) + "\n"
