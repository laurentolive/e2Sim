"""Code coverage of the firmware on the system tests (gcov, spec §14 V2).

Build with `make COVERAGE=1`: the counters are written each time the firmware DLL is unloaded (every reset, end
of the simulation) and gcov adds them up. `e2sim coverage BUILD_DIR` reads them with the gcov of the toolchain
(JSON format) and writes a summary and an annotated HTML report. No dependency.
"""

from __future__ import annotations

import gzip
import html
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileCoverage:
    path: str
    lines: dict[int, int] = field(default_factory=dict)  # line -> count
    functions: dict[str, int] = field(default_factory=dict)  # name -> count

    @property
    def total(self) -> int:
        return len(self.lines)

    @property
    def covered(self) -> int:
        return sum(1 for c in self.lines.values() if c > 0)

    @property
    def percent(self) -> float:
        return 100.0 * self.covered / self.total if self.total else 100.0


def collect(build_dir: Path, gcov: str, sources_root: Path | None = None) -> dict[str, FileCoverage]:
    """Coverage per source file from the .gcda of build_dir (sources outside sources_root ignored)."""
    gcdas = sorted(Path(build_dir).glob("*.gcda"))
    out: dict[str, FileCoverage] = {}
    if not gcdas:
        return out
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([gcov, "--json-format", "--object-directory", str(Path(build_dir).resolve()),
                        *[str(g.resolve()) for g in gcdas]], cwd=tmp, capture_output=True, check=False)
        for js in Path(tmp).glob("*.gcov.json.gz"):
            data = json.loads(gzip.decompress(js.read_bytes()))
            for f in data.get("files", []):
                src = Path(f["file"])
                if not src.is_absolute():
                    src = (Path(data.get("current_working_directory", ".")) / src).resolve()
                if sources_root is not None and Path(sources_root).resolve() not in src.resolve().parents:
                    continue
                fc = out.setdefault(str(src), FileCoverage(str(src)))
                for ln in f.get("lines", []):
                    fc.lines[ln["line_number"]] = fc.lines.get(ln["line_number"], 0) + ln["count"]
                for fn in f.get("functions", []):
                    fc.functions[fn["name"]] = fc.functions.get(fn["name"], 0) + fn["execution_count"]
    return dict(sorted(out.items()))


def summary(cov: dict[str, FileCoverage], root: Path | None = None) -> str:
    rows = []
    for path, fc in cov.items():
        name = Path(path).relative_to(root).as_posix() if root and Path(root) in Path(path).parents else Path(path).name
        rows.append(f"{fc.percent:6.1f} %  {fc.covered:5}/{fc.total:<5}  {name}")
    total = sum(f.total for f in cov.values())
    covered = sum(f.covered for f in cov.values())
    pct = 100.0 * covered / total if total else 100.0
    return "\n".join(rows + [f"{pct:6.1f} %  {covered:5}/{total:<5}  TOTAL (lines)"])


def write_html(cov: dict[str, FileCoverage], out_dir: Path, title: str = "e2Sim coverage"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    style = ("body{font:13px system-ui,sans-serif;margin:16px}table{border-collapse:collapse}"
             "td,th{padding:3px 10px;border-bottom:1px solid #ddd;text-align:left}"
             "pre{font:12px ui-monospace,Consolas,monospace;margin:0}.y{background:#d8f5d8}.n{background:#ffd6d6}"
             ".c{color:#888;display:inline-block;width:70px;text-align:right;padding-right:8px}")
    rows = []
    for i, (path, fc) in enumerate(cov.items()):
        page = f"f{i}.html"
        lines = []
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            text = []
        for n, src in enumerate(text, 1):
            c = fc.lines.get(n)
            cls = "" if c is None else ("y" if c > 0 else "n")
            count = "" if c is None else str(c)
            lines.append(f'<pre class="{cls}"><span class="c">{count}</span>{n:5}  {html.escape(src)}</pre>')
        (out_dir / page).write_text(f"<!doctype html><meta charset=utf-8><title>{html.escape(Path(path).name)}</title>"
                                    f"<style>{style}</style><h2>{html.escape(path)} - {fc.percent:.1f} %</h2>"
                                    + "".join(lines), encoding="utf-8")
        rows.append(f"<tr><td><a href='{page}'>{html.escape(Path(path).name)}</a></td><td>{fc.percent:.1f} %</td>"
                    f"<td>{fc.covered}/{fc.total}</td><td>{html.escape(path)}</td></tr>")
    total = sum(f.total for f in cov.values())
    covered = sum(f.covered for f in cov.values())
    pct = 100.0 * covered / total if total else 100.0
    (out_dir / "index.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title><style>{style}</style>"
        f"<h1>{html.escape(title)}: {pct:.1f} % of the lines ({covered}/{total})</h1>"
        f"<table><tr><th>File</th><th>Lines</th><th></th><th>Path</th></tr>{''.join(rows)}</table>", encoding="utf-8")
