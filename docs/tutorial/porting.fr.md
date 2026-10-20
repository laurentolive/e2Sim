# Porter un firmware sur e2Sim

[English](porting.en.md) | **Français**

But : faire tourner votre firmware sur le PC **sans modifier son code**, le tester avec pytest, le montrer dans
la GUI web et le déboguer dans VS Code. Seule la couche la plus basse, l'implémentation de votre HAL pour le
MCU, est remplacée. L'exemple complet utilisé ci-dessous est [examples/fan](../../examples/fan).

Durée : quelques heures pour un firmware sur une HAL déjà adaptée ; une journée de plus la première fois, pour
une nouvelle famille de HAL.

## 0. Avant de commencer

- Installer les outils (voir le [README](../../README.fr.md)) : gcc + gdb MSYS2, GNU make, Python 3.10+, e2Sim.
- Vérifier que le firmware passe par la HAL pour **tout** accès matériel. Un accès registre direct
  (`GPIOA->ODR = …`) dans l'application se voit au link (symbole manquant) : le déplacer d'abord dans la HAL,
  c'est aussi mieux pour la cible.
- Le firmware est une **superloop** (`main()` avec `while (1)`) avec des interruptions. Pas de RTOS pour l'instant.

## 1. L'adaptateur de la HAL (une fois par famille de HAL)

Écrire un fichier C par module de la HAL, à côté des implémentations des MCU (par exemple `Hw/MCU/E2SIM/`).
Chaque fonction :

1. commence par `e2sim_yield()` : c'est le point où le simulateur reprend la main (interruptions, temps) ;
2. appelle l'API de [`e2sim.h`](../../target/include/e2sim.h).

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

Correspondance des modules usuels (modèle complet : [examples/fan/hal_e2sim](../../examples/fan/hal_e2sim)) :

| HAL | e2Sim |
|---|---|
| lecture / écriture GPIO | `e2sim_in` / `e2sim_out(E2SIM_GPIO, …)` |
| lecture ADC (points bruts) | `e2sim_in(E2SIM_ADC, ch)` |
| rapport cyclique PWM | `e2sim_out(E2SIM_PWM, ch, duty)` |
| capture d'entrée | `e2sim_in(E2SIM_CAPTURE, ch)` |
| timer périodique + callback | `e2sim_timer_start(période_ns, true, isr, ctx)` |
| compteur libre (µs) | `e2sim_time_ns() / 1000` |
| écriture / lecture UART (bufferisée) | `e2sim_stream_write` / `e2sim_stream_read` |
| transfert SPI / I2C qui retourne avec la donnée | `e2sim_xfer(E2SIM_SPI, bus, tx, n, rx, n)` |
| interruption externe | `e2sim_on_input(E2SIM_EVENT, ligne, isr, ctx)` |
| EEPROM / flash | `e2sim_block(idx, taille)` (fichier persistant), puis `memcpy` |
| frame buffer d'écran | `e2sim_block(idx, taille)`, copié à « update » |
| watchdog | `e2sim_timer_start` one shot, relancé au refresh ; à l'échéance `e2sim_reset(E2SIM_RESET_WDT)` |
| WFI / idle | `e2sim_idle()` |
| section critique | `e2sim_irq_disable()` / `e2sim_irq_enable()` |
| cause du reset | `e2sim_reset_cause()` |

Règles :
- aucune logique produit dans l'adaptateur : la tension batterie, la réponse d'un capteur… sont dans les **modèles** ;
- une boucle d'attente qui n'appelle aucune fonction de la HAL ne rend jamais la main : y appeler une fonction
  de la HAL, ou `E2SIM_YIELD()` (vide sur cible). e2Sim signale une telle boucle avec sa pile au bout de 3 s.

## 2. Le makefile

```make
E2SIM_ROOT := $(shell e2sim root)          # ou le chemin du dépôt e2Sim
include $(E2SIM_ROOT)/mk/e2sim.mk

SRCS := $(wildcard app/*.c) $(wildcard modules/*.c) $(wildcard Hw/MCU/E2SIM/*.c)   # ni HAL MCU ni BSP
INCS := app modules header Hw/MCU/E2SIM
$(eval $(call e2sim_firmware,mon_produit,$(SRCS),$(INCS),MON_DEFINE=1))

all: $(E2SIM_FIRMWARES)
```

`make` produit, pour la toolchain par défaut de `e2sim_toolchains.yaml`, `build/host32/mon_produit.dll` et le
runner. `make TOOLCHAIN=host64` produit la variante 64 bits. Votre `main()` est renommé `e2sim_app_main` par le
build : les sources ne sont pas touchées.

