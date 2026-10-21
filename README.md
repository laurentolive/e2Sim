# e2Sim

**English** | [Français](README.fr.md)

Embedded firmware simulation **on a PC**: the application code runs natively, **unchanged**, on top of a
simulated HAL, clocked by a **deterministic virtual time**, driven by test scripts, a web GUI or other firmwares.

- The firmware is built as a **DLL** (GCC MinGW, i686 or x86_64); its `main()` runs in a fiber of the generic
  **runner** `e2sim_runner.exe`, which owns time, interrupts and ports.
- Only the HAL changes: an **adapter** implements it on [`e2sim.h`](target/include/e2sim.h).
- The environment of the MCU (sensors, other board, battery…) is simulated by **Python models**, at the level of
  the data of the HAL (ADC points, bytes, duty cycles), not physics.
- A reset (software, watchdog) **reloads the DLL in the same process**: RAM and init as at boot, the debugger stays
  attached.
- **pytest** tests reproducible to the bit, in accelerated time; **record / replay** of any scenario.
- Several linked firmwares (`system.yaml`): a firmware replaces a model.
- **eScope** on every firmware without code in it (V3 endpoint of the host), TCP relay of any UART.

| Documents | |
|---|---|
| [Porting tutorial](docs/tutorial/porting.en.md) | port a firmware step by step |
| [Reference](docs/reference.md) | command line, `board.yaml`, Python API, pytest, `e2sim.h` |
| [Specification](docs/SPEC.md) (French) | architecture and decisions |
| [fan-demo](https://github.com/laurentolive/fan-demo) | example project, separate repository: tests every feature and demonstrates them |
| [Development environment](docs/dev-setup.md) | tools to develop e2Sim (Windows, WSL) |
| [Issues](https://github.com/laurentolive/e2Sim/issues) | work in progress |

## Layout

```
target/            runner + API e2sim.h (MIT): fiber, virtual time, timers, IRQ, ports, reset, memory
e2sim/             Python host: Sim, models, board.yaml, symbols (gdb), pytest plugin, web GUI, CLI
mk/e2sim.mk        make rules: runner + firmware DLL for the selected toolchain
e2sim_cli.py       entry point from the repository (python e2sim_cli.py --help)
selftest/          self-tests of the runner
e2sim_toolchains.yaml.example   toolchains of the machine (template)
```

## Requirements

- Windows, or Linux (tested on Debian 13 in WSL: gcc, gdb, `gcc-multilib`), Python 3.10+ with `pyyaml`, `pytest`
  (`openpyxl` for the Excel report). On Linux the firmware is a `.so`, and a toolchain with
  `-fsanitize=address,undefined` runs the whole campaign under the sanitizers (memory errors reported with their stack).
- GNU make, MSYS2 with `mingw-w64-i686-gcc`, `mingw-w64-i686-gdb` (host32) and/or `mingw-w64-ucrt-x86_64-gcc`,
  `mingw-w64-ucrt-x86_64-gdb` (host64). gdb is also used by the host (symbols, `sim.var()`).
- Copy `e2sim_toolchains.yaml.example` to `e2sim_toolchains.yaml` (in the project, in `~/.e2sim/`, or set
  `E2SIM_TOOLCHAINS`) with the paths of the machine.

## Installation

From the repository: nothing to install, `python e2sim_cli.py …`, `E2SIM_ROOT` = root of the repository.

As a package (`e2sim` command, pytest plugin, SDK `target/` + `mk/` in `<prefix>/share/e2sim`):

```
pip install "e2sim[test,report] @ git+https://github.com/laurentolive/e2Sim"
e2sim --version
e2sim root          # SDK directory: E2SIM_ROOT of the makefiles
```

## Quick start

The example project is [fan-demo](https://github.com/laurentolive/fan-demo) (two boards, every feature, demonstration):

```
git clone https://github.com/laurentolive/fan-demo.git && cd fan-demo
python tools/fetch.py   # e2Sim at the version of tools.lock.yaml
make test-all           # host32 and host64 (linux32 and linux64 on Linux)
make demo               # demonstration in the web GUI, chapter by chapter
make E2SIM_ROOT=../e2Sim test-all   # against a working copy of e2Sim
```

```python
def test_power_on(sim):                  # fixture of the e2sim pytest plugin
    sim["BTN_POWER"].press(ms=300)
    sim.run(s=1)
    assert sim["SELF_HOLD"] == 1
    assert sim.var("app.speedLevel") == 1
    sim["LCD"].assert_matches("ref/home.png")
```

## Debug (VS Code)

`e2sim gui board.yaml --connect 47600` waits for the runner started by the debugger
(`e2sim_runner --dll … --host 127.0.0.1:47600 --connect-timeout 0`) and ends with the debug session; the
breakpoints of the firmware stay valid after a reset. Ready-made configurations (one F5 starts the GUI and the
firmware): `.vscode/` of [fan-demo](https://github.com/laurentolive/fan-demo).

## License

`e2sim license` shows the license; `e2sim license choose | activate [KEY] | deactivate | check | buy | portal`.
Checked when `run`, `gui`, `connect`, `replay` start and once per pytest session; it never blocks a simulation
(Demonstration by default). In CI: no dialog, key in `E2SIM_LICENSE_KEY`. `E2SIM_NO_DIALOG=1` removes the dialogs,
`E2SIM_NO_GUI=1` forces the console.

PC tool (`e2sim/`, `mk/`, `docs/`): [PolyForm Noncommercial 1.0.0](LICENSE.md) + commercial license.
`target/`: MIT (compiled with the firmware, free to copy).
