# e2Sim reference

Command line, configuration files, Python API, pytest plugin and target API. Tutorial:
[porting a firmware](tutorial/porting.en.md). Design: [SPEC.md](SPEC.md) (French).

## Command line

`e2sim <command>` (installed package) or `python e2sim_cli.py <command>` (repository). Exit code: 0 ok, 1 failure,
2 error.

| Command | Use |
|---|---|
| `run BOARD [--toolchain T] [--duration S] [--power-on] [--snapshot PORT[=file.png]] [--connect PORT]` | run a board or a system, as fast as possible for `--duration` virtual seconds, else in real time (Ctrl+C) |
| `gui BOARD [--port 8080] [--power-on] [--no-browser] [--toolchain T]` | web GUI, real time ×0.1 / ×1 / ×10 / max, pause, step |
| `connect BOARD [--port 47600] [--power-on]` | wait for a runner started by the debugger, then real time |
| `replay FILE.e2simrec [--toolchain T] [--connect PORT]` | send a record again, check the outputs are the same (exit 1 if not) |
| `license [status\|choose\|activate [KEY]\|deactivate\|check\|buy\|portal]` | license |
| `toolchain list` / `toolchain mk [NAME] --dir DIR` | toolchains of `e2sim_toolchains.yaml` / fragment for make |
| `coverage BUILD_DIR [--sources DIR] [--html DIR]` | coverage of the firmware (build `COVERAGE=1`, then run the tests): summary + annotated HTML |
| `extract (--make CMD [--cwd DIR] \| --compdb FILE) --name NAME [--exclude GLOB]… [--adapter DIR]… [--drop-define NAME]… [--out FILE]` | sources, `-I`, `-D` of the target build (dry run `make -n -B -w`, or compile_commands.json) → make fragment `NAME_SRCS / _INCS / _DEFS` + `e2sim_firmware` call; MCU HAL / BSP excluded by glob, adapter sources added |
| `root` | directory of the SDK (`target/`, `mk/`): `E2SIM_ROOT` of the makefiles |
| `fs mkdir\|rm PATHS` | portable file operations for the makefiles |

Environment: `E2SIM_TOOLCHAINS` (toolchain file), `E2SIM_TOOLCHAIN` (default toolchain of a `Sim`),
`E2SIM_UPDATE_REFS=1` (rewrite reference images), `E2SIM_LICENSE_KEY`, `E2SIM_NO_DIALOG=1`, `E2SIM_NO_GUI=1`.

## e2sim_toolchains.yaml

```yaml
python: C:/Dev/Tools/Python312/python.exe   # optional: Python of the makefiles (default: the one running e2sim)
toolchains:
  host32: { arch: i686,   prefix: C:/Dev/Tools/msys64/mingw32/bin/, path: [C:/Dev/Tools/msys64/mingw32/bin] }
  host64: { arch: x86_64, prefix: C:/Dev/Tools/msys64/ucrt64/bin/,  path: [C:/Dev/Tools/msys64/ucrt64/bin] }
default: host32
```

Search: `E2SIM_TOOLCHAINS`, then `e2sim_toolchains.yaml` in the current directory and its parents, then
`~/.e2sim/e2sim_toolchains.yaml`. Choice: command line (`TOOLCHAIN=`, `--toolchain`, `--e2sim-toolchain`), then
`toolchain:` of the board, then `default:`.

## Makefile (mk/e2sim.mk)

```make
E2SIM_ROOT := $(shell e2sim root)
include $(E2SIM_ROOT)/mk/e2sim.mk
$(eval $(call e2sim_firmware,NAME,SOURCES,INCLUDE_DIRS,DEFINES))
```

Builds `$(BUILD)/<toolchain>/NAME.dll` (+ `.map`) and `e2sim_runner.exe`. Variables: `TOOLCHAIN`, `COVERAGE=1` (gcov
counters, written at each unload of the DLL and added up; the DLLs are rebuilt when the options change), `BUILD` (default
`build`), `E2SIM_CFLAGS` (default `-std=c11 -g3 -O0 -funsigned-char` + warnings), `E2SIM_DLL_BASE` (default
`0x10000000`). The sources are built with `-Dmain=e2sim_app_main` and `-DE2SIM_DLL_BASE=…`. `$(E2SIM_FIRMWARES)`
lists the declared firmwares.

## board.yaml

