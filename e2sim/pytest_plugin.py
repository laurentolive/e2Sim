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
    g.addoption("--e2sim-record", metavar="DIR", default=None,
                help="record every test (DIR/<test>.e2simrec): replay with e2sim replay")


def pytest_configure(config):
    config.addinivalue_line("markers", "e2sim_requirement(*ids): requirements verified by the test")
    if config.getoption("--e2sim-update-refs"):
        os.environ["E2SIM_UPDATE_REFS"] = "1"
    if getattr(config, "workerinput", None) is not None:
        return  # pytest-xdist worker: done once by the controller
    # licence: once per session, popups if a display exists, never a console question (pytest captures stdin)
    from .license.ui import make_ui
    from .license import LicenseManager

    ui = make_ui()
    try:
        mgr = LicenseManager(ui)
        mgr.startup()
        config._e2sim_license = mgr.status_text()
    finally:
        ui.close()


def pytest_sessionstart(session):
    """Licence in the JUnit XML report (spec §17.5)."""
    config = session.config
    xml = getattr(config, "_xml", None)
    try:
        from _pytest.junitxml import xml_key

        xml = config.stash.get(xml_key, xml)
    except ImportError:
        pass
    text = getattr(config, "_e2sim_license", None)
    if xml is not None and text:
        xml.add_global_property("license", text)


def pytest_report_header(config):
    text = getattr(config, "_e2sim_license", None)
    return f"e2sim: {text}" if text else None


def pytest_collection_modifyitems(items):
    for item in items:
        for m in item.iter_markers("e2sim_requirement"):
            for req in m.args:
                item.user_properties.append(("requirement", req))


@pytest.fixture
def e2sim_toolchain(request):
    return request.config.getoption("--e2sim-toolchain")


@pytest.fixture
def sim(request, e2sim_board, e2sim_toolchain, tmp_path):
    """Started simulation of e2sim_board (a fixture of the conftest), fresh NVM in tmp_path."""
    rec_dir = request.config.getoption("--e2sim-record")
    rec = None
    if rec_dir:
        from pathlib import Path

        rec = Path(rec_dir) / (request.node.name.replace("/", "_").replace("[", "_").replace("]", "") + ".e2simrec")
    s = Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path, record=rec)
    s.start()
    try:
        yield s
    finally:
        s.stop()
