"""eScope protocol V3 endpoint of one instance, in the host (spec §9.1).

eScope sees a V3 target on TCP: link addresses (symbols of the DLL) relocated by the host, 4 or 8 bytes
addresses as the build (ADDR64_FLAG), one frame per sampling period of virtual time, no frame lost.
Nothing of eScope in the firmware: the samples are taken by the runner (REC_SAMPLE_CFG).
"""

from __future__ import annotations

from . import proto
from .tcp import TcpServer

READ_FLAG, WRITE_FLAG, ADDR64_FLAG = 0x40, 0x20, 0x10
CMD_DEINIT, CMD_CLEAR = 0x01, 0x02
CMD_READ_PERIODIC, CMD_READ_APERIODIC, CMD_WRITE_APERIODIC = 0x43, 0x44, 0x25
ERR_TXOVF, ERR_CFGOVF, ERR_ADDR, ERR_ADDRSIZE = 0x86, 0x87, 0x88, 0x8A
MAX_PAYLOAD = 255


class EscopeEndpoint:
    def __init__(self, inst, port: int = 0, period_ns: int = 1_000_000):
        self.inst = inst  # InstanceState
        self.period_ns = period_ns
        self.server = TcpServer(port, f"escope-{inst.name}")
        self.port = self.server.port
        self.addr_size = 4
        self._rx = bytearray()
        self.periodic: list[tuple[int, int]] = []  # (wire address, size)
        self.oneshot: list[bytes] = []             # data of the one shot reads, in the next frame
        self.error: tuple[int, bytes] | None = None
        self._error_next = 0
        self._cfg_dirty = False
        self._cnt = 0
        self.frames = 0

    # -- called by the simulation ------------------------------------------
    def records(self) -> bytes:
        """Inputs of the next RUN: new sampling configuration."""
        if not self._cfg_dirty:
            return b""
        self._cfg_dirty = False
        w = proto.Writer().u8(proto.REC_SAMPLE_CFG).u64(self.period_ns if self.periodic else 0).u16(len(self.periodic))
        for addr, size in self.periodic:
            w.u64(self.inst.inst.relocate(addr)).u16(size)
        return bytes(w.b)

    def on_sample_ack(self, status: int, index: int):
        if status != proto.MEM_OK and index < len(self.periodic):
            addr, size = self.periodic.pop(index)
            self._set_error(ERR_ADDR, self._addr_bytes(addr) + bytes([size]))

    def on_sample(self, t: int, data: bytes):
        if self.error is None:
            extra = b"".join(self.oneshot)
            self.oneshot.clear()
            self._frame(proto_cmd=CMD_READ_PERIODIC, payload=data + extra)

    def process(self):
        """At a quantum boundary: commands received from eScope, error frames, lone one shot reads."""
        data, connections = self.server.take()
        if connections:
            self._reset()
        self._rx += data
        self._parse()
        if self.error is not None:
            now = self.inst.sim.now_ns
            n = 0
            while self._error_next <= now and n < 100:
                self._frame(self.error[0], self.error[1])
                self._error_next += self.period_ns
                n += 1
            if self._error_next <= now:
                self._error_next = now + self.period_ns
        elif self.oneshot and not self.periodic:
            payload = b"".join(self.oneshot)
            self.oneshot.clear()
            self._frame(CMD_READ_PERIODIC, payload)

    def close(self):
        self.server.close()

    # -- protocol ------------------------------------------------------------
    def _reset(self):
        self._rx.clear()
        self.periodic.clear()
        self.oneshot.clear()
        self.error = None
        self._cfg_dirty = True

    def _addr_bytes(self, addr: int) -> bytes:
        return addr.to_bytes(self.addr_size, "little")

    def _set_error(self, code: int, payload: bytes = b""):
        self.error = (code, payload)
        self._error_next = self.inst.sim.now_ns
        self._rx.clear()

    def _frame(self, proto_cmd: int, payload: bytes):
        frame = bytes([0x55, self._cnt & 0xFF, len(payload), proto_cmd]) + payload + b"\xAA"
        self._cnt += 1
        self.frames += 1
        self.server.send(frame)

    def _parse(self):
        cmd_size = 2 + self.addr_size
        while self._rx:
            cmd = self._rx[0]
            if self.error is not None and cmd not in (CMD_CLEAR, CMD_DEINIT):
                self._rx.clear()  # in error until CMD_CLEAR, as the target
                return
            if cmd & (READ_FLAG | WRITE_FLAG):
                if bool(cmd & ADDR64_FLAG) != (self.addr_size == 8):
                    self._set_error(ERR_ADDRSIZE, bytes([self.addr_size]))
                    return
                cmd &= ~ADDR64_FLAG
            if cmd == CMD_DEINIT:
                self._reset()
                return
            if cmd == CMD_CLEAR:  # new configuration: what came with it is dropped
                self._reset()
                return
            if cmd in (CMD_READ_PERIODIC, CMD_READ_APERIODIC, CMD_WRITE_APERIODIC):
                if len(self._rx) < cmd_size:
                    return
                size = self._rx[1]
                addr = int.from_bytes(self._rx[2:cmd_size], "little")
                if cmd == CMD_WRITE_APERIODIC:
                    if len(self._rx) < cmd_size + size:
                        return
                    data = bytes(self._rx[cmd_size:cmd_size + size])
                    del self._rx[:cmd_size + size]
                    if not self._mem_write(addr, data):
                        self._set_error(ERR_ADDR, self._addr_bytes(addr) + bytes([size]))
                    continue
                del self._rx[:cmd_size]
                if sum(s for _, s in self.periodic) + size > MAX_PAYLOAD:
                    self._set_error(ERR_TXOVF)
                    return
                if cmd == CMD_READ_PERIODIC:
                    self.periodic.append((addr, size))
                    self._cfg_dirty = True
                else:
                    data = self._mem_read(addr, size)
                    if data is None:
                        self._set_error(ERR_ADDR, self._addr_bytes(addr) + bytes([size]))
                    else:
                        self.oneshot.append(data)
                continue
            self._rx.clear()  # NOP or unknown: resynchronise on the next reception

    def _mem_read(self, addr: int, size: int) -> bytes | None:
        st = self.inst
        mid = st.inst.next_mem_id()
        status, data = st.mem(proto.Writer().u8(proto.REC_MEM_READ).u32(mid).u64(st.inst.relocate(addr)).u32(size), mid)
        return data if status == proto.MEM_OK else None

    def _mem_write(self, addr: int, data: bytes) -> bool:
        st = self.inst
        mid = st.inst.next_mem_id()
        status, _ = st.mem(proto.Writer().u8(proto.REC_MEM_WRITE).u32(mid).u64(st.inst.relocate(addr)).data(data), mid)
        return status == proto.MEM_OK


def unpack_frames(buf: bytearray) -> list[tuple[int, int, bytes]]:
    """Client side helper (tests): complete frames (flow, cmd, payload) removed from buf."""
    out = []
    while len(buf) >= 5:
        if buf[0] != 0x55:
            del buf[0]
            continue
        n = buf[2]
        if len(buf) < 5 + n:
            break
        if buf[4 + n] != 0xAA:
            del buf[0]
            continue
        out.append((buf[1], buf[3], bytes(buf[4:4 + n])))
        del buf[:5 + n]
    return out


def command(cmd: int, addr: int, size: int, addr_size: int, data: bytes = b"") -> bytes:
    """Client side helper (tests): one V3 command."""
    if addr_size == 8 and cmd & (READ_FLAG | WRITE_FLAG):
        cmd |= ADDR64_FLAG
    return bytes([cmd, size]) + addr.to_bytes(addr_size, "little") + data

