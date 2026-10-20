"""Record / replay (spec §7.4): the record of a scenario, sent again without models nor script, gives the
same outputs; on the other architecture too."""

from pathlib import Path

import e2sim
from e2sim.sim import replay
from fan_helpers import boot, fan_on, key

SYSTEM = Path(__file__).parent.parent / "sim" / "system.yaml"
OTHER = {"host32": "host64", "host64": "host32"}


def hmi_scenario(sim):
    boot(sim)
    fan_on(sim)
    key(sim, "BTN_PLUS")
    sim.model("TempSensor").temp_C = 62.0       # xfer answers
    sim.model("MotorBoard").corrupt_crc = True  # stream
    sim.run(s=1)
    sim.model("MotorBoard").corrupt_crc = False
    assert sim.var("app.speedLevel") == 2       # memory access
    sim["BTN_POWER"].press(s=2.5)
    sim.run(s=3)                                 # power off
    sim["EEPROM"].write_block(2, b"\x09")        # NVM corrupted by the host
    boot(sim)


@e2sim.requirement("E2SIM-REPLAY-01")
def test_t12_replay_hmi(e2sim_board, e2sim_toolchain, tmp_path):
    rec = tmp_path / "hmi.e2simrec"
    with e2sim.Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path / "rec", record=rec) as sim:
        hmi_scenario(sim)
        expected = sim.trace_digest()
        resets = list(sim.resets)
    r, same = replay(rec, work_dir=tmp_path / "replay")
    assert same and r.trace_digest() == expected
    assert r.resets == resets


@e2sim.requirement("E2SIM-REPLAY-02")
def test_t12_replay_system_other_arch(e2sim_toolchain, tmp_path):
    rec = tmp_path / "system.e2simrec"
    with e2sim.Sim(SYSTEM, toolchain=e2sim_toolchain, work_dir=tmp_path / "rec", record=rec) as sim:
        sim["hmi.BTN_POWER"].press(ms=300)
        sim.run(s=0.8)
        sim["hmi.BTN_POWER"].press(ms=100)
        sim.run(s=0.5)
        sim.model("motor.Motor").load = 1.4
        sim.run(s=2)
        expected = sim.trace_digest()
    _, same = replay(rec, work_dir=tmp_path / "same")
    assert same
    other = OTHER.get(e2sim_toolchain or "host32")
    if other:
        r, same = replay(rec, toolchain=other, work_dir=tmp_path / "other")
        assert same and r.trace_digest() == expected, f"same outputs on {other}: portable firmware"


@e2sim.requirement("E2SIM-REPLAY-03")
def test_t12_replay_detects_a_difference(e2sim_board, e2sim_toolchain, tmp_path):
    rec = tmp_path / "hmi.e2simrec"
    with e2sim.Sim(e2sim_board, toolchain=e2sim_toolchain, work_dir=tmp_path / "rec", record=rec) as sim:
        boot(sim)
        fan_on(sim)
        key(sim, "BTN_PLUS")
    data = bytearray(rec.read_bytes())
    marker = bytes([0x20, 1]) + (1).to_bytes(2, "little") + (1).to_bytes(4, "little")  # REC_IN GPIO BTN_PLUS = 1
    pos = data.rfind(marker)
    assert pos > 0
    data[pos + 4:pos + 8] = (0).to_bytes(4, "little")  # the last PLUS press removed
    rec.write_bytes(bytes(data))
    _, same = replay(rec, work_dir=tmp_path / "replay")
    assert not same, "a different input gives different outputs"
