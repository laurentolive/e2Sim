import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2sim import pe, toolchains  # noqa: E402

HERE = Path(__file__).parent


def pytest_addoption(parser):
    parser.addoption("--e2sim-toolchain", default=None, help="toolchain (default: 'default:' of the file)")


@pytest.fixture
def tc(request) -> toolchains.Toolchain:
    """Toolchain of the self-tests."""
    return toolchains.load(start=HERE).get(request.config.getoption("--e2sim-toolchain"))


@pytest.fixture
def blink(tc):
    """(firmware library, runner, gdb) of the blink self-test firmware."""
    b = HERE / "blink" / "build" / tc.name
    return b / f"blink{pe.LIB_EXT}", b / f"e2sim_runner{pe.EXE_EXT}", tc.tool("gdb")


def make_program() -> str:
    return os.environ.get("MAKE") or shutil.which("make") or "C:/Dev/Tools/make.exe"
