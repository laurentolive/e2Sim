"""Versions: e2sim --version, API version compiled into the firmware and checked by the host (firmware, runner)."""

import subprocess
import sys

import pytest

import e2sim
from e2sim import proto

from conftest import HERE


def test_version_cli():
    out = subprocess.run([sys.executable, str(HERE.parent / "e2sim_cli.py"), "--version"], capture_output=True, text=True)
    assert out.stdout.startswith(f"e2sim {e2sim.__version__} (API {proto.API_VERSION[0]}.{proto.API_VERSION[1]}")


def test_api_version_announced(tc, tmp_path):
    with e2sim.Sim(HERE / "blink" / "blink.board.yaml", toolchain=tc.name, work_dir=tmp_path) as sim:
        sim.start()
        inst = sim.instance().inst
        assert inst.fw_api >> 16 == proto.API_VERSION[0] and inst.runner_api >> 16 == proto.API_VERSION[0]


def test_api_version_refused():
    v1, v2 = 1 << 16, 2 << 16
    proto.check_api("fw", v1 | 3, v1)  # another minor: accepted
    with pytest.raises(proto.LinkError, match="firmware built with e2Sim API 2.0, runner 1.0: rebuild"):
        proto.check_api("fw", v2, v1)
    with pytest.raises(proto.LinkError, match="firmware without e2Sim API version"):
        proto.check_api("fw", 0, v1)
    with pytest.raises(proto.LinkError, match="runner built with e2Sim API 2.0"):
        proto.check_api("fw", v2, v2)
