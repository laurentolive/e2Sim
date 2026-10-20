import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # e2sim package (repository root)

pytest_plugins = ["e2sim.pytest_plugin"]


@pytest.fixture
def e2sim_board():
    return Path(__file__).parent.parent / "sim" / "hmi.board.yaml"
