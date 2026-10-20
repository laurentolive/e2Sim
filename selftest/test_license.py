"""Licence: never blocks; without dialog (CI), a Demonstration licence is started."""

import os


def test_license_demonstration(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("E2SIM_NO_DIALOG", "1")
    monkeypatch.delenv("E2SIM_LICENSE_KEY", raising=False)
    from e2sim.license import check_at_startup

    text = check_at_startup()
    assert text.startswith("Demonstration License"), text
    assert any(p.name.startswith("license") for p in (tmp_path / ("e2Sim" if os.name == "nt" else "e2sim")).iterdir())
    assert check_at_startup() == text, "a Demonstration already started is reloaded, never restarted"
