"""Firmware symbols through gdb in batch mode (DWARF of the DLL): HAL constants and variables."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class SymbolError(Exception):
    pass


@dataclass
class VarInfo:
    expr: str
    addr: int          # link address
    size: int
    kind: str          # int, bool, enum, float, ptr, raw
    signed: bool
    type: str


# runs inside gdb: one JSON line with the answer of every request
_GDB_SCRIPT = r'''
import gdb, json, os
REQ = json.loads(%r)
_SOURCES = None


def sources():
    """C sources of the firmware: scopes where a macro (-g3) may be defined."""
    global _SOURCES
    if _SOURCES is None:
        text = gdb.execute("info sources", to_string=True)
        names = [n.strip() for line in text.splitlines() for n in line.split(", ")]
        _SOURCES = [n for n in names if n.lower().endswith(".c") and os.path.isfile(n)]
    return _SOURCES


def macro_value(name):
    """#define of the firmware, built with -g3: evaluated in the scope of each source until found."""
    for src in sources():
        try:
            gdb.execute('list "%%s":1' %% src.replace("\\", "/"), to_string=True)
            return int(gdb.parse_and_eval(name))
        except gdb.error:
            continue
    raise gdb.error("neither an enum constant nor a macro (macros need -g3): " + name)

CODES = {gdb.TYPE_CODE_INT: "int", gdb.TYPE_CODE_CHAR: "int", gdb.TYPE_CODE_BOOL: "bool",
         gdb.TYPE_CODE_ENUM: "enum", gdb.TYPE_CODE_FLT: "float", gdb.TYPE_CODE_PTR: "ptr"}
out = {}
for kind, expr in REQ:
    try:
        if kind == "const":
            try:
                out[expr] = {"value": int(gdb.parse_and_eval(expr))}
            except gdb.error:
                out[expr] = {"value": macro_value(expr)}
            continue
        v = gdb.parse_and_eval(expr)
        if v.address is None:
            raise gdb.error("not an lvalue")
        t = v.type.strip_typedefs()
        code = CODES.get(t.code, "raw")
        signed = False
        if code in ("int", "enum"):
            try:
                signed = bool(t.is_signed)
            except Exception:
                signed = code == "enum"
        out[expr] = {"addr": int(v.address), "size": t.sizeof, "kind": code, "signed": signed, "type": str(v.type)}
    except Exception as e:
        out[expr] = {"error": str(e)}
print("E2SIM_JSON" + json.dumps(out))
'''


class Symbols:
    def __init__(self, dll: Path, gdb: str):
        self.dll = Path(dll)
        self.gdb = gdb
        self._cache: dict[tuple[str, str], dict] = {}
        self._mtime = None

    def _query(self, requests: list[tuple[str, str]]) -> dict:
        mtime = self.dll.stat().st_mtime
        if mtime != self._mtime:
            self._cache.clear()
            self._mtime = mtime
        todo = [r for r in requests if r not in self._cache]
        if todo:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(_GDB_SCRIPT % json.dumps(todo))
                script = f.name
            try:
                res = subprocess.run([self.gdb, "-batch", "-nx", "-q", "-ex", f"file {self.dll.as_posix()}",
                                      "-x", script], capture_output=True, text=True, timeout=60)
            except FileNotFoundError:
                raise SymbolError(f"gdb not found: {self.gdb}") from None
            finally:
                Path(script).unlink(missing_ok=True)
            line = next((ln for ln in res.stdout.splitlines() if ln.startswith("E2SIM_JSON")), None)
            if line is None:
                raise SymbolError(f"gdb failed on {self.dll}:\n{res.stdout}{res.stderr}")
            answers = json.loads(line[len("E2SIM_JSON"):])
            for r in todo:
                self._cache[r] = answers.get(r[1], {"error": "no answer"})
        return {r[1]: self._cache[r] for r in requests}

    def constants(self, names: list[str]) -> dict[str, int]:
        """Values of enum constants (or macros with -g3) of the HAL."""
        res = self._query([("const", n) for n in names])
        errors = [f"{n}: {a['error']}" for n, a in res.items() if "error" in a]
        if errors:
            raise SymbolError(f"{self.dll.name}: unknown symbols (enum constant or #define of the HAL, -g3):\n  " + "\n  ".join(errors))
        return {n: a["value"] for n, a in res.items()}

    def var(self, expr: str) -> VarInfo:
        a = self._query([("var", expr)])[expr]
        if "error" in a:
            raise SymbolError(f"{self.dll.name}: '{expr}': {a['error']}")
        return VarInfo(expr=expr, addr=a["addr"], size=a["size"], kind=a["kind"], signed=a["signed"], type=a["type"])

    def prefetch(self, exprs: list[str]):
        self._query([("var", e) for e in exprs])
