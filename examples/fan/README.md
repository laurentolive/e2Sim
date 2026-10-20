# Exemple : ventilateur sur batterie

Firmware original écrit pour e2Sim (spec §16), qui sert de démonstration, de modèle de portage et de test
d'intégration d'e2Sim.

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
fan_hmi/      application IHM (main() superloop) ; halCfg.h : ressources HAL de la carte
sim/          hmi.board.yaml + modèles Python (Battery, TempSensor, MotorBoard)
tests/        tests pytest T00..T06 + images de référence
```

```
make test          # toolchain par défaut
make test-all      # host32 et host64 (mêmes références d'écran)
```

V1 : carte moteur `fan_motor` (PWM, tachymètre, EXTI, eScope embarqué) et `system.yaml` à deux firmwares.
