"""Firmware binary: architecture and link base of the firmware library (PE .dll on Windows, ELF .so on Linux)."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

PE_MACHINES = {0x14C: "i686", 0x8664: "x86_64", 0xAA64: "aarch64"}
ELF_MACHINES = {3: "i686", 62: "x86_64", 183: "aarch64"}

LIB_EXT = ".dll" if os.name == "nt" else ".so"
EXE_EXT = ".exe" if os.name == "nt" else ""


@dataclass
class PeInfo:
    arch: str
    image_base: int  # link address of the image: PE ImageBase, lowest PT_LOAD address of an ELF
    ptr_size: int


def firmware_path(path: Path) -> Path:
    """The firmware library of this platform: board.yaml may name the .dll, a .so is used on Linux."""
    path = Path(path)
    if not path.is_file() and path.suffix in (".dll", ".so"):
        other = path.with_suffix(LIB_EXT)
        if other.is_file():
            return other
    return path


def read(path: str | Path) -> PeInfo:
    data = Path(path).read_bytes()[:65536]
    if data[:2] == b"MZ":
        return _pe(path, data)
    if data[:4] == b"\x7fELF":
        return _elf(path, data)
    raise ValueError(f"{path}: neither a PE nor an ELF file")


def _pe(path, data: bytes) -> PeInfo:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path}: not a PE file")
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    opt = pe + 24
    if struct.unpack_from("<H", data, opt)[0] == 0x20B:  # PE32+
        return PeInfo(PE_MACHINES.get(machine, hex(machine)), struct.unpack_from("<Q", data, opt + 24)[0], 8)
    return PeInfo(PE_MACHINES.get(machine, hex(machine)), struct.unpack_from("<I", data, opt + 28)[0], 4)


def _elf(path, data: bytes) -> PeInfo:
    is64 = data[4] == 2
    end = "<" if data[5] == 1 else ">"
    machine = struct.unpack_from(end + "H", data, 18)[0]
    if is64:
        phoff = struct.unpack_from(end + "Q", data, 32)[0]
        phentsize, phnum = struct.unpack_from(end + "HH", data, 54)
    else:
        phoff = struct.unpack_from(end + "I", data, 28)[0]
        phentsize, phnum = struct.unpack_from(end + "HH", data, 42)
    base = None
    for i in range(phnum):
        off = phoff + i * phentsize
        if off + phentsize > len(data):
            break
        p_type = struct.unpack_from(end + "I", data, off)[0]
        if p_type != 1:  # PT_LOAD
            continue
        vaddr = struct.unpack_from(end + "Q", data, off + 16)[0] if is64 else struct.unpack_from(end + "I", data, off + 8)[0]
        base = vaddr if base is None else min(base, vaddr)
    return PeInfo(ELF_MACHINES.get(machine, hex(machine)), base or 0, 8 if is64 else 4)
