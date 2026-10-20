"""The coverage matrix of the spec (§16.3) is true: every test and demo chapter it cites exists, every test of
the example carries a requirement (the example project tests every feature of e2Sim)."""

import ast
import re
import sys
from pathlib import Path

import e2sim

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
SPEC = ROOT / "docs" / "SPEC.md"


def matrix_rows():
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("### 16.3"):text.index("### 16.4")]
    rows = [r for r in section.splitlines() if r.startswith("|") and not r.startswith("|---")][1:]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows]


def _functions(folder: Path) -> dict[str, ast.FunctionDef]:
    out = {}
    for f in folder.glob("test_*.py"):
        for node in ast.parse(f.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                out[node.name] = node
    return out


def expand(cell: str, prefix: str) -> list[int]:
    """'T03 à T08, T12' -> [3..8, 12]."""
    nums = []
    for a, b in re.findall(prefix + r"(\d+)(?:\s*à\s*" + prefix + r"(\d+))?", cell):
        nums += range(int(a), int(b or a) + 1)
    return nums


@e2sim.requirement("E2SIM-MATRIX-01")
def test_matrix_tests_exist():
    tests = _functions(HERE)
    selftests = _functions(ROOT / "selftest")
    numbers = {int(m.group(1)) for n in tests if (m := re.match(r"test_t(\d+)_", n))}
    rows = matrix_rows()
    assert len(rows) >= 20
    for feature, where, cell, demo in rows:
        assert cell, f"{feature}: no test"
        for n in expand(cell, "T"):
            assert n in numbers, f"{feature}: test T{n:02d} not found in examples/fan/tests"
        for name in re.findall(r"selftest \((\w+)\)", cell):
            assert name in selftests, f"{feature}: selftest {name} not found"
        if "GUI" in cell:
            assert "test_gui_api" in tests
        if "test-all" in cell:
            assert "test-all:" in (HERE.parent / "Makefile").read_text(encoding="utf-8")
        known = expand(cell, "T") or re.search(r"tous|selftest \(|GUI|test-all|manuel", cell)
        assert known, f"{feature}: test reference not understood: {cell!r}"


@e2sim.requirement("E2SIM-MATRIX-01")
def test_matrix_demo_chapters_exist():
    sys.path.insert(0, str(HERE.parent / "demo"))
    import demo

    chapters = len(demo.CHAPTERS) + 1  # + 11: replay of the record, at the end of main()
    for feature, where, cell, cell_demo in matrix_rows():
        nums = [int(x) for x in re.findall(r"\d+", cell_demo)]
        if " à " in cell_demo:
            nums = list(range(nums[0], nums[-1] + 1))
        assert nums or cell_demo in ("—", "toute la démo", "annexe du guide"), f"{feature}: demo {cell_demo!r}"
        for n in nums:
            assert 1 <= n <= chapters, f"{feature}: demo chapter {n} does not exist"


@e2sim.requirement("E2SIM-MATRIX-01")
def test_every_test_has_a_requirement():
    for name, fn in _functions(HERE).items():
        marks = [d for d in fn.decorator_list if "requirement" in ast.unparse(d)]
        assert marks, f"{name}: no @e2sim.requirement(...)"
