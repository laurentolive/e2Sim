"""Sanitizers (toolchain with -fsanitize=address,undefined): a memory error of the firmware is a SimError with
the report of AddressSanitizer, not a silent crash."""

import pytest

import e2sim

from conftest import HERE


def test_sanitizer_report(tc, tmp_path):
    if not any("sanitize=address" in f for f in tc.flags):
        pytest.skip("toolchain without AddressSanitizer (e.g. --e2sim-toolchain linux64-asan)")
    sim = e2sim.Sim(HERE / "blink" / "blink.board.yaml", toolchain=tc.name, work_dir=tmp_path)
    try:
        sim.start()
        sim.run(ms=5)
        sim["OVERFLOW"].set(1)
        with pytest.raises(e2sim.SimError) as e:
            sim.run(ms=5)
    finally:
        try:
            sim.stop()
        except Exception:  # noqa: BLE001 - the runner is already stopped
            pass
    msg = str(e.value)
    assert "sanitizer" in msg and "overflow_here" in msg and "blink.c:" in msg, msg
    assert "out of bounds" in msg or "buffer-overflow" in msg, msg  # UBSan (bounds) or ASan, the first one
