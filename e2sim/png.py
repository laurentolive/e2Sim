"""Framebuffer <-> PNG without dependency (RGB 8 bits, filter 0)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def rgb565_to_rgb(data: bytes, w: int, h: int) -> bytes:
    out = bytearray(w * h * 3)
    for i in range(w * h):
        v = data[2 * i] | (data[2 * i + 1] << 8)
        r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
        out[3 * i:3 * i + 3] = bytes(((r * 527 + 23) >> 6, (g * 259 + 33) >> 6, (b * 527 + 23) >> 6))
    return bytes(out)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write(path: str | Path, rgb: bytes, w: int, h: int, scale: int = 1):
    if scale > 1:
        rows = []
        for y in range(h):
            row = b"".join(rgb[3 * (y * w + x):3 * (y * w + x) + 3] * scale for x in range(w))
            rows += [row] * scale
        w, h, raw = w * scale, h * scale, rows
    else:
        raw = [rgb[3 * y * w:3 * (y + 1) * w] for y in range(h)]
    payload = b"".join(b"\0" + r for r in raw)
    png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(payload, 9)) + _chunk(b"IEND", b""))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(png)


def read(path: str | Path) -> tuple[bytes, int, int]:
    """Read an RGB 8 bits PNG (as written by write(); all filters supported)."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, color = struct.unpack(">IIBB", body[:10])
            if depth != 8 or color != 2:
                raise ValueError(f"{path}: RGB 8 bits PNG expected")
        elif kind == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    stride = w * 3
    out = bytearray()
    prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        out += line
        prev = line
    return bytes(out), w, h
