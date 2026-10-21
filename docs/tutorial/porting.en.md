# Porting a firmware to e2Sim

**English** | [Français](porting.fr.md)

Goal: run your firmware on the PC **without changing its code**, test it with pytest, show it in the web GUI and
debug it in VS Code. Only the lowest layer, the implementation of your HAL for the MCU, is replaced. The complete
example used below is [fan-demo](https://github.com/laurentolive/fan-demo).

Time: a few hours for a firmware on a HAL already adapted; one more day the first time for a new family of HAL.

## 0. Before you start

- Install the tools (see the [README](../../README.md)): MSYS2 gcc + gdb, GNU make, Python 3.10+, e2Sim.
- Check that your firmware goes through a HAL for **every** hardware access. Direct register accesses
  (`GPIOA->ODR = …`) in the application are found at link time (missing symbols): move them into the HAL first,
  this is good for the target too.
- The firmware is a **superloop** (`main()` with `while (1)`) with interrupts. No RTOS for now.

## 1. The HAL adapter (once per family of HAL)

Write one C file per module of your HAL, next to the implementations of the MCUs (for example
`Hw/MCU/E2SIM/`). Each function:

1. starts with `e2sim_yield()`: it is the point where the simulator takes the hand back (interrupts, time);
2. calls the API of [`e2sim.h`](../../target/include/e2sim.h).

```c
#include "halGpio.h"
#include "e2sim.h"

bool halGpio_Read(halGpio_t pin)
{
    e2sim_yield();
    return e2sim_in(E2SIM_GPIO, (uint16_t)pin) != 0;
}

void halGpio_Write(halGpio_t pin, bool level)
{
    e2sim_yield();
    e2sim_out(E2SIM_GPIO, (uint16_t)pin, level ? 1 : 0);
}
```

Mapping of the usual modules (complete model: [port/e2sim of fan-demo](https://github.com/laurentolive/fan-demo/tree/master/port/e2sim)):

| HAL | e2Sim |
|---|---|
| GPIO read / write | `e2sim_in` / `e2sim_out(E2SIM_GPIO, …)` |
| ADC read (raw points) | `e2sim_in(E2SIM_ADC, ch)` |
| PWM duty | `e2sim_out(E2SIM_PWM, ch, duty)` |
| input capture | `e2sim_in(E2SIM_CAPTURE, ch)` |
| periodic timer + callback | `e2sim_timer_start(period_ns, true, isr, ctx)` |
| free running counter (us) | `e2sim_time_ns() / 1000` |
| UART write / read (buffered) | `e2sim_stream_write` / `e2sim_stream_read` |
| SPI / I2C transfer that returns with the data | `e2sim_xfer(E2SIM_SPI, bus, tx, n, rx, n)` |
| external interrupt | `e2sim_on_input(E2SIM_EVENT, line, isr, ctx)` |
| EEPROM / flash | `e2sim_block(idx, size)` (persistent file), then `memcpy` |
| display frame buffer | `e2sim_block(idx, size)`, copied on "update" |
| watchdog | one shot `e2sim_timer_start`, restarted by refresh; on expiry `e2sim_reset(E2SIM_RESET_WDT)` |
| WFI / idle | `e2sim_idle()` |
| critical section | `e2sim_irq_disable()` / `e2sim_irq_enable()` |
| reset cause | `e2sim_reset_cause()` |

Rules:
- no product logic in the adapter: the battery voltage, the answer of a sensor… belong to the **models**;
- a busy loop that calls no HAL function never gives the hand back: call a HAL function in it, or
  `E2SIM_YIELD()` (empty on the target). e2Sim reports such a loop with its stack after 3 s.

## 2. The makefile

```make
E2SIM_ROOT := $(shell e2sim root)          # or the path of the e2Sim repository
include $(E2SIM_ROOT)/mk/e2sim.mk

SRCS := $(wildcard app/*.c) $(wildcard modules/*.c) $(wildcard Hw/MCU/E2SIM/*.c)   # no MCU HAL, no BSP
INCS := app modules header Hw/MCU/E2SIM
$(eval $(call e2sim_firmware,my_product,$(SRCS),$(INCS),MY_DEFINE=1))

all: $(E2SIM_FIRMWARES)
```

Faster, from the target build (nothing is compiled, no ARM compiler needed):

```
e2sim extract --make "make -C ../firmware" --exclude "*/Hw/MCU/*" --exclude "*/BSP/*" \n              --adapter Hw/MCU/E2SIM --name my_product --out e2sim_sources.mk
```

then `include e2sim_sources.mk` after `mk/e2sim.mk` (or `--compdb compile_commands.json`).

`make` builds, for the default toolchain of `e2sim_toolchains.yaml`, `build/host32/my_product.dll` and the runner.
`make TOOLCHAIN=host64` builds the 64 bits variant. Your `main()` is renamed `e2sim_app_main` by the build: the
sources are not touched.

## 3. board.yaml

It describes the ports (what the HAL exchanges), the models and the power supply:

```yaml
name: my_product
firmware: build/{toolchain}/my_product.dll
power: { mode: latch, button: BTN_POWER, hold: SELF_HOLD }   # or { mode: auto }

ports:
  BTN_POWER: { class: GPIO,  idx: HAL_GPIO_BTN_POWER, type: bit, dir: in }
  SELF_HOLD: { class: GPIO,  idx: HAL_GPIO_SELF_HOLD, type: bit, dir: out }
  VBAT:      { class: ADC,   idx: HAL_ADC_VBAT,       type: value, dir: in }
  SENSOR:    { class: SPI,   idx: HAL_SPI_SENSOR,     type: xfer, cost_ns: 30000 }
  DEBUG:     { class: UART,  idx: HAL_UART_DEBUG,     type: stream, tcp: 0 }
  LCD:       { class: BLOCK, idx: 0, type: block, framebuffer: { w: 128, h: 64, format: RGB565 } }
  EEPROM:    { class: BLOCK, idx: 1, type: block, size: 2048, persist: true }

models:
  - { class: models.battery.Battery, ports: { adc: VBAT } }
```

`idx` takes the **names of your HAL** (enum constants, or `#define` thanks to `-g3`): e2Sim reads their values in the
debug information of the DLL. Nothing is generated in the firmware. All the keys: [reference](../reference.md#boardyaml).

## 4. A first run

```
e2sim run board.yaml --power-on --duration 2 --snapshot LCD=out/lcd.png
e2sim gui board.yaml                   # http://127.0.0.1:8080/
```

The console prints the logs, the eScope port of the firmware, and the TCP ports of the relayed UARTs.

## 5. Models

A model gives the data the HAL expects (no physics):

```python
import e2sim

class Battery(e2sim.Model):
    adc = e2sim.Value()                       # bound by board.yaml: ports: { adc: VBAT }
    voltage_V = e2sim.Param(12.0)             # changeable from a test or the GUI

    @e2sim.every(ms=10)
    def step(self):
        self.adc.set(round(self.voltage_V / 15.0 * 4095))     # ADC points

class Sensor(e2sim.Model):
    spi = e2sim.Xfer()
    def on_spi(self, tx: bytes) -> bytes:     # synchronous: the HAL transfer returns with these bytes
        return bytes([0, 0x01, 0x2C])
```

Callbacks: `on_<port>(value)` for an output of the firmware, `on_<port>(data)` for a stream, `on_<port>(tx)` for a
transaction, `@e2sim.every(...)` for a period, `on_reset(cause)`, `on_power(on)`.

## 6. Tests

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def e2sim_board():
    return Path(__file__).parent.parent / "board.yaml"
```

```python
# tests/test_power.py
import e2sim

@e2sim.requirement("PRD-PWR-01")
def test_power_on(sim):
    sim["BTN_POWER"].press(ms=300)
    sim.run(s=1)
    assert sim["SELF_HOLD"] == 1
    assert sim.var("app.state") == 2           # any variable of the firmware, by its C expression
    sim.model("Battery").voltage_V = 9.0       # fault injection through the model
    sim["VBAT"].force(0)                       # or over it
    sim.run(s=1)
    sim["LCD"].assert_matches("ref/low_battery.png")
```

```
pytest tests --e2sim-toolchain host32 --junitxml out/junit.xml --e2sim-xlsx out/report.xlsx
pytest tests --e2sim-record out/rec    # then: e2sim replay out/rec/<test>.e2simrec
```

Same result run after run, and on both architectures: a difference between `host32` and `host64` shows a non
portable code (pointer stored in a 32 bits integer…).

## 7. Debug

1. `e2sim gui board.yaml --connect 47600 --power-on` (the GUI waits for the firmware; `e2sim connect` without GUI);
2. launch `build/host32/e2sim_runner.exe --dll build/host32/my_product.dll --host 127.0.0.1:47600 --connect-timeout 0`
   under gdb, in any order (VS Code compound configuration: [.vscode of fan-demo](https://github.com/laurentolive/fan-demo/tree/master/.vscode)).
   The GUI ends with the debug session.

Virtual time stops on a breakpoint: no timeout, the whole system is frozen. Breakpoints survive a reset.

## 8. Several boards

```yaml
# system.yaml
instances:
  hmi:   { board: hmi.board.yaml }
  motor: { board: motor.board.yaml }
links:
  - [hmi.UART_LINK, motor.UART_LINK]
  - [hmi.MOTOR_EN, motor.ENABLE]
```

A linked firmware replaces the model of the port. In the tests: `sim["motor.PWM"]`, `sim.var("motor:ctrl.duty")`,
`sim.model("motor.Motor")`.

## Common problems

| Symptom | Cause |
|---|---|
| `unknown symbols … HAL_…` | the name is not in the DWARF: enum not used by the code, or macro without `-g3` |
| `no yield point for 3 s` + stack | busy loop without HAL call: add one, or `E2SIM_YIELD()` |
| the firmware does not start (power latch) | `power: latch`: press the button long enough for the firmware to drive `hold` |
| leak at each reset | allocation at boot without free: `reset: process` in board.yaml |
| different results host32 / host64 | non portable code (`sizeof(void *)`, pointer in `uint32_t`) |
