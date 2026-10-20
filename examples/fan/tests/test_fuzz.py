"""Fuzzing of the frame parsers of both firmwares (fanProto): no crash, no hang, no reset, invariants kept."""

from pathlib import Path

import e2sim
from e2sim import fuzz
from fan_helpers import boot, fan_on

MOTOR = Path(__file__).parent.parent / "sim" / "motor.board.yaml"
SOF = 0xA5


def frame(cmd: int, payload: bytes) -> bytes:
    crc = 0
    for b in bytes([cmd, len(payload)]) + payload:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return bytes([SOF, cmd, len(payload)]) + payload + bytes([crc])


@e2sim.requirement("E2SIM-FUZZ-01")
def test_t20_fuzz_hmi_status_parser(sim, tmp_path):
    """Mutated status frames and noise on the motor link of the HMI (the model keeps answering)."""
    boot(sim)
    fan_on(sim)
    corpus = [frame(0x81, bytes([0x58, 0x02, 0])), frame(0x81, bytes([0xB0, 0x04, 2])), frame(0x01, b"\x00\x00\x00")]
    res = fuzz.stream(sim, "UART_LINK", corpus=corpus, frames=3000, seed=7, every_ms=2,
                      check=lambda: sim.var("app.speedLevel") in range(1, 6), save=tmp_path / "hmi.fuzz")
    assert res.ok, res.report()
    assert sim.var("s_parser.errors") > 100, "bad frames counted and dropped"
    sim.run(s=1)
    assert not sim.var("app.fault") & 1, "the link recovers after the noise"


@e2sim.requirement("E2SIM-FUZZ-01")
def test_t20_fuzz_motor_set_parser(e2sim_toolchain, tmp_path):
    """Mutated set points on the motor board alone: the duty stays in range, the protections hold."""
    with e2sim.Sim(MOTOR, toolchain=e2sim_toolchain, work_dir=tmp_path) as sim:
        sim["ENABLE"].set(1)
        sim.run(s=0.5)
        corpus = [frame(0x01, bytes([0xB0, 0x04, 1])), frame(0x01, bytes([0x08, 0x07, 1])), frame(0x01, b"\x00\x00\x00")]
        res = fuzz.stream(sim, "UART_LINK", corpus=corpus, frames=2000, seed=3, every_ms=3,
                          check=lambda: 0 <= sim["PWM_MOTOR"].value <= 1000)
        assert res.ok, res.report()
        assert sim.var("s_parser.errors") > 50
        assert len(sim["UART_LINK"].data) > 0, "valid frames among the mutations were answered"


@e2sim.requirement("E2SIM-FUZZ-02")
def test_t20_fuzz_reports_a_failure(sim):
    """The harness itself: a failing check stops the run and keeps the input."""
    boot(sim)
    stop = sim.now + 0.1
    res = fuzz.stream(sim, "UART_LINK", frames=50, seed=1, check=lambda: sim.now < stop)
    assert not res.ok and "check failed" in res.report() and res.history
    assert res.frames == len(res.history) < 50
