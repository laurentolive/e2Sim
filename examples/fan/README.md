# Projet exemple : ventilateur sur batterie

Firmware original écrit pour e2Sim (spec §16), avec deux buts :

1. **tester l'ensemble des fonctionnalités** d'e2Sim : `make test-all` (chaque fonctionnalité a son test,
   matrice de couverture en spec §16.3) ;
2. **en faire la démonstration** : `make demo`, scénario commenté en 10 chapitres dans la GUI web, guide
   [demo/DEMO.md](demo/DEMO.md). La démo est elle-même testée (`make demo-check`).

C'est aussi le modèle de portage d'un firmware.

**Carte IHM `fan_hmi`** : verrou d'alimentation (`SELF_HOLD`), 3 touches, écran 128×64 RGB565, capteur de
température SPI, batterie sur ADC, carte moteur sur UART (protocole à CRC), réglages en NVM, watchdog.

| Touche | Action |
|---|---|
| POWER (appui court) | ventilateur marche / arrêt |
| POWER (2 s) | sauvegarde, puis coupure quand la touche est relâchée |
| PLUS / MINUS | vitesse 1 à 5 |

```
hal/          HAL d'exemple (en-têtes génériques)
hal_e2sim/    adaptateur de la HAL sur e2sim.h  ← modèle à recopier
common/       protocole IHM ↔ moteur, CRC
escope/       code cible eScope V3 (copie, MIT), embarqué par fan_motor sur UART_SCOPE
fan_hmi/      application IHM (main() superloop) ; halCfg.h : ressources HAL de la carte
sim/          hmi.board.yaml + modèles Python (Battery, TempSensor, MotorBoard)
tests/        tests pytest T00..T15 + démo + images de référence
demo/         démo : demo.py (chapitres) et DEMO.md (guide)
```

```
make test          # toolchain par défaut
make test-all      # host32 et host64 (mêmes références d'écran)
make demo          # démonstration dans la GUI
make demo-check    # la démo en test
make coverage      # couverture des firmwares par la campagne : out/coverage/index.html
```

**Carte moteur `fan_motor`** : régulation PI de vitesse sur tachymètre, PWM, comparateur de courant sur
interruption externe, surintensité logicielle, rotor bloqué. `sim/system.yaml` simule les deux cartes : le
firmware moteur remplace alors le modèle `MotorBoard`. Il embarque aussi eScope sur `UART_SCOPE`, relayée en
TCP par e2Sim ; sa configuration PC est [hal_e2sim/eScopeCfg.h](hal_e2sim/eScopeCfg.h).
