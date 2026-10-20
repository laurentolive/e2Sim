"""Self-tests of the runner (target side), with the blink firmware, below the Sim API."""

from pathlib import Path

import pytest

from e2sim import proto
from e2sim.instance import Instance

HERE = Path(__file__).parent


@pytest.fixture
def inst(request):
    tc = request.config.getoption("--e2sim-toolchain")
    b = HERE / "blink" / "build" / tc
    i = Instance("blink", b / "blink.dll", b / "e2sim_runner.exe", timeout_s=5)
    i.xfer_handler = lambda cls, idx, t, tx: (bytes([tx[1], tx[0]]), 0)
    i.start()
    yield i
    i.stop()


def gpio_in(idx, v):
    return bytes(proto.Writer().u8(proto.REC_IN).u8(proto.CLASSES["GPIO"]).u16(idx).i32(v).b)


def streams(done):
    return [r[3] for r in done.records if r[0] == "stream"]


def test_boot_timer_and_reset(inst):
    d = inst.run(0, bytes([proto.REC_POWER, 1]))
    assert [r[1] for r in d.records if r[0] == "reset"] == ["power_on"]
    assert inst.module_base == inst.pe.image_base, "fixed image base"

    outs = []
    for q in range(1, 1201):
        d = inst.run(q * 1_000_000, b"")
        outs += [(r[3], r[4]) for r in d.records if r[0] == "out" and r[2] == 1]
        if q == 1:
            assert streams(d) == [b"boot 1 cause 0 data 1234\n"]
    # 1 ms tick ISR, GPIO 1 toggled every 500 ticks: exact virtual time
    assert outs == [(1, 500_100_000), (0, 1_000_100_000)]

    d = inst.run(1_201_000_000, gpio_in(2, 1))
    assert ("out", proto.CLASSES["VALUE"], 0, 0x55AA, 1_200_000_000) in d.records, "synchronous xfer"

    d = inst.run(1_202_000_000, gpio_in(3, 1) + gpio_in(2, 0))
    resets = [r for r in d.records if r[0] == "reset"]
    assert resets and resets[0][1] == "soft"
    # .bss cleared (boot 1), .data restored (1234) by the DLL reload
    assert streams(d)[0] == b"boot 1 cause 1 data 1234\n"
    assert len(resets) == 10, "reset held active: one reset per reset duration (100 us), no zero time loop"


def test_memory_access(inst):
    inst.run(0, bytes([proto.REC_POWER, 1]))
    inst.run(1_000_000, b"")
    w = proto.Writer().u8(proto.REC_MEM_READ).u32(1).u64(8).u32(4)  # unmapped page
    d = inst.run(1_000_000, bytes(w.b))
    assert ("mem", 1, 1, b"") in d.records
