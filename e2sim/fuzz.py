"""Fuzzing of a stream port of the firmware (frame parsers): deterministic random or mutated frames.

    from e2sim import fuzz
    result = fuzz.stream(sim, "UART_LINK", corpus=[valid_frame, ...], frames=5000, seed=1,
                         check=lambda: sim.var("ctrl.duty") <= 1000)
    assert result.ok, result.report()

A failure is a crash of the runner, a loop without yield point, a reset the scenario did not expect, or a check
returning False. The input that led to it is in result.history (and saved with save=); with Sim(record=...) the
whole run replays exactly (e2sim replay).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .proto import LinkError
from .sim import Sim, SimError


def mutate(rng: random.Random, frame: bytes) -> bytes:
    """One random mutation: bit flip, byte replaced, inserted, deleted, truncation, duplication."""
    b = bytearray(frame or b"\x00")
    op = rng.randrange(6)
    i = rng.randrange(len(b))
    if op == 0:
        b[i] ^= 1 << rng.randrange(8)
    elif op == 1:
        b[i] = rng.randrange(256)
    elif op == 2:
        b.insert(i, rng.randrange(256))
    elif op == 3 and len(b) > 1:
        del b[i]
    elif op == 4:
        del b[i:]
    else:
        b += b[i:]
    return bytes(b)


@dataclass
class FuzzResult:
    port: str
    seed: int
    frames: int = 0
    bytes: int = 0
    failure: str = ""
    history: list[bytes] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failure

    def report(self) -> str:
        if self.ok:
            return f"fuzz {self.port}: {self.frames} frames, {self.bytes} bytes, seed {self.seed}: no failure"
        last = self.history[-1].hex(" ") if self.history else ""
        return (f"fuzz {self.port}: FAILED after {self.frames} frames (seed {self.seed}): {self.failure}\n"
                f"  last input: {last}")


def stream(sim: Sim, port: str, *, corpus: list[bytes] | None = None, frames: int = 1000, seed: int = 1,
           every_ms: float = 5, random_ratio: float = 0.2, max_len: int = 32,
           check: Callable[[], bool] | None = None, resets_allowed: bool = False,
           save: str | Path | None = None) -> FuzzResult:
    """Write frames on the stream port, one every every_ms of virtual time, and watch the firmware."""
    rng = random.Random(seed)
    res = FuzzResult(port=port, seed=seed)
    p = sim[port]
    inst = sim.instance(port.partition(".")[0]) if "." in port else sim.instance()
    resets0 = len(inst.resets)
    for _ in range(frames):
        if corpus and rng.random() >= random_ratio:
            data = mutate(rng, rng.choice(corpus))
        else:
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(1, max_len + 1)))
        res.history.append(data)
        res.frames += 1
        res.bytes += len(data)
        try:
            p.write(data)
            sim.run(ms=every_ms)
            if not resets_allowed and len(inst.resets) > resets0:
                res.failure = f"unexpected reset ({inst.resets[-1][1]}) at t = {inst.resets[-1][0] / 1e9:.6f} s"
            elif check is not None and not check():
                res.failure = f"check failed at t = {sim.now:.6f} s"
        except (SimError, LinkError) as e:
            res.failure = f"{type(e).__name__}: {e}"
        if res.failure:
            break
    if save is not None:
        Path(save).parent.mkdir(parents=True, exist_ok=True)
        Path(save).write_text("\n".join(h.hex() for h in res.history) + "\n", encoding="ascii")
    return res
