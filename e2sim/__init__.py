"""e2Sim - firmware simulation on PC (host side)."""

from .model import Bit, Block, Event, Model, Param, Stream, Value, Xfer, every
from .sim import Port, Sim, SimError, SimTimeout

__version__ = "0.1.0"


def requirement(*ids: str):
    """Mark a test with the requirement(s) it verifies (JUnit property, e2Unit report)."""
    import pytest

    return pytest.mark.e2sim_requirement(*ids)


__all__ = ["Bit", "Block", "Event", "Model", "Param", "Port", "Sim", "SimError", "SimTimeout", "Stream", "Value",
           "Xfer", "every", "requirement"]
