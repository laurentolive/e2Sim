"""Host <-> runner wire protocol (must match target/src/e2sim_wire.h)."""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field

WIRE_VERSION = 2

MSG_HELLO = 0x01
MSG_DONE = 0x02
MSG_XFER_REQ = 0x03
MSG_CONFIG = 0x81
MSG_RUN = 0x82
MSG_XFER_REPLY = 0x83
MSG_QUIT = 0x84

REC_END = 0x00
REC_OUT = 0x10
REC_STREAM = 0x11
REC_EVENT = 0x12
REC_BLOCK = 0x13
REC_LOG = 0x14
REC_RESET = 0x15
REC_MEM = 0x16
REC_SAMPLE_ACK = 0x17
REC_SAMPLE = 0x18

REC_IN = 0x20
REC_STREAM_IN = 0x21
REC_EVENT_IN = 0x22
REC_RESET_IN = 0x23
REC_POWER = 0x24
REC_MEM_READ = 0x25
REC_MEM_WRITE = 0x26
REC_SAMPLE_CFG = 0x27

MEM_OK = 0

# port classes (e2sim_class_t)
CLASSES = {"GPIO": 1, "ADC": 2, "PWM": 3, "CAPTURE": 4, "VALUE": 5, "UART": 6, "SPI": 7, "I2C": 8, "BLOCK": 9,
           "EVENT": 10}
CLASS_NAMES = {v: k for k, v in CLASSES.items()}

RESET_CAUSES = {0: "power_on", 1: "soft", 2: "wdt", 3: "host"}
RESET_CODES = {v: k for k, v in RESET_CAUSES.items()}
LOG_LEVELS = {0: "debug", 1: "info", 2: "warning", 3: "error"}


class LinkError(Exception):
    pass


class Writer:
    def __init__(self):
        self.b = bytearray()

    def u8(self, v): self.b += struct.pack("<B", v); return self
    def u16(self, v): self.b += struct.pack("<H", v); return self
    def u32(self, v): self.b += struct.pack("<I", v & 0xFFFFFFFF); return self
    def i32(self, v): self.b += struct.pack("<i", v); return self
    def u64(self, v): self.b += struct.pack("<Q", v); return self

    def data(self, d: bytes):
        self.u16(len(d))
        self.b += d
        return self

    def str(self, s: str):
        return self.data(s.encode("utf-8"))


class Reader:
    def __init__(self, b: bytes):
        self.b = b
        self.pos = 0

    def _take(self, fmt):
        n = struct.calcsize(fmt)
        if self.pos + n > len(self.b):
            raise LinkError("truncated message")
        v = struct.unpack_from(fmt, self.b, self.pos)[0]
        self.pos += n
        return v

    def u8(self): return self._take("<B")
    def u16(self): return self._take("<H")
    def u32(self): return self._take("<I")
    def i32(self): return self._take("<i")
    def u64(self): return self._take("<Q")

    def data(self) -> bytes:
        n = self.u16()
        if self.pos + n > len(self.b):
            raise LinkError("truncated message")
        d = self.b[self.pos:self.pos + n]
        self.pos += n
        return bytes(d)

    def str(self) -> str:
        return self.data().decode("utf-8", "replace")


class Link:
    """Framed messages on a connected socket."""

    def __init__(self, sock: socket.socket, timeout_s: float | None):
        self.sock = sock
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(timeout_s)

    def send(self, msg_type: int, payload: bytes = b""):
        self.sock.sendall(struct.pack("<IB", len(payload) + 1, msg_type) + payload)

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except socket.timeout:
                raise LinkError("no answer from the firmware (loop without yield point, or crash ?)") from None
            except OSError as e:
                raise LinkError(f"link lost: {e}") from None
            if not chunk:
                raise LinkError("link closed by the firmware process")
            buf += chunk
        return bytes(buf)

    def recv(self) -> tuple[int, Reader]:
        length, msg_type = struct.unpack("<IB", self._recv_exact(5))
        return msg_type, Reader(self._recv_exact(length - 1))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


@dataclass
class Done:
    """Decoded MSG_DONE: records in firmware order (order matters: a reset clears the outputs)."""
    now: int
    end: int          # quantum boundary reached
    powered: bool
    halted: bool
    records: list = field(default_factory=list)
    # ("out", cls, idx, value, t) ("stream", idx, t, bytes) ("event", idx, t) ("block", idx, size, name)
    # ("log", t, level, text) ("reset", cause, t, base) ("mem", id, status, bytes)


def decode_done(r: Reader) -> Done:
    d = Done(now=r.u64(), end=r.u64(), powered=bool(r.u8()), halted=bool(r.u8()))
    add = d.records.append
    while True:
        rec = r.u8()
        if rec == REC_END:
            return d
        if rec == REC_OUT:
            add(("out", r.u8(), r.u16(), r.i32(), r.u64()))
        elif rec == REC_STREAM:
            add(("stream", r.u16(), r.u64(), r.data()))
        elif rec == REC_EVENT:
            add(("event", r.u16(), r.u64()))
        elif rec == REC_BLOCK:
            add(("block", r.u16(), r.u32(), r.str()))
        elif rec == REC_LOG:
            add(("log", r.u64(), LOG_LEVELS.get(r.u8(), "?"), r.str()))
        elif rec == REC_RESET:
            add(("reset", RESET_CAUSES.get(r.u8(), "?"), r.u64(), r.u64()))
        elif rec == REC_MEM:
            add(("mem", r.u32(), r.u8(), r.data()))
        elif rec == REC_SAMPLE_ACK:
            add(("sample_ack", r.u8(), r.u16()))
        elif rec == REC_SAMPLE:
            add(("sample", r.u64(), r.data()))
        else:
            raise LinkError(f"unknown record 0x{rec:02x}")
