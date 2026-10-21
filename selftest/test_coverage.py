"""Coverage (gcov) of a firmware run by the simulator: counters written at each DLL unload, added up."""

import subprocess
from pathlib import Path

from conftest import make_program
from e2sim import coverage, pe, proto
from e2sim.instance import Instance

HERE = Path(__file__).parent


def test_coverage_report(tc, tmp_path):
    build = tmp_path / "build"
    r = subprocess.run([make_program(), "-s", "-C", str(HERE / "blink"), f"TOOLCHAIN={tc.name}", f"BUILD={build.as_posix()}",
                        "COVERAGE=1"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = build / tc.name
    i = Instance("blink", out / f"blink{pe.LIB_EXT}", out / f"e2sim_runner{pe.EXE_EXT}", timeout_s=10)
    i.start()
    try:
        i.run(0, bytes([proto.REC_POWER, 1]))
        for q in range(1, 600):
            i.run(q * 1_000_000, b"")
        reset = bytes(proto.Writer().u8(proto.REC_IN).u8(proto.CLASSES["GPIO"]).u16(3).i32(1).b)
        i.run(600_100_000, reset)  # soft resets: the DLL is unloaded, its counters written, then added up
    finally:
        i.stop()
    cov = coverage.collect(out, tc.tool("gcov"), HERE)
    blink = next(f for p, f in cov.items() if p.endswith("blink.c"))
    assert blink.functions.get("tick", 0) >= 590, "1 ms tick counted over the whole run"
    assert blink.functions.get("hang_here") == 0, "never called"
    assert blink.functions.get("e2sim_app_main", 0) >= 2, "boot + resets added up"
    coverage.write_html(cov, tmp_path / "html")
    assert (tmp_path / "html" / "index.html").is_file()
    assert "TOTAL" in coverage.summary(cov)
