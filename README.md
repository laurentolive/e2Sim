# e2Sim

Simulation de firmware embarqué **sur PC** : le code applicatif tourne en natif, sans modification, au-dessus
d'une HAL simulée, cadencé par un **temps virtuel déterministe**, piloté par des scripts de test (et en V1 par
une GUI web et d'autres firmwares).

- Le firmware est compilé en **DLL** (GCC MinGW, i686 ou x86_64) ; son `main()` tourne dans une fiber du
  **runner** générique `e2sim_runner.exe`, qui gère le temps, les interruptions et les ports.
- Seule la HAL change : un **adaptateur** l'implémente sur [`e2sim.h`](target/include/e2sim.h).
- L'entourage du MCU (capteurs, carte voisine, batterie…) est simulé par des **modèles Python**, au niveau des
  données de la HAL.
- Un reset (logiciel, watchdog) **recharge la DLL dans le même process** : RAM et init du firmware comme au
  boot, le debugger reste attaché.
- Tests **pytest** reproductibles au bit près, en temps accéléré (runs longs équivalents au pas fixe).
- Plusieurs firmwares reliés (`system.yaml`) : un firmware remplace un modèle.
- **eScope** sur chaque instance sans code dans le firmware (endpoint V3 du host, port affiché par
  `e2sim run`), et relais TCP de n'importe quelle UART (`tcp:` dans `board.yaml`).

Spécification : [docs/SPEC.md](docs/SPEC.md). État : V0 terminée, V1 en cours (multi-firmware, eScope, relais TCP, GUI web faits ; record/replay, licence à venir).

## Arborescence

```
target/            runner + API e2sim.h (MIT) : fiber, temps virtuel, timers, IRQ, ports, reset, mémoire
e2sim/             host Python : Sim, modèles, board.yaml, symboles (gdb), plugin pytest, CLI
mk/e2sim.mk        règles make : runner + DLL firmware, toolchain issue du registre
e2sim_cli.py       point d'entrée (python e2sim_cli.py --help)
examples/fan/      firmware exemple (MIT) : HAL, adaptateur hal_e2sim, fan_hmi, modèles, tests
selftest/          autotests du runner
toolchains.yaml.example   registre de toolchains partagé avec e2Unit
```

## Prérequis

- Python 3.10+ avec `pyyaml`, `pytest`.
- GNU make, MSYS2 avec `mingw-w64-i686-gcc`, `mingw-w64-i686-gdb` (host32) et/ou `mingw-w64-ucrt-x86_64-gcc`,
  `mingw-w64-ucrt-x86_64-gdb` (host64). gdb sert aussi au host (symboles, `sim.var()`).
- Copier `toolchains.yaml.example` en `toolchains.yaml` (ou `~/.esquaresoft/toolchains.yaml`, ou variable
  `ESQ_TOOLCHAINS`) et y mettre les chemins de la machine.

## Démarrage rapide

```
cd examples/fan
make                       # toolchain par défaut du registre (host32)
make TOOLCHAIN=host64
make test                  # build + pytest
make test-all              # host32 et host64
python ../../e2sim_cli.py run sim/hmi.board.yaml --power-on --duration 2 --snapshot LCD=out/lcd.png
python ../../e2sim_cli.py gui sim/hmi.board.yaml       # GUI web : http://127.0.0.1:8080/
python ../../e2sim_cli.py gui sim/system.yaml          # les deux cartes
```

## Porter un firmware

1. **Adaptateur HAL** : chaque fonction de la HAL appelle `e2sim_yield()` puis l'API `e2sim.h`
   (modèle : [examples/fan/hal_e2sim](examples/fan/hal_e2sim)). Une fois par famille de HAL.
2. **Makefile** :
   ```make
   E2SIM_ROOT := <chemin vers e2Sim>
   include $(E2SIM_ROOT)/mk/e2sim.mk
   $(eval $(call e2sim_firmware,mon_produit,<sources sans HAL MCU ni BSP>,<includes>,<defines>))
   ```
3. **board.yaml** : ports (index = constantes d'enum de la HAL, résolues dans le DWARF), modèles, alimentation
   ([exemple](examples/fan/sim/hmi.board.yaml)).
4. **Modèles** Python (optionnel) et **tests** pytest ([exemple](examples/fan/tests/test_fan_hmi.py)).

```python
def test_power_on(sim):                  # fixture du plugin e2sim.pytest_plugin
    sim["BTN_POWER"].press(ms=300)
    sim.run(s=1)
    assert sim["SELF_HOLD"] == 1
    assert sim.var("app.speedLevel") == 1
    sim["LCD"].assert_matches("ref/home.png")
```

## Debug (VS Code)

[examples/fan/.vscode](examples/fan/.vscode) : lancer la tâche **e2sim connect** (host en temps réel, en
attente du firmware), puis la configuration **fan_hmi (host32)** : le runner démarre sous gdb, les breakpoints
du firmware restent valides après un reset.

## Licence

Outil PC (`e2sim/`, `mk/`, `docs/`) : [PolyForm Noncommercial 1.0.0](LICENSE.md) + licence commerciale.
`target/` et `examples/` : MIT (compilés avec le firmware, à recopier librement).