## 3. board.yaml

Il décrit les ports (ce qu'échange la HAL), les modèles et l'alimentation :

```yaml
name: mon_produit
firmware: build/{toolchain}/mon_produit.dll
power: { mode: latch, button: BTN_POWER, hold: SELF_HOLD }   # ou { mode: auto }

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

`idx` prend les **noms de votre HAL** (constantes d'enum, ou `#define` grâce à `-g3`) : e2Sim lit leur valeur
dans les informations de debug de la DLL. Rien n'est généré dans le firmware. Toutes les clés :
[référence](../reference.md#boardyaml).

## 4. Premier lancement

```
e2sim run board.yaml --power-on --duration 2 --snapshot LCD=out/lcd.png
e2sim gui board.yaml                   # http://127.0.0.1:8080/
```

La console affiche les logs, le port eScope du firmware et les ports TCP des UART relayées.

## 5. Modèles

Un modèle fournit les données qu'attend la HAL (pas de physique) :

```python
import e2sim

class Battery(e2sim.Model):
    adc = e2sim.Value()                       # relié par board.yaml : ports: { adc: VBAT }
    voltage_V = e2sim.Param(12.0)             # modifiable depuis un test ou la GUI

    @e2sim.every(ms=10)
    def step(self):
        self.adc.set(round(self.voltage_V / 15.0 * 4095))     # points ADC

class Sensor(e2sim.Model):
    spi = e2sim.Xfer()
    def on_spi(self, tx: bytes) -> bytes:     # synchrone : le transfert de la HAL retourne avec ces octets
        return bytes([0, 0x01, 0x2C])
```

Callbacks : `on_<port>(valeur)` pour une sortie du firmware, `on_<port>(data)` pour un stream, `on_<port>(tx)`
pour une transaction, `@e2sim.every(...)` pour une période, `on_reset(cause)`, `on_power(on)`.

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
    assert sim.var("app.state") == 2           # n'importe quelle variable du firmware, par son expression C
    sim.model("Battery").voltage_V = 9.0       # injection de faute par le modèle
    sim["VBAT"].force(0)                       # ou par-dessus
    sim.run(s=1)
    sim["LCD"].assert_matches("ref/low_battery.png")
```

```
pytest tests --e2sim-toolchain host32 --junitxml out/junit.xml --e2sim-xlsx out/report.xlsx
pytest tests --e2sim-record out/rec    # puis : e2sim replay out/rec/<test>.e2simrec
```

Même résultat d'un lancement à l'autre, et dans les deux architectures : un écart entre `host32` et `host64`
révèle un code non portable (pointeur rangé dans un entier 32 bits…).

## 7. Debug

1. `e2sim connect board.yaml --port 47600 --power-on` (le host attend le firmware) ;
2. lancer `build/host32/e2sim_runner.exe --dll build/host32/mon_produit.dll --host 127.0.0.1:47600 --connect-timeout 0`
   sous gdb (configuration VS Code : [examples/fan/.vscode](../../examples/fan/.vscode)).

Le temps virtuel s'arrête sur un breakpoint : pas de timeout, tout le système est figé. Les breakpoints survivent
à un reset.

## 8. Plusieurs cartes

```yaml
# system.yaml
instances:
  hmi:   { board: hmi.board.yaml }
  motor: { board: motor.board.yaml }
links:
  - [hmi.UART_LINK, motor.UART_LINK]
  - [hmi.MOTOR_EN, motor.ENABLE]
```

Un firmware relié remplace le modèle du port. Dans les tests : `sim["motor.PWM"]`, `sim.var("motor:ctrl.duty")`,
`sim.model("motor.Motor")`.

## Problèmes courants

| Symptôme | Cause |
|---|---|
| `unknown symbols … HAL_…` | le nom n'est pas dans le DWARF : enum non utilisé par le code, ou macro sans `-g3` |
| `no yield point for 3 s` + pile | boucle d'attente sans appel HAL : en ajouter un, ou `E2SIM_YIELD()` |
| le firmware ne démarre pas (verrou d'alimentation) | `power: latch` : appuyer assez longtemps pour que le firmware tienne `hold` |
| fuite à chaque reset | allocation au boot sans libération : `reset: process` dans board.yaml |
| résultats différents host32 / host64 | code non portable (`sizeof(void *)`, pointeur dans un `uint32_t`) |
