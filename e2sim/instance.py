"""One simulated firmware instance: runner process + link (spec §3, §4.3)."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Callable

from . import pe, proto

# exit code of a runner stopped by a sanitizer (ASan, UBSan, LSan): set by the host through *SAN_OPTIONS
SANITIZER_EXIT = 86

# xfer handler: (cls, idx, t_ns, tx bytes) -> (rx bytes, cost_ns)
XferHandler = Callable[[int, int, int, bytes], "tuple[bytes, int]"]


class Instance:
    def __init__(self, name: str, dll: Path, runner: Path, *, yield_cost_ns: int = 1000,
                 blocks_cfg: list[tuple[int, int, str]] | None = None, timeout_s: float = 10.0,
                 connect_port: int | None = None, log_dir: Path | None = None, reset_process: bool = False,
                 hang_timeout_s: float = 3.0, transport: str = "shm"):
        self.name = name
        self.dll = Path(dll)
        self.runner = Path(runner)
        self.yield_cost_ns = yield_cost_ns
        self.blocks_cfg = blocks_cfg or []
        self.timeout_s = timeout_s
        self.connect_port = connect_port
        self.log_dir = log_dir
        self.reset_process = reset_process
        self.hang_timeout_s = hang_timeout_s
        self.transport = transport  # "shm" (shared memory after CONFIG) or "tcp"
        self.restarts = 0
        self.proc: subprocess.Popen | None = None
        self.link: proto.Link | None = None
        self.tcp: proto.Link | None = None  # kept open while the shared memory is used
        self.pe = pe.read(self.dll)
        self.module_base = 0
        self.ptr_size = self.pe.ptr_size
        self.pid = 0
        self.xfer_handler: XferHandler | None = None
        self.tap: Callable[[int, bytes], None] | None = None  # (kind, payload) of every message sent (record)
        self._mem_id = 0

    # ------------------------------------------------------------------
    def start(self, start_ns: int = 0, boot_cause: int | None = None):
        """Start the runner. start_ns / boot_cause: new process after a reset (reset: process)."""
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
                out = open(self.log_dir / f"{self.name}.stdout.log", "ab" if self.restarts else "wb")  # noqa: SIM115 - owned by the process
            self.proc = subprocess.Popen(
                [str(self.runner), "--dll", str(self.dll), "--host", f"127.0.0.1:{port}",
                 "--hang-timeout", str(round(self.hang_timeout_s * 1000))],
                stdout=out, stderr=subprocess.STDOUT if out else None, env=self._sanitizer_env())
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
        r.str()  # path of the firmware
        self.fw_api, self.runner_api = r.u32(), r.u32()
        proto.check_api(self.name, self.fw_api, self.runner_api)
        w = proto.Writer().u64(self.yield_cost_ns).u16(len(self.blocks_cfg))
        for idx, fill, path in self.blocks_cfg:
            w.u16(idx).u8(fill).str(path)
        w.u8(1 if self.reset_process else 0).u64(start_ns).u8(0xFF if boot_cause is None else boot_cause)
        shm = None
        if self.transport == "shm" and os.name == "nt":
            from .shm import ShmLink

            shm = ShmLink(None if self.connect_port else self.timeout_s)
            if self.proc is not None:
                shm.process = int(self.proc._handle)  # Windows only (transport shm)
            elif self.pid:
                shm.watch_pid(self.pid)  # debugger: end of the session = end of the runner
        w.str(shm.name if shm else "").u32(os.getpid())
        self.link.send(proto.MSG_CONFIG, bytes(w.b))
        if shm is not None:  # the runner switches to the shared memory after CONFIG
            self.tcp = self.link
            self.link = shm

    def _sanitizer_env(self) -> dict:
        """Sanitizer reports of a firmware built with -fsanitize: own exit code, report file (ignored otherwise)."""
        env = dict(os.environ)
        if self.log_dir is None:
            return env
        self.sanitizer_log = Path(self.log_dir) / f"{self.name}.sanitizer"
        common = f"exitcode={SANITIZER_EXIT}:log_path={self.sanitizer_log.as_posix()}"
        for var, extra in (("ASAN_OPTIONS", "detect_leaks=1"), ("UBSAN_OPTIONS", "print_stacktrace=1:halt_on_error=1"),
                           ("LSAN_OPTIONS", "")):
            env[var] = ":".join(x for x in (env.get(var, ""), common, extra) if x)
        return env

    def sanitizer_report(self) -> str | None:
        """Report of the sanitizer when the runner was stopped by one, else None."""
        if self.proc is None or self.proc.poll() != SANITIZER_EXIT:
            return None
        log = getattr(self, "sanitizer_log", None)
        texts = [f.read_text(errors="replace") for f in sorted(log.parent.glob(log.name + "*"))] if log else []
        out = Path(self.log_dir) / f"{self.name}.stdout.log" if self.log_dir else None
        if out is not None and out.is_file():  # UBSan writes its reports on the error output of the runner
            text = out.read_text(errors="replace")
            marks = [text.find(m) for m in ("runtime error:", "ERROR: AddressSanitizer", "ERROR: LeakSanitizer")]
            first = min((m for m in marks if m >= 0), default=-1)
            if first >= 0:
                texts.insert(0, text[text.rfind("\n", 0, first) + 1:])
        lines = [ln for ln in "\n".join(texts).splitlines()
                 if ln.strip() and "doesn't fully support makecontext" not in ln] or ["(no report)"]
        return "\n".join(lines[:60] + (["..."] if len(lines) > 60 else []))

    def stop(self):
        if self.link is not None:
            try:
                self.link.send(proto.MSG_QUIT)
            except (OSError, ValueError, proto.LinkError):
                pass
        report = None
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            report = self.sanitizer_report()  # e.g. a leak, reported at the end of the process
            self.proc = None
        for link in (self.link, getattr(self, "tcp", None)):
            if link is not None:
                link.close()
        self.link = None
        self.tcp = None
        if report:
            raise proto.LinkError(f"{self.name}: sanitizer report\n{report}")

    # ------------------------------------------------------------------
    def run(self, until_ns: int, records: bytes, from_ns: int = 0, quantum_ns: int = 0) -> proto.Done:
        """Inputs (records) applied, run until until_ns, outputs returned. quantum_ns != 0: quanta from from_ns,
        stop at the end of the first quantum with an output (Done.end)."""
        hdr = proto.Writer().u64(until_ns).u64(from_ns).u64(quantum_ns).b
        return self.run_payload(bytes(hdr + records + bytes([proto.REC_END])))

    def run_payload(self, payload: bytes, xfer_replies: list[bytes] | None = None) -> proto.Done:
        """Send a RUN payload as it is (replay: with the recorded transaction answers)."""
        self.send_payload(payload)
        return self.recv_done(xfer_replies)

    def send_payload(self, payload: bytes):
        """First half of a RUN: the runner computes while the host serves the other instances."""
        if self.tap is not None:
            self.tap(1, payload)
        self.link.send(proto.MSG_RUN, payload)

    def send_run(self, until_ns: int, records: bytes, from_ns: int = 0, quantum_ns: int = 0):
        hdr = proto.Writer().u64(until_ns).u64(from_ns).u64(quantum_ns).b
        self.send_payload(bytes(hdr + records + bytes([proto.REC_END])))

    def recv_done(self, xfer_replies: list[bytes] | None = None) -> proto.Done:
        """Second half of a RUN: transactions served, DONE returned."""
        while True:
            t, r = self.link.recv()
            if t == proto.MSG_DONE:
                done = proto.decode_done(r)
                for rec in done.records:
                    if rec[0] == "reset":
                        self.module_base = rec[3]
                return done
            if t == proto.MSG_HANG:
                ts, n = r.u64(), r.u8()
                pcs = [self.unrelocate(r.u64()) for _ in range(n)]
                raise proto.HangError(f"{self.name}: no yield point for {self.hang_timeout_s:g} s at "
                                      f"t = {ts / 1e9:.6f} s: firmware loop without HAL call", ts, pcs)
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

    @property
    def _mask(self) -> int:
        return (1 << (8 * self.ptr_size)) - 1

    def unrelocate(self, addr: int) -> int:
        """Address in the process -> link address (symbols)."""
        return (addr - self.module_base + self.pe.image_base) & self._mask

    def relocate(self, link_addr: int) -> int:
        """Link address (symbols) -> address in the process."""
        return (link_addr - self.pe.image_base + self.module_base) & self._mask

    def next_mem_id(self) -> int:
        self._mem_id += 1
        return self._mem_id
