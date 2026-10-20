"""Environment models in Python, at HAL data level (spec §7.1).

    class Battery(e2sim.Model):
        adc = e2sim.Value()                  # port bound by board.yaml: ports: {adc: VBAT_ADC}
        voltage_V = e2sim.Param(12.0)        # settable from board.yaml, scripts, GUI

        @e2sim.every(ms=10)
        def step(self):
            self.adc.set(round(self.voltage_V / 15.0 * 4095))

Callbacks (optional): on_<port>(value) for an output bit / value of the firmware, on_<port>(data) or
on_rx(data) for a stream, on_<port>(tx) or on_xfer(tx) -> bytes | (bytes, cost_ns) for a transaction,
on_<port>() for an event, on_reset(cause), on_power(on), setup().
"""

from __future__ import annotations

from typing import Any, Callable


class PortRef:
    """Declares a port of the model, bound to a board port by name."""

    kind = "any"

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        try:
            return obj._ports[self.name]
        except KeyError:
            raise AttributeError(f"{type(obj).__name__}.{self.name}: port not bound (board.yaml: ports:)") from None


class Bit(PortRef):
    kind = "bit"


class Value(PortRef):
    kind = "value"


class Stream(PortRef):
    kind = "stream"


class Xfer(PortRef):
    kind = "xfer"


class Block(PortRef):
    kind = "block"


class Event(PortRef):
    kind = "event"


class Param:
    """Parameter of a model: default in the class, overridden by board.yaml params: or a script."""

    def __init__(self, default: Any = None, doc: str = ""):
        self.default = default
        self.doc = doc

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return obj._params.get(self.name, self.default)

    def __set__(self, obj, value):
        obj._params[self.name] = value


def every(*, ms: float = 0, us: float = 0, s: float = 0) -> Callable:
    """Run the method periodically, in virtual time (at quantum boundaries)."""
    period_ns = round(s * 1e9 + ms * 1e6 + us * 1e3)
    if period_ns <= 0:
        raise ValueError("every(): period > 0 expected")

    def deco(fn):
        fn._e2sim_every = period_ns
        return fn

    return deco


class Model:
    def __init__(self, sim, instance: str, name: str, ports: dict, params: dict | None = None):
        self._sim = sim
        self._instance = instance
        self.name = name
        self._ports = ports
        self._params = {}
        for k, v in (params or {}).items():
            if not isinstance(getattr(type(self), k, None), Param):
                raise ValueError(f"model {name}: unknown parameter '{k}'")
            setattr(self, k, v)
        refs = {k: v for cls in reversed(type(self).__mro__) for k, v in vars(cls).items() if isinstance(v, PortRef)}
        missing = [k for k in refs if k not in ports]
        if missing:
            raise ValueError(f"model {name}: ports not bound: {', '.join(missing)}")
        for k, ref in refs.items():
            if ref.kind != "any" and ports[k].type != ref.kind:
                raise ValueError(f"model {name}: port '{k}' is {ports[k].type}, {ref.kind} expected")
        self._periodic = [(getattr(self, k), fn._e2sim_every)
                          for cls in reversed(type(self).__mro__) for k, fn in vars(cls).items()
                          if callable(fn) and hasattr(fn, "_e2sim_every")]

    @property
    def now(self) -> float:
        """Virtual time, seconds."""
        return self._sim.now

    @property
    def now_ns(self) -> int:
        return self._sim.now_ns

    @property
    def params(self) -> dict:
        return {k: getattr(self, k) for cls in type(self).__mro__ for k, v in vars(cls).items() if isinstance(v, Param)}

    def setup(self):
        pass

    def on_reset(self, cause: str):
        pass

    def on_power(self, on: bool):
        pass

    def __repr__(self):
        return f"<{type(self).__name__} {self.name} {self.params}>"