| Key | Default | Meaning |
|---|---|---|
| `name` | file name | name of the instance |
| `firmware` | required | DLL; `{toolchain}` is replaced by the toolchain name |
| `runner` | next to the DLL | `e2sim_runner.exe` |
| `toolchain` | | toolchain of this board |
| `quantum_ms` | 1 | synchronisation step host ↔ firmware |
| `cpu: { yield_cost_ns }` | 1000 | virtual time of one yield point (busy waits progress) |
| `reset` | `in_process` | `in_process`: DLL reloaded; `process`: new runner process at each reset |
| `power: { mode, button, hold, hold_ms }` | `auto` | `auto`: on at start; `latch`: on while `button` (input) or `hold` (output) is 1, kept `hold_ms` (10); `manual` |
| `ports` | | see below |
| `models` | | `- { class: module.Class, name, ports: { attr: PORT }, params: { … } }` |
| `escope: { port, period_us, enabled }` | auto port, 1000, true | eScope V3 endpoint of the host |
| `gui: { skin, widgets: [ { port, at, size, label, widget, range, zoom } ] }` | | `skin`: image of the product (SVG or PNG, relative to the board); a widget with `at: [x, y]` (center, pixels of the image) and `size: [w, h]` is placed on it: display, key (input bit, hold to press), LED (output bit). Without `at`: hints for the panel (`widget: switch`, slider `range`, display `zoom`) |

Ports:

| Key | Meaning |
|---|---|
| `class` | `GPIO`, `ADC`, `PWM`, `CAPTURE`, `VALUE`, `UART`, `SPI`, `I2C`, `BLOCK`, `EVENT` |
| `idx` | index in the HAL: number, enum constant or `#define` (DWARF, `-g3`) |
| `type` | `bit`, `value`, `stream`, `xfer`, `block`, `event` (default from the class) |
| `dir` | `in` (default), `out`, `io` |
| `default` | initial value of an input |
| `framebuffer: { w, h, format }` | block shown as a display (`RGB565`) |
| `size`, `persist`, `fill` | block size; persistent in `<work_dir>/<instance>.<port>.nvm.bin`; erased value (0xFF) |
| `cost_ns` | virtual time of an `xfer` transaction |
| `tcp` | stream relayed to a local TCP server (0: automatic port) |
| `baud` | stream line rate (10 bits per byte), both directions |

## system.yaml

```yaml
instances:
  hmi:   { board: hmi.board.yaml }
  motor: { board: motor.board.yaml }
links:
  - [hmi.UART_LINK, motor.UART_LINK]   # stream <-> stream
  - [hmi.MOTOR_EN, motor.ENABLE]       # output -> input (bit, value, event)
```

A model bound to a linked port is not created. Outputs reach the other instance at the next quantum.

## Python API

```python
import e2sim
sim = e2sim.Sim("board.yaml" or "system.yaml", toolchain=None, work_dir=None, connect=None, timeout_s=10,
                record=None, reset_mode=None)
```

| `Sim` | |
|---|---|
| `start()`, `stop()`, context manager | runners started (automatic at the first access) / stopped |
| `run(s=, ms=, us=, fixed=False)` | run (long runs: several quanta per round trip, same result as `fixed=True`) |
| `run_until(cond, timeout_s=10, desc="")` | quantum by quantum until `cond()`; `SimTimeout` (an `AssertionError`) |
| `step()`, `run_realtime(speed=1, duration_s=None)`, `at(t_ns, fn)` | one quantum / real time / action at a virtual time |
| `now`, `now_ns` | virtual time |
| `sim["PORT"]`, `sim["inst.PORT"]` | `Port` |
| `var(expr)`, `set_var(expr, v)`; `"inst:expr"` with a system | firmware variable by C expression (gdb), read / written between two quanta |
| `model("Name")`, `model("inst.Name")` | model instance |
| `instance(name=None)` | `InstanceState`: same API for one firmware of a system (`[]`, `var`, `model`, `power_on`, `resets`, `symbols`, `escope`) |
| `power_on()`, `power_off()`, `reset(cause="host")`, `powered`, `resets`, `logs` | one firmware |
| `trace`, `trace_digest()` | every output, stream, reset, power event / its hash |

`e2sim.sim.replay(path, toolchain=None, work_dir=None, connect=None) -> (Sim, same)`.

