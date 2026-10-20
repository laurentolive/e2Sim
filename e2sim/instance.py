"""One simulated firmware instance: runner process + link (spec §3, §4.3)."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Callable

from . import pe, proto

# xfer handler: (cls, idx, t_ns, tx bytes) -> (rx bytes, cost_ns)
XferHandler = Callable[[int, int, int, bytes], "tuple[bytes, int]"]


class Instance:
    def __init__(self, name: str, dll: Path, runner: Path, *, yield_cost_ns: int = 1000,
                 blocks_cfg: list[tuple[int, int, str]] | None = None, timeout_s: float = 10.0,
                 connect_port: int | None = None, log_dir: Path | None = None):
        self.name = name
        self.dll = Path(dll)
        self.runner = Path(runner)
        self.yield_cost_ns = yield_cost_ns
        self.blocks_cfg = blocks_cfg or []
        self.timeout_s = timeout_s
        self.connect_port = connect_port
        self.log_dir = log_dir
        self.proc: subprocess.Popen | None = None
        self.link: proto.Link | None = None
        self.pe = pe.read(self.dll)
        self.module_base = 0
        self.ptr_size = self.pe.ptr_size
        self.pid = 0
        self.xfer_handler: XferHandler | None = None
        self.tap: Callable[[int, bytes], None] | None = None  # (kind, payload) of every message sent (record)
        self._mem_id = 0

    # ------------------------------------------------------------------
    def start(self):
        for p, what in ((self.dll, "firmware"), (self.runner, "runner")):
            if not p.is_file():
                raise FileNotFoundError(f"{self.name}: {what} {p} not found (build it first: make)")
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.connect_port or 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        if self.connect_port is None:
            out = None
            if self.log_dir is not None:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                out = open(self.log_dir / f"{self.name}.stdout.log", "wb")  # noqa: SIM115 - owned by the process
            self.proc = subprocess.Popen(
                [str(self.runner), "--dll", str(self.dll), "--host", f"127.0.0.1:{port}"],
                stdout=out, stderr=subprocess.STDOUT if out else None)
            srv.settimeout(self.timeout_s)
        else:
            srv.settimeout(None)  # firmware launched from the debugger, whenever it comes
        try:
            sock, _ = srv.accept()
        except socket.timeout:
            raise proto.LinkError(f"{self.name}: the runner did not connect") from None
        finally:
            srv.close()
        # a debugger may stop the firmware anywhere: no answer timeout in that mode
        self.link = proto.Link(sock, None if self.connect_port else self.timeout_s)
        t, r = self.link.recv()
        if t != proto.MSG_HELLO:
            raise proto.LinkError(f"{self.name}: HELLO expected, got 0x{t:02x}")
        version = r.u32()
        if version != proto.WIRE_VERSION:
            raise proto.LinkError(f"{self.name}: runner protocol {version}, host {proto.WIRE_VERSION}: rebuild")
        self.ptr_size = r.u8()
        self.module_base = r.u64()
        self.pid = r.u32()
        w = proto.Writer().u64(self.yield_cost_ns).u16(len(self.blocks_cfg))
        for idx, fill, path in self.blocks_cfg:
            w.u16(idx).u8(fill).str(path)
        self.link.send(proto.MSG_CONFIG, bytes(w.b))

    def stop(self):
        if self.link is not None:
            try:
                self.link.send(proto.MSG_QUIT)
            except OSError:
                pass
            self.link.close()
            self.link = None
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None

    # ------------------------------------------------------------------
    def run(self, until_ns: int, records: bytes, from_ns: int = 0, quantum_ns: int = 0) -> proto.Done:
        """Inputs (records) applied, run until until_ns, outputs returned. quantum_ns != 0: quanta from from_ns,
        stop at the end of the first quantum with an output (Done.end)."""
        hdr = proto.Writer().u64(until_ns).u64(from_ns).u64(quantum_ns).b
        return self.run_payload(bytes(hdr + records + bytes([proto.REC_END])))

    def run_payload(self, payload: bytes, xfer_replies: list[bytes] | None = None) -> proto.Done:
        """Send a RUN payload as it is (replay: with the recorded transaction answers)."""
        if self.tap is not None:
            self.tap(1, payload)
        self.link.send(proto.MSG_RUN, payload)
        while True:
            t, r = self.link.recv()
            if t == proto.MSG_DONE:
                done = proto.decode_done(r)
                for rec in done.records:
                    if rec[0] == "reset":
                        self.module_base = rec[3]
                return done
            if t == proto.MSG_XFER_REQ:
                cls, idx, ts, tx = r.u8(), r.u16(), r.u64(), r.data()
                if xfer_replies is not None:
                    if not xfer_replies:
                        raise proto.LinkError(f"{self.name}: replay: transaction not in the record (firmware changed ?)")
                    reply = xfer_replies.pop(0)
                else:
                    rx, cost = (b"", 0) if self.xfer_handler is None else self.xfer_handler(cls, idx, ts, tx)
                    reply = bytes(proto.Writer().u64(cost).data(bytes(rx)).b)
                if self.tap is not None:
                    self.tap(2, reply)
                self.link.send(proto.MSG_XFER_REPLY, reply)
            else:
                raise proto.LinkError(f"{self.name}: unexpected message 0x{t:02x}")

    def relocate(self, link_addr: int) -> int:
        """Link address (symbols) -> address in the process."""
        return link_addr - self.pe.image_base + self.module_base

    def next_mem_id(self) -> int:
        self._mem_id += 1
        return self._mem_id
