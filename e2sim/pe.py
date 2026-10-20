"""Minimal PE header reader: architecture and link image base of the firmware DLL."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MACHINES = {0x14C: "i686", 0x8664: "x86_64", 0xAA64: "aarch64"}


@dataclass
class PeInfo:
    arch: str
    image_base: int
    ptr_size: int


def read(path: str | Path) -> PeInfo:
    data = Path(path).read_bytes()[:4096]
    if data[:2] != b"MZ":
        raise ValueError(f"{path}: not a PE file")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path}: not a PE file")
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20B:  # PE32+
        base = struct.unpack_from("<Q", data, opt + 24)[0]
        ptr = 8
    else:
        base = struct.unpack_from("<I", data, opt + 28)[0]
        ptr = 4
    return PeInfo(arch=MACHINES.get(machine, hex(machine)), image_base=base, ptr_size=ptr)