`e2sim.fuzz.stream(sim, port, corpus=None, frames=1000, seed=1, every_ms=5, random_ratio=0.2, max_len=32,
check=None, resets_allowed=False, save=None) -> FuzzResult`: deterministic random or mutated frames (bit flip,
byte replaced / inserted / deleted, truncation, duplication) written on a stream port; stops at the first crash,
loop without yield point, unexpected reset or failed `check()`. `FuzzResult.ok`, `.report()`, `.history`
(inputs), `save=` writes them (hex, one per line). With `Sim(record=…)` the run replays exactly.

| `Port` | |
|---|---|
| `value`, `get()`, `set(v)`, `press(ms=100, value=1)` | bit / value; `==`, `int()`, `bool()` |
| `force(v)`, `release()`, `forced` | override of an input, even driven by a model |
| `history` | `(t_ns, value)` of the changes of an output |
| `write(data)`, `data`, `text`, `clear()`, `relay`, `rx_q` | stream (bytes to the firmware / written by it) |
| `fire()` | event to the firmware |
| `read_block(off, n)`, `write_block(off, data)` | block (NVM fault injection…) |
| `rgb()`, `save_png(path, scale=1)`, `assert_matches(ref, max_diff_pixels=0)` | display; reference relative to the calling file, created when missing |
| `responder` | `fn(tx) -> rx` for an `xfer` without model |

| `Model` | |
|---|---|
| `Bit()`, `Value()`, `Stream()`, `Xfer()`, `Block()`, `Event()` | ports of the model, bound by `board.yaml` |
| `Param(default, doc)` | parameter (board `params:`, scripts, GUI) |
| `@e2sim.every(ms=, us=, s=)` | periodic method, virtual time |
| `on_<port>(value \| data \| tx)`, `on_rx(data)`, `on_xfer(tx) -> bytes \| (bytes, cost_ns)` | callbacks |
| `setup()`, `on_reset(cause)`, `on_power(on)`, `now`, `now_ns`, `params` | |

## pytest plugin

Registered by the package (`pytest11`), or `pytest_plugins = ["e2sim.pytest_plugin"]` in a conftest.

| | |
|---|---|
| fixture `e2sim_board` | to provide: path of the board / system of the tests |
| fixture `sim` | started `Sim` of `e2sim_board`, NVM in `tmp_path` |
| fixture `e2sim_toolchain` | value of `--e2sim-toolchain` |
| `@e2sim.requirement("REQ-1", …)` | requirements of the test (JUnit property, Excel report) |
| `--e2sim-toolchain T` | toolchain of the firmware |
| `--e2sim-update-refs` | rewrite the reference images |
| `--e2sim-record DIR` | one `.e2simrec` per test |
| `--e2sim-xlsx FILE` | Excel report: Summary, Tests, Requirements |

## GUI JSON API

`GET /api/layout`, `GET /api/state`, `POST /api/cmd` with `{"op": …}`: `run`, `pause`, `step`, `speed` (`value`,
0 = max), `set` / `press` / `force` / `release` (`port`, `value`, `ms`), `write` / `clear` (`port`, `text`),
`param` (`model`, `name`, `value`), `power` (`instance`, `on`), `reset` (`instance`), `var` (`expr`), `state`,
`note` (`text`), `quit`.

## Target API (e2sim.h)

| Function | |
|---|---|
| `e2sim_yield()` | yield point, start of every HAL function (no effect in interrupt) |
| `e2sim_idle()` | WFI: jump to the next event |
| `e2sim_time_ns()` | virtual time |
| `e2sim_reset(cause)`, `e2sim_reset_cause()` | reset (end of the ISR when called from one) / cause of the last one |
| `e2sim_in(cls, idx)`, `e2sim_out(cls, idx, v)`, `e2sim_event_out(idx)` | bit / value ports, events |
| `e2sim_stream_read(idx, buf, max)`, `e2sim_stream_write(idx, buf, n)` | UART streams |
| `e2sim_xfer(cls, idx, tx, n, rx, max)` | synchronous transaction, answered by a model |
| `e2sim_block(idx, size)` | shared block (NVM file, frame buffer) |
| `e2sim_timer_start(period_ns, periodic, isr, ctx)`, `e2sim_timer_stop(t)` | timers |
| `e2sim_on_input(cls, idx, isr, ctx)` | interrupt on an input change, a reception, an event |
| `e2sim_irq_disable()`, `e2sim_irq_enable()` | critical sections |
| `e2sim_mem_valid(ptr, size, write)` | memory check (eScope embedded: `ESCOPE_ADDR_IS_VALID`) |
| `e2sim_log(level, fmt, …)` | log to the host |
| `E2SIM_YIELD()` | yield point in a busy loop without HAL call |
