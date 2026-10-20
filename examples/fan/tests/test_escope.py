"""eScope endpoint of the host (spec §9.1) and TCP relay of a stream (§9.3), seen by a V3 client."""

import socket
import time

import e2sim
from e2sim.escope import (CMD_CLEAR, CMD_READ_APERIODIC, CMD_READ_PERIODIC, CMD_WRITE_APERIODIC, ERR_ADDR,
                          ERR_ADDRSIZE, command, unpack_frames)
from fan_helpers import boot, fan_on, key


class Client:
    """Minimal eScope V3 client."""

    def __init__(self, sim, port):
        self.sim = sim
        self.sock = socket.create_connection(("127.0.0.1", port))
        self.sock.settimeout(0.05)
        self.buf = bytearray()
        sim.run(ms=2)  # connection seen at a quantum boundary

    def send(self, data: bytes):
        self.sock.sendall(data)
        time.sleep(0.02)  # let the server thread receive it
        self.sim.step()

    def frames(self):
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            self.buf += chunk
        return unpack_frames(self.buf)

    def close(self):
        self.sock.close()


def addr(sim, expr):
    info = sim.instance().symbols.var(expr)
    return info.addr, info.size


@e2sim.requirement("E2SIM-ESCOPE-01")
def test_t14_escope_periodic_reads(sim):
    boot(sim)
    fan_on(sim)
    st = sim.instance()
    asz = st.escope.addr_size
    assert asz == st.inst.ptr_size
    c = Client(sim, st.escope.port)
    c.send(bytes([CMD_CLEAR]))
    a_ms, s_ms = addr(sim, "app_ms")
    a_lvl, _ = addr(sim, "app.speedLevel")
    c.send(command(CMD_READ_PERIODIC, a_ms, s_ms, asz) + command(CMD_READ_PERIODIC, a_lvl, 1, asz))
    c.frames()
    sim.run(ms=300)
    key(sim, "BTN_PLUS")
    sim.run(ms=300)
    frames = c.frames()
    assert len(frames) >= 700
    flows = [f[0] for f in frames]
    assert all((b - a) & 0xFF == 1 for a, b in zip(flows, flows[1:])), "no frame lost"
    ms = [int.from_bytes(f[2][:s_ms], "little") for f in frames]
    # time axis = frame index x sampling period: the 1 ms tick advances by one between two frames
    assert all(b - a == 1 for a, b in zip(ms, ms[1:]))
    levels = [f[2][s_ms] for f in frames]
    assert levels[0] == 1 and levels[-1] == 2
    c.close()


@e2sim.requirement("E2SIM-ESCOPE-02")
def test_t14_escope_write_oneshot_errors(sim):
    boot(sim)
    st = sim.instance()
    asz = st.escope.addr_size
    c = Client(sim, st.escope.port)
    a_lvl, _ = addr(sim, "settings.speedLevel")
    a_bat, _ = addr(sim, "app.batPercent")

    c.send(command(CMD_WRITE_APERIODIC, a_lvl, 1, asz, bytes([4])))
    assert sim.var("settings.speedLevel") == 4

    c.send(command(CMD_READ_APERIODIC, a_bat, 1, asz))
    sim.run(ms=2)
    frames = c.frames()
    assert frames and frames[-1][2] == bytes([sim.var("app.batPercent")])

    c.send(command(CMD_READ_PERIODIC, 0x8, 2, asz))  # unmapped address: refused, no crash
    sim.run(ms=10)
    errors = [f for f in c.frames() if f[1] == ERR_ADDR]
    assert len(errors) >= 5, "error frame repeated until CMD_CLEAR"
    assert errors[0][2] == (8).to_bytes(asz, "little") + bytes([2])

    c.send(bytes([CMD_CLEAR]))
    other = 8 if asz == 4 else 4
    c.send(command(CMD_READ_PERIODIC, a_bat, 1, other))  # address size of the other architecture
    sim.run(ms=5)
    frames = c.frames()
    assert frames and frames[-1][1] == ERR_ADDRSIZE and frames[-1][2] == bytes([asz])
    c.close()


@e2sim.requirement("E2SIM-TCP-01")
def test_t15_stream_tcp_relay(sim):
    port = sim["UART_DEBUG"].relay.port
    s = socket.create_connection(("127.0.0.1", port))
    s.settimeout(0.5)
    time.sleep(0.05)
    boot(sim)
    fan_on(sim)
    data = b""
    try:
        while b"fan on" not in data:
            data += s.recv(4096)
    except socket.timeout:
        pass
    s.close()
    assert b"fan_hmi boot" in data and b"fan on" in data
