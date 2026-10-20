"""Record / replay (spec §7.4).

Record: every message the host sends to the runners (RUN with its inputs, transaction answers), in order.
Replay: the same messages sent again, without models nor script: the firmware gets exactly the same inputs at
the same virtual times, so its outputs must be the same (trace digest stored at the end of the record).

File (.e2simrec): b"E2SIMREC" u32 header length, JSON header, then entries
[u8 kind][u16 instance][u32 length][payload], kind 1 RUN, 2 XFER reply, 3 block written by the host
(u16 idx, u32 offset, data), 0xFF end (payload: JSON footer).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

MAGIC = b"E2SIMREC"
VERSION = 1
KIND_RUN, KIND_XFER, KIND_BLOCK, KIND_END = 1, 2, 3, 0xFF


class RecordError(Exception):
    pass


class Recorder:
    def __init__(self, path: str | Path, header: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "wb")  # noqa: SIM115 - closed by close()
        h = json.dumps({"version": VERSION, **header}).encode()
        self.f.write(MAGIC + struct.pack("<I", len(h)) + h)

    def write(self, kind: int, instance: int, payload: bytes):
        self.f.write(struct.pack("<BHI", kind, instance, len(payload)) + payload)

    def close(self, footer: dict):
        if self.f.closed:
            return
        self.write(KIND_END, 0, json.dumps(footer).encode())
        self.f.close()


def read(path: str | Path) -> tuple[dict, list[tuple[int, int, bytes]], dict]:
    data = Path(path).read_bytes()
    if data[:8] != MAGIC:
        raise RecordError(f"{path}: not an e2Sim record")
    n = struct.unpack_from("<I", data, 8)[0]
    header = json.loads(data[12:12 + n])
    if header.get("version") != VERSION:
        raise RecordError(f"{path}: record version {header.get('version')}, expected {VERSION}")
    pos, entries, footer = 12 + n, [], {}
    while pos < len(data):
        kind, inst, length = struct.unpack_from("<BHI", data, pos)
        payload = data[pos + 7:pos + 7 + length]
        pos += 7 + length
        if kind == KIND_END:
            footer = json.loads(payload)
            break
        entries.append((kind, inst, payload))
    if not footer:
        raise RecordError(f"{path}: record not closed (simulation interrupted ?)")
    return header, entries, footer
