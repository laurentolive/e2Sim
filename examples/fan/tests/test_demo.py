"""The demonstration (demo/demo.py) played as a test: it must never break (spec §16)."""

import sys
from pathlib import Path

import e2sim

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))
import demo  # noqa: E402


@e2sim.requirement("E2SIM-DEMO-01")
def test_demo_all_chapters(e2sim_toolchain, tmp_path):
    """Every chapter of the demo, checks included, then the replay of its recording."""
    args = ["--check", "--record", str(tmp_path / "demo.e2simrec")]
    if e2sim_toolchain:
        args += ["--toolchain", e2sim_toolchain]
    assert demo.main(args) == 0
