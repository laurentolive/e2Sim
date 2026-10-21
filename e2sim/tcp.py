"""Local TCP server with one client at a time: bytes received in a thread, served at quantum boundaries."""

from __future__ import annotations

import socket
import threading


class TcpServer:
    def __init__(self, port: int = 0, name: str = ""):
        self.name = name
        try:
            self._srv = self._listen(port)
        except OSError:
            if port == 0:
                raise
            self._srv = self._listen(0)  # fixed port of the board taken (other program, other simulation)
            print(f"e2sim: {name}: port {port} already in use, port {self._srv.getsockname()[1]} used", flush=True)
        self.port = self._srv.getsockname()[1]
        self._client: socket.socket | None = None
        self._rx = bytearray()
        self._lock = threading.Lock()
        self._connected_events = 0
        self._closed = False
        self._thread = threading.Thread(target=self._accept_loop, name=f"e2sim-tcp-{name}", daemon=True)
        self._thread.start()

    @staticmethod
    def _listen(port: int) -> socket.socket:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: SO_REUSEADDR would share a port already listened
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:  # POSIX: rebind a fixed port at once after a restart
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", port))
            srv.listen(1)
        except OSError:
            srv.close()
            raise
        return srv

    def _accept_loop(self):
        while not self._closed:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                if self._client is not None:  # a new client replaces the previous one
                    self._client.close()
                self._client = conn
                self._rx.clear()
                self._connected_events += 1
            threading.Thread(target=self._recv_loop, args=(conn,), daemon=True).start()

    def _recv_loop(self, conn: socket.socket):
        while True:
            try:
                data = conn.recv(4096)
            except OSError:
                data = b""
            with self._lock:
                if not data:
                    if self._client is conn:
                        self._client = None
                    conn.close()
                    return
                if self._client is conn:
                    self._rx += data

    @property
    def connected(self) -> bool:
        return self._client is not None

    def take(self) -> tuple[bytes, int]:
        """Bytes received since the last call, number of new connections."""
        with self._lock:
            data, events = bytes(self._rx), self._connected_events
            self._rx.clear()
            self._connected_events = 0
        return data, events

    def send(self, data: bytes):
        """Blocking: a slow client slows the simulation down, nothing is lost. Without client: dropped."""
        client = self._client
        if client is None or not data:
            return
        try:
            client.sendall(data)
        except OSError:
            with self._lock:
                if self._client is client:
                    self._client = None

    def close(self):
        self._closed = True
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
        self._srv.close()
