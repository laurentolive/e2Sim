"""pytest plugin: `sim` fixture (spec §7.2).

conftest.py of a test directory:
    pytest_plugins = ["e2sim.pytest_plugin"]

    @pytest.fixture
    def e2sim_board():
        return Path(__file__).parent / "../sim/hmi.board.yaml"

Options: --e2sim-toolchain <name> (default: E2SIM_TOOLCHAIN, board, registry), --e2sim-update-refs.
"""

from __future__ import annotations

import os

import pytest

from .sim import Sim


def pytest_addoption(parser):
    g = parser.getgroup("e2sim")
    g.addoption("--e2sim-toolchain", default=None, help="toolchain of the firmware build to simulate")
    g.addoption("--e2sim-update-refs", action="store_true", help="rewrite the reference images")


def pytest_configure(config):
    config.addinivalue_line("markers", "e2sim_requirement(*ids): requirements verified by the test")
    if config.getoption("--e2sim-update-refs"):
        os.environ["E2SIM_UPDATE_REFS"] = "1"


def pytest_collection_modifyitems(items):
    for item in items:
        for m in item.iter_markers("e2sim_requirement"):
            for req in m.args:
                item.user_properties.append(("requirement", req))


@pytest.fixture
def e2sim_toolchain(request):
    return request.config.getoption("--e2sim-toolchain")


@pytest.fixture
def sim(e2sim_board, e2sim_toolchain, tmp_path):
    """Started simulation of e2sim_board (a fixture of the conftest), fresh NVM in tmp_path."""
    s = Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path)
    s.start()
    try:
        yield s
    finally:
        s.stop()
