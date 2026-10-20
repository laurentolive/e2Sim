"""Scenario helpers of the fan HMI tests."""


def boot(sim):
    """Press POWER until the firmware holds the power latch."""
    sim["BTN_POWER"].press(ms=300)
    sim.run_until(lambda: sim["SELF_HOLD"] == 1, timeout_s=1, desc="SELF_HOLD")
    sim.run(ms=500)


def fan_on(sim):
    sim["BTN_POWER"].press(ms=100)
    sim.run(ms=300)
    assert sim.var("app.running")


def key(sim, name, ms=100):
    sim[name].press(ms=ms)
    sim.run(ms=ms + 100)


def toggles(port, since_ns):
    return sum(1 for t, _ in port.history if t >= since_ns)
