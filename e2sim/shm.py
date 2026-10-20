"""Shared memory transport host <-> runner (Windows): one view and one event per direction (spec §4.3).

The exchange alternates strictly (RUN / XFER_REQ / XFER_REPLY / DONE): one message at a time in each view.
Same interface as proto.Link. The runner opens it after CONFIG (TCP stays for HELLO / CONFIG).
"""

from __future__ import annotations

import ctypes
import itertools
import mmap
import os
import struct
from ctypes import wintypes

from . import proto

SIZE = 16 << 20  # WIRE_SHM_SIZE of e2sim_wire.h
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k32.SetEvent.argtypes = [wintypes.HANDLE]
_k32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
_k32.WaitForMultipleObjects.restype = wintypes.DWORD
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_counter = itertools.count()
INFINITE = 0xFFFFFFFF


class ShmLink:
    def __init__(self, timeout_s: float | None):
        self.name = f"Local\\e2sim_ipc_{os.getpid()}_{next(_counter)}"
        self.mm = mmap.mmap(-1, 2 * SIZE, tagname=self.name + "_map")
        self.h2r = _k32.CreateEventW(None, False, False, self.name + "_h2r")
        self.r2h = _k32.CreateEventW(None, False, False, self.name + "_r2h")
        if not self.h2r or not self.r2h:
            raise proto.LinkError(f"CreateEvent failed ({ctypes.get_last_error()})")
        self.timeout_ms = INFINITE if timeout_s is None else int(timeout_s * 1000)
        self.process = None  # handle of the runner: its end is seen at once

    def send(self, msg_type: int, payload: bytes = b""):
        n = len(payload) + 1
        if n + 4 > SIZE:
            raise proto.LinkError(f"message of {n} bytes: too big for the shared memory")
        self.mm[0:5] = struct.pack("<IB", n, msg_type)
        self.mm[5:5 + len(payload)] = payload
        _k32.SetEvent(self.h2r)

    def recv(self) -> tuple[int, proto.Reader]:
        handles = (wintypes.HANDLE * 2)(self.r2h, self.process or self.r2h)
        r = _k32.WaitForMultipleObjects(2 if self.process else 1, handles, False, self.timeout_ms)
        if r == 0x102:  # WAIT_TIMEOUT
            raise proto.LinkError("no answer from the firmware (loop without yield point, or crash ?)")
        if r != 0:
            raise proto.LinkError("the runner process ended")
        n, msg_type = struct.unpack_from("<IB", self.mm, SIZE)
        return msg_type, proto.Reader(self.mm[SIZE + 5:SIZE + 4 + n])

    def close(self):
        if self.mm is not None:
            self.mm.close()
            self.mm = None
            _k32.CloseHandle(self.h2r)
            _k32.CloseHandle(self.r2h)
