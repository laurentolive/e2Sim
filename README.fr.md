# e2Sim

[English](README.md) | **Français**

Simulation de firmware embarqué **sur PC** : le code applicatif tourne en natif, **sans modification**, au-dessus
d'une HAL simulée, cadencé par un **temps virtuel déterministe**, piloté par des scripts de test, une GUI web ou
d'autres firmwares.

- Le firmware est compilé en **DLL** (GCC MinGW, i686 ou x86_64) ; son `main()` tourne dans une fiber du
  **runner** générique `e2sim_runner.exe`, qui gère le temps, les interruptions et les ports.
- Seule la HAL change : un **adaptateur** l'implémente sur [`e2sim.h`](target/include/e2sim.h).
- L'entourage du MCU (capteurs, carte voisine, batterie…) est simulé par des **modèles Python**, au niveau des
  données de la HAL (points ADC, octets, rapports cycliques), pas de la physique.
- Un reset (logiciel, watchdog) **recharge la DLL dans le même process** : RAM et init du firmware comme au
  boot, le debugger reste attaché.
- Tests **pytest** reproductibles au bit près, en temps accéléré ; **record / replay** de n'importe quel scénario.
- Plusieurs firmwares reliés (`system.yaml`) : un firmware remplace un modèle.
- **eScope** sur chaque firmware sans code dans le firmware (endpoint V3 du host), relais TCP de n'importe
  quelle UART.

| Documents | |
|---|---|
| [Tutoriel de portage](docs/tutorial/porting.fr.md) | porter un firmware pas à pas |
| [Référence](docs/reference.md) (anglais) | ligne de commande, `board.yaml`, API Python, pytest, `e2sim.h` |
| [Spécification](docs/SPEC.md) | architecture et décisions |
| [Projet exemple](examples/fan) | teste toutes les fonctionnalités et en fait la démo (`make demo`) |
| [Tickets](https://github.com/laurentolive/e2Sim/issues) | travail en cours |

## Arborescence

```
target/            runner + API e2sim.h (MIT) : fiber, temps virtuel, timers, IRQ, ports, reset, mémoire
e2sim/             host Python : Sim, modèles, board.yaml, symboles (gdb), plugin pytest, GUI web, CLI
mk/e2sim.mk        règles make : runner + DLL firmware pour la toolchain choisie
e2sim_cli.py       point d'entrée depuis le dépôt (python e2sim_cli.py --help)
examples/fan/      projet exemple (MIT) : banc de test de toutes les fonctionnalités + démo
selftest/          autotests du runner
e2sim_toolchains.yaml.example   toolchains de la machine (modèle)
```

## Prérequis

- Windows, Python 3.10+ avec `pyyaml`, `pytest` (`openpyxl` pour le rapport Excel).
- GNU make, MSYS2 avec `mingw-w64-i686-gcc`, `mingw-w64-i686-gdb` (host32) et/ou `mingw-w64-ucrt-x86_64-gcc`,
  `mingw-w64-ucrt-x86_64-gdb` (host64). gdb sert aussi au host (symboles, `sim.var()`).
- Copier `e2sim_toolchains.yaml.example` en `e2sim_toolchains.yaml` (dans le projet, dans `~/.e2sim/`, ou
  variable `E2SIM_TOOLCHAINS`) avec les chemins de la machine.

## Installation

Depuis le dépôt : rien à installer, `python e2sim_cli.py …`, `E2SIM_ROOT` = racine du dépôt.

Comme package (commande `e2sim`, plugin pytest, SDK `target/` + `mk/` dans `<prefix>/share/e2sim`) :

```
pip install "e2sim[test,report] @ git+https://github.com/laurentolive/e2Sim"
e2sim --version
e2sim root          # dossier du SDK : E2SIM_ROOT des makefiles
```

Makefile d'un firmware hors du dépôt : `E2SIM_ROOT := $(shell e2sim root)` puis `include $(E2SIM_ROOT)/mk/e2sim.mk`.
Ne pas mettre de clé `python:` dans `e2sim_toolchains.yaml` qui désignerait un autre Python que celui du package.

## Démarrage rapide

```
cd examples/fan
make                    # toolchain par défaut (host32)
make test-all           # host32 et host64
make demo               # démonstration dans la GUI web, chapitre par chapitre
python ../../e2sim_cli.py gui sim/system.yaml          # les deux cartes : http://127.0.0.1:8080/
```

```python
def test_power_on(sim):                  # fixture du plugin pytest e2sim
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

`e2sim license` affiche la licence ; `e2sim license choose | activate [CLÉ] | deactivate | check | buy | portal`.
Vérifiée au lancement de `run`, `gui`, `connect`, `replay` et une fois par session pytest ; elle ne bloque jamais
une simulation (Démonstration par défaut). En CI : aucun dialogue, clé dans `E2SIM_LICENSE_KEY`.
`E2SIM_NO_DIALOG=1` supprime les dialogues, `E2SIM_NO_GUI=1` force la console.

Outil PC (`e2sim/`, `mk/`, `docs/`) : [PolyForm Noncommercial 1.0.0](LICENSE.md) + licence commerciale.
`target/` et `examples/` : MIT (compilés avec le firmware, à recopier librement).
