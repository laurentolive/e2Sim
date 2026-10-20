# Démo e2Sim : le ventilateur à deux cartes

Durée : 15 à 20 minutes. Prérequis : `make` (les deux firmwares), un navigateur, et eScope pour le chapitre 3.

```
cd examples/fan
make demo                       # interactif : Entrée avant chaque chapitre, temps réel
make demo DEMO_OPTS="--auto"    # chapitres enchaînés (stand, boucle)
make demo-check                 # la même démo en test, accélérée, sans navigateur
```

La page `http://127.0.0.1:8080/` s'ouvre : une colonne par firmware (écran, touches, LEDs, sorties, terminaux,
paramètres des modèles). Le bandeau bleu affiche le chapitre en cours. On peut aussi agir à la main dans la
page entre deux chapitres.

## Message d'introduction

« Ce sont deux vrais firmwares, compilés depuis leurs sources sans aucune modification, qui tournent sur le PC.
Seule la couche basse de la HAL est remplacée. Autour d'eux, l'environnement (moteur, batterie, capteur) est
simulé en Python, au niveau des données de la HAL. Le temps est virtuel : tout est reproductible au bit près. »

## Chapitres

| # | Montrer | Dire |
|---|---|---|
| 1 | Bouton POWER, LED, terminal `UART_DEBUG` | Le `main()` du firmware démarre tel quel ; le verrou d'alimentation tient quand on relâche la touche. |
| 2 | Écran de l'IHM, `PWM_MOTOR`, vitesses | L'IHM envoie la consigne par UART, la carte moteur régule (PI) et renvoie la vitesse mesurée : deux firmwares reliés, comme sur le produit. |
| 3 | eScope connecté aux ports affichés dans la console | Chaque firmware a un endpoint eScope sans une ligne de code ajoutée ; la carte moteur embarque aussi eScope sur une UART, relayée en TCP. Tracer `motor.rpmMeas` et `motor.duty`. |
| 4 | Paramètre `load` du modèle moteur | Le modèle change la charge : le régulateur du firmware compense (le rapport cyclique monte). |
| 5 | Paramètre `temp_C` du capteur | Le capteur SPI répond de façon synchrone ; à 70 °C : OVER TEMP, moteur arrêté. |
| 6 | Paramètre `voltage_V` de la batterie, puis Force sur `VBAT_ADC` | Points ADC bruts : BAT LOW à 9,2 V. Injection de faute : l'entrée est forcée à 0 par-dessus le modèle (pont diviseur coupé), puis rendue au modèle. |
| 7 | Paramètre `blocked` du moteur | Le comparateur de courant déclenche une interruption externe : la coupure arrive dans la milliseconde, sans attendre la boucle de régulation. |
| 8 | Paramètre `stuck_busy` du capteur | Le firmware attend le capteur sans timeout : le watchdog le remet à zéro, dans le même process (le debugger resterait attaché). Défaut trouvé en simulation, sans banc. |
| 9 | Vitesse « max » | Le temps accéléré : le compteur de minutes de fonctionnement défile et se sauve en NVM. Une endurance de plusieurs heures se joue en minutes. |
| 10 | Appui long POWER | Sauvegarde, coupure, rallumage : les réglages sont relus de la NVM (fichier persistant). |
| 11 | Console | Toute la démo a été enregistrée ; elle est rejouée sans modèle ni script : mêmes sorties au bit près (et sur l'autre architecture). |

## eScope (chapitre 3)

Ajouter un device eScope : transport `TCP:127.0.0.1,<port affiché>`, protocole V3, symboles GDB sur
`build/host32/fan_motor.dll` (ou `fan_hmi.dll`), « Addresses : 32 bits » (64 bits pour `host64`), sampling time
1 ms. Variables : `motor.rpmMeas`, `motor.duty`, `motor.current_mA`, `app.speedLevel`. L'axe de temps est juste
même en vitesse « max » : les trames arrivent simplement plus vite.

## Annexe : debugger

Dans VS Code (dossier `examples/fan`) : tâche **e2sim connect**, puis configuration **fan_hmi (host32)**.
Poser un breakpoint dans `sensor_Process()`, déclencher le chapitre 8 depuis la page : le reset watchdog
recharge le firmware et le breakpoint est toujours là.
