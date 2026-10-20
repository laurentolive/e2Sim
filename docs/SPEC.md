# e2Sim — Spécification v1.0

> Simulateur de firmware embarqué sur PC : le code applicatif tourne en natif au-dessus d'une HAL simulée,
> cadencé par un temps virtuel déterministe, piloté par un humain, des scripts ou d'autres firmwares.

Statut : **brouillon à consolider** — 2026-10-20
Historique : v0.2 premières décisions (superloop, ports niveau HAL, GCC, eScope) ;
v0.3 GUI web, entrée `main()`, lien e2Unit, firmware exemple ;
v0.4 axe temps eScope par index × période, registre de toolchains partagé avec e2Unit, make ;
v0.5 i686 et x86_64, alignement sur l'évolution « PC simulation » d'eScope ;
v0.6 licence (§17) ;
v0.7 reset et power dans le même process, transactions synchrones, index résolus par DWARF, accès mémoire
par IPC, endpoint eScope dans le host, phasage ajusté, exemples tirés du seul firmware exemple ;
v0.8 décisions d'implémentation V0 : firmware en DLL chargée par un runner générique (reset = rechargement de la
DLL), durée de reset, verrou d'alimentation dans `board.yaml`, API `e2sim.h` alignée sur le code ;
v0.9 runs longs équivalents au pas fixe, multi-firmware livré au quantum suivant, vitesse mesurée ;
v1.0 e2Sim indépendant d'e2Unit (fichier de toolchains propre), projet exemple banc de test + démo (§16),
suivi des actions dans les tickets GitHub

---

## 1. Objectifs et périmètre

### 1.1 Objectifs
| # | Objectif | Mesure de succès |
|---|---|---|
| O1 | Porter rapidement un firmware sur PC | Nouveau produit sur une HAL déjà adaptée : **< 1 jour** |
| O2 | **Aucun impact sur le firmware** (exigence de premier niveau) | Sources applicatives et en-têtes HAL inchangés : pas de `#ifdef SIMU`, pas de fichier généré à inclure, pas d'instrumentation |
| O3 | Tests reproductibles | Même scénario → mêmes sorties, au bit près |
| O4 | Trois modes d'interaction | Humain (GUI), scripts de test, autres firmwares |
| O5 | Debug confortable | Pas à pas, breakpoints, attach au process depuis VS Code, conservé à travers les resets |
| O6 | Observabilité | eScope disponible sur tout firmware simulé, sans intégration dans le firmware |

Seule la couche la plus basse change : l'**adaptateur HAL** (§5.2) remplace l'implémentation MCU de la HAL.

### 1.2 Hors périmètre (non-objectifs)
- Émulation d'instructions / cycle-accurate (rôle de Renode, QEMU).
- Simulation **physique** des interfaces : pas de tensions, pas de bits UART, pas de timing électrique.
  Les ports transportent **les données attendues par la HAL** (§5).
- RTOS (pas prévu à moyen terme ; l'architecture ne doit pas l'interdire).
- Exécution distribuée sur plusieurs machines : **un seul PC**.

---

## 2. Glossaire

| Terme | Définition |
|---|---|
| **Firmware sim** | DLL (`<produit>.dll`) = sources firmware + adaptateur HAL, chargée par le runner |
| **Runner** | `e2sim_runner.exe`, générique (un par toolchain) : charge la DLL, l'exécute, dialogue avec le host |
| **Adaptateur HAL** | Implémentation de la HAL du firmware au-dessus de l'API `e2sim.h`, à la place de l'implémentation MCU |
| **libe2sim-target** | `e2sim.h` + runner : fiber, temps virtuel, IRQ, ports, reset, accès mémoire, IPC. La DLL importe l'API depuis le runner |
| **Host** | Process Python maître : temps global, modèles, scripts, GUI, endpoints eScope, liaisons inter-firmwares |
| **Instance** | Un firmware simulé dans une session (un process) |
| **Port** | Point d'échange nommé et typé entre firmware et host (§5) |
| **Modèle** | Objet Python qui simule l'entourage du MCU au niveau données |
| **Quantum** | Pas de synchronisation host ↔ firmware en temps virtuel (défaut 1 ms) |
| **Yield point** | Point où le firmware rend la main au simulateur (appel HAL, idle) |

---

## 3. Architecture

```
 ┌──── e2sim_runner.exe + <produit>.dll  (1 process par instance, i686 ou x86_64) ─────────┐
 │  Code applicatif inchangé                                                                │
 │  main() d'origine (renommé e2sim_app_main, superloop inchangée) dans une FIBER           │
 │  ───────────────────────────── HAL du firmware (en-têtes inchangés) ──────────────       │
 │  Adaptateur HAL  → appelle l'API e2sim.h                                                 │
 │  libe2sim-target : ordonnanceur local, timers, IRQ, ports, transactions, NVM,            │
 │                    framebuffer, reset/power, échantillonnage et accès mémoire, log       │
 └──────────────────────────────┬───────────────────────────────────────────────────────────┘
                                │ TCP localhost (contrôle, deltas de ports, transactions, mémoire)
                                │ + mémoire partagée (blocs : framebuffer, NVM)
 ┌──────────────────────────────┴────────────────────────────┐
 │  Host e2Sim (Python)                                      │   TCP eScope V3      ┌──────────┐
 │  ├─ Horloge maître, synchro par quantum                   │◄────────────────────►│  eScope  │
 │  ├─ Modèles d'environnement (Python)                      │  1 port par instance │ (traces) │
 │  ├─ Endpoint eScope intégré, un par instance (§9.1)       │                      └──────────┘
 │  ├─ Relais TCP des ports stream (§9.3)                    │
 │  ├─ Liaisons inter-firmwares (system.yaml)                │
 │  ├─ API scripts + plugin pytest                           │
 │  ├─ GUI web locale générée depuis board.yaml              │
 │  └─ Record / replay, logs, rapports                       │
 └───────────────────────────────────────────────────────────┘
```

**Principes structurants**
1. **Coupure à la HAL du firmware** : l'adaptateur e2Sim est une implémentation de plus de la HAL, à côté
   de celles des MCU réels.
2. **MCU virtuel ≠ environnement** : l'adaptateur ne contient *aucune* logique produit ; le comportement
   de l'entourage (capteurs, carte voisine, actionneurs) est dans les modèles Python.
3. **Un process par instance**, qui vit toute la session (resets et cycles d'alimentation compris) : isole
   les globales et les crashs, permet le multi-firmware et garde le debugger attaché.
4. **Le host est maître du temps** ; un firmware arrêté sur breakpoint gèle toute la simulation de façon cohérente.

---

## 4. Exécution du firmware et temps virtuel

### 4.1 Modèle d'exécution : superloop inchangée
- Le point d'entrée est **le `main()` du firmware**, générique pour tous les projets. Les sources firmware
  sont compilées avec `-Dmain=e2sim_app_main` (posé par `mk/e2sim.mk`) ; le vrai `main()` du process
  est dans `libe2sim-target`. Il crée une **fiber** dans laquelle il appelle `e2sim_app_main()`, qui ne
  retourne normalement jamais (un retour est traité comme un arrêt du MCU).
- Le contexte « scheduler » (fiber principale) exécute : échanges avec le host, timers, **ISR**,
  échantillonnage mémoire, émission des sorties.
- Bascule fiber ↔ scheduler aux **yield points** :
  - **chaque appel HAL** (via l'adaptateur) → `e2sim_yield()` ;
  - **idle / WFI / refresh watchdog** → `e2sim_idle()` : le temps saute au prochain événement ;
  - macro `E2SIM_YIELD()` optionnelle (vide sur cible) pour une boucle d'attente qui n'appelle aucune HAL.
- Implémentation : Windows Fibers (`CreateFiber/SwitchToFiber`), abstraite pour un portage ucontext (Linux) futur.

### 4.2 Interruptions
- Les ISR sont exécutées **dans le contexte scheduler**, à un yield point, quand leur date ≤ temps courant.
- Une ISR peut appeler la HAL : dans le contexte scheduler, **`e2sim_yield()` et `e2sim_idle()` ne font
  rien** (pas de bascule, pas d'avance du temps). `e2sim_xfer()` reste utilisable (§5.1).
- `e2sim_irq_disable()/enable()` (sections critiques HAL) : ISR différées jusqu'à la réactivation.
- Priorités : une ISR n'est pas préemptée ; ordre de service = date puis priorité déclarée.
- Sources : timers (`e2sim_timer_*`), changement d'un port entrant (EXTI, réception UART), fin de conversion.

### 4.3 Temps virtuel
- Temps en **ns, entier 64 bits**. Le firmware ne voit jamais l'horloge murale.
- **Coût CPU** : chaque `e2sim_yield()` (contexte fiber) avance le temps de `cpu.yield_cost_ns`
  (défaut 1 µs) → les attentes actives sur compteur HAL progressent ; `e2sim_idle()` saute au prochain événement.
- **Synchronisation host ↔ firmware par quantum** (défaut 1 ms) :
  1. le host envoie `RUN_UNTIL(T)` + les entrées modifiées ;
  2. le firmware exécute jusqu'à T (événements locaux à sa résolution propre) ;
  3. il renvoie les sorties modifiées (deltas), les octets stream émis (horodatés) et les échantillons mémoire.
  Une entrée host est vue avec ≤ 1 quantum de latence — acceptable au niveau données.
  Les octets stream reçus sont délivrés au firmware à leur date (décalée d'un quantum).
- Exception : les **transactions synchrones** (§5.1) sont servies au milieu du quantum, temps arrêté.
- **Runs longs** (une instance, `sim.run()`) : le runner enchaîne les quanta sans aller-retour avec le host et
  s'arrête à la fin du premier quantum qui a produit une sortie (ou un log, un reset) ; le host plafonne le run
  à sa prochaine échéance (action programmée, tâche périodique d'un modèle, délai du verrou d'alimentation).
  Le firmware passe par chaque frontière de quantum : le résultat est **identique au pas fixe** (vérifié par
  T00), seul le nombre d'allers-retours change. Mesuré sur `fan_hmi` : ×14 au pas fixe de 1 ms, ×97 en runs
  longs (limités ici par les modèles à 10 ms et la trame IHM à 100 ms). `run_until()` reste au pas fixe : sa
  condition peut dépendre de variables qui changent sans sortie.
- **Modes** : `max` (aussi vite que possible : CI, endurance), `realtime ×k` (humain),
  `step` (pas à pas en quantums), `pause`.
- **Détection de blocage** : pas de yield pendant N s d'horloge murale (hors debugger attaché)
  → diagnostic « boucle sans yield point » avec la pile de la fiber.

### 4.4 Reset, alimentation, watchdog : dans le même process
Le process d'une instance vit **toute la session** : le debugger reste attaché à travers les resets.

- Le firmware est compilé en **DLL** ; le process est le **runner** générique, qui la charge.
- **Reset** (appel HAL de reset, timeout watchdog, commande host) :
  1. la fiber applicative est détruite ; timers, ISR enregistrées et buffers de réception sont vidés ;
  2. la DLL est **déchargée puis rechargée** (`FreeLibrary` / `LoadLibrary`) : `.data`, `.bss` et
     l'initialisation CRT du firmware repartent exactement comme au boot, sans toucher à la CRT du process.
     Avec une base d'image fixe, la DLL revient à la même adresse ; le debugger garde ses breakpoints
     (breakpoints « pending » réinsérés au rechargement) ;
  3. les ports `out` repassent à 0, le host reçoit un événement `RESET` (cause : power_on, soft, wdt, host) ;
  4. le temps avance de la **durée de reset** (100 µs) : un reset maintenu actif ne boucle pas à temps nul ;
  5. une nouvelle fiber rappelle `e2sim_app_main()`.
- Un reset demandé depuis une ISR (watchdog) prend effet à la fin de l'ISR.
- L'état du simulateur vit dans le runner, jamais réinitialisé.
- Les **blocs NVM** survivent (fichiers mappés) ; la RAM repart comme au boot réel.
- **Power off** (ex. sortie de maintien d'alimentation relâchée, commande host) : la fiber est arrêtée, les
  sorties passent à l'état « non alimenté », le temps virtuel continue pour le reste du système.
  **Power on** = reset avec la cause `POWER_ON`.
- Limite : le tas `malloc` est celui du process (CRT système) : un firmware qui alloue au démarrage sans
  libérer fuit à chaque reset. Option prévue `reset: process` dans `board.yaml` pour relancer le process à la
  place (debugger détaché ; défaut `reset: in_process`, seul implémenté en V0).
- **Verrou d'alimentation** (`power: { mode: latch, button: BTN_POWER, hold: SELF_HOLD, hold_ms: 10 }`) :
  alimenté tant que la touche est appuyée ou que le firmware tient la sortie de maintien. Le verrou tient
  `hold_ms` sans l'une ni l'autre, comme la capacité d'un vrai montage pendant un reset. Autres modes :
  `auto` (alimenté au démarrage), `manual` (`sim.power_on()`).
- Le watchdog est simulé en temps virtuel (désactivable pendant le debug).

---

## 5. Ports (interface niveau HAL)

Les ports transportent **exactement ce que la HAL renvoie ou reçoit**, sans conversion physique.
Ex. : la lecture ADC de la HAL renvoie des points ADC → le port ADC transporte des points ADC.

| Type | Contenu | Exemples HAL | Sens |
|---|---|---|---|
| `bit` | 0/1 | lecture / écriture GPIO | in / out |
| `value` | entier signé 32 bits | lecture ADC, duty PWM, période de capture, compteur | in / out |
| `stream` | flux d'octets horodatés, asynchrone | UART | in / out |
| `xfer` | transaction **synchrone** : octets émis → octets reçus | SPI, I2C, tout échange où la fonction HAL retourne avec la donnée reçue | io |
| `block` | zone mémoire partagée | framebuffer LCD, EEPROM, flash série | in / out / io |
| `event` | impulsion horodatée | IRQ externe, trigger | in / out |

- Adressage en C : **(classe, index HAL)** — pas de recherche par chaîne dans le chemin critique.
  Le nom humain est donné par `board.yaml` (§6).
- **Transactions `xfer`** : la fiber est suspendue, la requête part au host, le modèle répond, la fonction
  HAL retourne avec la donnée reçue. Le **temps virtuel est arrêté** pendant l'aller-retour (option
  `cost_ns` par port pour imputer la durée du transfert) : le déterminisme est conservé. Un `xfer` est
  servi par un modèle Python ; un `xfer` entre deux firmwares est hors périmètre.
- Les blocs NVM sont persistés dans un fichier mappé en mémoire (`<instance>.<bloc>.nvm.bin`, ignoré par
  git) : état conservé entre runs, injection de corruption possible.
- Les ports `out` sont aussi exposés en lecture au host ; les ports `in` peuvent être forcés par le host
  même s'ils sont pilotés par un modèle (override, pour l'injection de fautes).

### 5.1 API cible (e2sim.h) — esquisse
```c
/* temps et exécution */
uint64_t e2sim_time_ns(void);
void     e2sim_yield(void);                 /* appelé par chaque fonction de l'adaptateur HAL ; sans effet en ISR */
void     e2sim_idle(void);                  /* WFI : saute au prochain événement ; sans effet en ISR              */
void     e2sim_reset(e2sim_reset_cause_t c);/* fiber : ne retourne pas ; ISR : reset à la fin de l'ISR             */
e2sim_reset_cause_t e2sim_reset_cause(void); /* cause du dernier reset                                     */

/* ports */
int32_t  e2sim_in (e2sim_class_t c, uint16_t idx);
void     e2sim_out(e2sim_class_t c, uint16_t idx, int32_t v);
void     e2sim_event_out(uint16_t idx);
size_t   e2sim_stream_read (uint16_t idx, uint8_t *buf, size_t max);  /* classe UART */
void     e2sim_stream_write(uint16_t idx, const uint8_t *buf, size_t len);
size_t   e2sim_xfer(e2sim_class_t c, uint16_t idx, const uint8_t *tx, size_t tx_len,
                    uint8_t *rx, size_t rx_max);           /* synchrone, temps arrêté */
void    *e2sim_block(uint16_t idx, size_t size);

/* interruptions */
typedef void (*e2sim_isr_t)(void *ctx);
e2sim_timer_t e2sim_timer_start(uint64_t period_ns, bool periodic, e2sim_isr_t isr, void *ctx);
void     e2sim_timer_stop(e2sim_timer_t t);
void     e2sim_on_input(e2sim_class_t c, uint16_t idx, e2sim_isr_t isr, void *ctx); /* EXTI, RX */
void     e2sim_irq_disable(void);
void     e2sim_irq_enable(void);

/* diagnostic */
void     e2sim_log(int level, const char *fmt, ...);
```
L'accès mémoire (lecture, écriture, échantillonnage périodique) n'a pas d'API côté firmware : c'est un
service de `libe2sim-target` piloté par le host (§7.2, §9).

### 5.2 Exemple d'adaptateur (HAL du firmware exemple)
```c
bool     halGpio_Read(halGpio_t pin)               { e2sim_yield(); return e2sim_in(E2SIM_GPIO, pin) != 0; }
void     halGpio_Write(halGpio_t pin, bool v)      { e2sim_yield(); e2sim_out(E2SIM_GPIO, pin, v); }
uint16_t halAdc_Read(halAdc_t ch)                  { e2sim_yield(); return (uint16_t)e2sim_in(E2SIM_ADC, ch); }
void     halPwm_SetDuty(halPwm_t ch, uint16_t d)   { e2sim_yield(); e2sim_out(E2SIM_PWM, ch, d); }
size_t   halSpi_Transfer(halSpi_t bus, const uint8_t *tx, uint8_t *rx, size_t n)
                                                   { e2sim_yield(); return e2sim_xfer(bus, tx, n, rx, n); }
```
L'adaptateur est **générique à une famille de HAL** (réutilisé par tous les produits qui la partagent).
Les seules parties projet sont des tables (périodes de timers…) et d'éventuels drivers de composants
externes (LCD → bloc framebuffer, flash série → bloc).

---

## 6. Description produit : `board.yaml`

Une seule source de vérité pour les ports, les modèles et la GUI. Exemple tiré du firmware exemple (§16) :

```yaml
name: fan_hmi
firmware: ../build/{toolchain}/fan_hmi.dll   # {toolchain} : toolchain choisie (§10.1) ; entrée : main()
quantum_ms: 1
cpu: { yield_cost_ns: 1000 }
reset: in_process                     # défaut (§4.4) ; "process" relance le process à chaque reset
power: { mode: latch, button: BTN_POWER, hold: SELF_HOLD }   # §4.4

ports:
  BTN_POWER:  { class: GPIO,  idx: HAL_GPIO_BTN_POWER, type: bit,   dir: in, default: 0 }
  BTN_PLUS:   { class: GPIO,  idx: HAL_GPIO_BTN_PLUS,  type: bit,   dir: in, default: 0 }
  LED_STATUS: { class: GPIO,  idx: HAL_GPIO_LED,       type: bit,   dir: out }
  SELF_HOLD:  { class: GPIO,  idx: HAL_GPIO_SELF_HOLD, type: bit,   dir: out }
  VBAT_ADC:   { class: ADC,   idx: HAL_ADC_VBAT,       type: value, dir: in }
  TEMP_SPI:   { class: SPI,   idx: HAL_SPI_SENSOR,     type: xfer, cost_ns: 30000 }
  UART_LINK:  { class: UART,  idx: HAL_UART_LINK,      type: stream }
  UART_DEBUG: { class: UART,  idx: HAL_UART_DEBUG,     type: stream, tcp: 47710 }
  LCD:        { class: BLOCK, idx: HALSIM_BLOCK_LCD,   type: block, framebuffer: { w: 128, h: 64, format: RGB565 } }
  EEPROM:     { class: BLOCK, idx: HALSIM_BLOCK_NVM,   type: block, size: 2048, persist: true }   # enum de l'adaptateur

models:
  - { class: models.battery.Battery,        ports: { adc: VBAT_ADC } }
  - { class: models.temp_sensor.TempSensor, ports: { spi: TEMP_SPI } }
  - { class: models.motor_board.MotorBoard, ports: { uart: UART_LINK } }   # remplacé par fan_motor dans system.yaml

escope: { port: 47700 }               # endpoint eScope intégré (§9.1)

gui:
  skin: assets/fan_front.png
  widgets:
    - { port: BTN_POWER,  widget: button, at: [212, 80] }
    - { port: LCD,        widget: screen, at: [120, 40], zoom: 2 }
    - { port: LED_STATUS, widget: led }
    - { model: Battery, param: voltage_V, widget: slider, range: [9.0, 12.6] }
```

**Résolution des index** (O2 : rien n'est généré dans le firmware) : un `idx` symbolique est un nom
d'enum ou de macro de la HAL du firmware. Le host le résout au chargement **depuis le DWARF de
l'exécutable** (gdb en mode batch, comme les symboles eScope, §9.4). Les macros `#define` ne sont pas dans
le DWARF par défaut : compiler avec `-g3`, ou donner l'index en numérique. Un nom introuvable est une
erreur de chargement explicite.

---

## 7. Host Python

### 7.1 Modèles d'environnement
Niveau **données** uniquement : un modèle lit et écrit des ports, et réagit à des événements, à des
transactions ou à une période.
```python
class MotorBoard(e2sim.Model):              # stream asynchrone
    uart = e2sim.Stream()
    rpm = e2sim.Param(0)
    no_answer = e2sim.Param(False)          # injection de faute depuis GUI/script

    def on_rx(self, frame: bytes):
        if not self.no_answer:
            self.uart.write(self.answer(frame))

class TempSensor(e2sim.Model):              # transaction synchrone
    spi = e2sim.Xfer()
    temp_C = e2sim.Param(25.0)

    def on_xfer(self, tx: bytes) -> bytes:  # retour = octets lus par halSpi_Transfer
        return self.register_read(tx)

class Battery(e2sim.Model):
    adc = e2sim.Value()
    voltage_V = e2sim.Param(12.0)

    @e2sim.every(ms=10)
    def step(self):
        self.adc.set(round(self.voltage_V / 15.0 * 4095))   # points ADC, pas de tension
```

### 7.2 API scripts + pytest
```python
@e2sim.requirement("FAN-HMI-01")
def test_power_on(sim):                     # fixture fournie par le plugin pytest e2sim
    sim["BTN_POWER"].press(ms=100)
    sim.run(s=2)
    assert sim["SELF_HOLD"] == 1
    sim["LCD"].assert_matches("ref/home.png")

def test_motor_board_silent(sim):
    sim.model("MotorBoard").no_answer = True
    sim.run_until(lambda: sim.var("app.fault") != 0, timeout_s=5)
```
- `sim.var("expr")` : lecture / écriture de variables firmware.
  - **Résolution** : gdb en mode batch sur l'exécutable (adresse, taille, type ; expressions C), comme eScope.
  - **Accès** : commande IPC `MEM_READ` / `MEM_WRITE` servie par `libe2sim-target` **dans le contexte
    scheduler** (jamais au milieu d'une mise à jour applicative). Le host traduit l'adresse de link en
    adresse réelle avec l'`__ImageBase` annoncé par le firmware à la connexion ; le firmware contrôle
    l'adresse (`VirtualQuery`) et répond une erreur au lieu de planter.
  - Les écritures sont journalisées comme des entrées (replay exact).
- Sorties : JUnit XML (Jenkins), journal horodaté en temps virtuel, captures d'écran ; rapport Excel.

### 7.3 GUI
- **Générée depuis `board.yaml`** : boutons, interrupteurs, LEDs, sliders, valeurs, écran, terminal stream,
  commandes de temps (play, pause, step, ×k), paramètres des modèles et injection de fautes.
- Skin optionnel : image du produit + zones cliquables.
- **UI web locale** servie par le host (HTTP sur `127.0.0.1`, bibliothèque standard Python), ouverte dans le
  navigateur : `e2sim gui board.yaml|system.yaml`. La page lit `GET /api/state` (100 ms) et envoie
  `POST /api/cmd` (`run`, `pause`, `step`, `speed`, `set`, `press`, `write`, `param`, `power`, `reset`) ; la même
  API JSON sert l'automatisation externe. Choix d'implémentation : du polling HTTP plutôt qu'un WebSocket,
  suffisant en local et sans dépendance.
- Pas de framework front lourd ni d'étape de build JS : composants générés depuis `board.yaml`, servis tels quels.
- La GUI est un client comme un autre : on peut lancer un script et suivre en GUI simultanément.

### 7.4 Record / replay
- Le host enregistre tous les messages qu'il envoie aux runners (`RUN` avec leurs entrées, écritures mémoire
  comprises ; réponses aux transactions ; écritures de blocs par le host) et le contenu initial des NVM
  (`.e2simrec`). Le replay renvoie ces messages tels quels, **sans modèle ni script**, et compare l'empreinte
  de la trace des sorties : `e2sim replay <fichier>` (code retour 0 si identique), `--connect` pour le rejouer
  sous debugger, `pytest --e2sim-record DIR` pour enregistrer chaque test. Un enregistrement fait sur une
  architecture se rejoue à l'identique sur l'autre (firmware portable).
- **Snapshot « par replay »** : revenir à l'instant T = relancer et rejouer jusqu'à T (vite en mode `max`).

---

## 8. Multi-firmware (même PC)

```yaml
# system.yaml
instances:
  hmi:   { board: hmi.board.yaml }
  motor: { board: motor.board.yaml }
links:
  - [hmi.UART_LINK, motor.UART_LINK]       # stream ↔ stream
  - [hmi.MOTOR_EN,  motor.ENABLE]          # bit out → bit in
```
- Le host avance toutes les instances au même T (quantum commun, pas de runs longs), puis échange les deltas
  et les streams. Les sorties d'une instance sont livrées aux autres **au quantum suivant**, quel que soit
  l'ordre d'exécution des instances : pas de causalité inversée.
- **Latence** : un échange entre deux firmwares passe par le host à la frontière du quantum, soit
  ≈ 1 quantum par sens. Les timeouts des protocoles inter-cartes doivent dépasser **2 quanta** ; sinon,
  réduire `quantum_ms` pour le système.
- Un lien remplace un modèle : un firmware simulé prend la place d'un modèle Python (`MotorBoard` → `fan_motor`).
- Les instances sont attachables individuellement au debugger ; un breakpoint gèle tout le système.
- Liens `bit`, `value`, `event` et `stream` uniquement (pas de `xfer` entre firmwares, §5).

---

## 9. Intégration eScope

Principe : **eScope ne sait pas qu'il parle à une simulation**. Pour lui, c'est une cible protocole V3 sur
TCP. e2Sim s'appuie sur l'évolution « PC simulation » d'eScope (adresses 64 bits `ADDR64_FLAG`, codes
`ERR_ADDR` / `ERR_ADDRSIZE`, GDB sur PE ; branche `issue-1-pc-simulation`, à merger dans master).

### 9.1 Endpoint eScope intégré au host (mode principal)
- Le host expose **un endpoint eScope V3 par instance** (`escope: { port: … }` dans `board.yaml`, ou port
  attribué automatiquement et affiché). eScope s'y connecte avec `TCP:127.0.0.1,<port>`.
- **Toujours présent**, que le firmware embarque eScope ou non : **aucun code eScope dans le firmware** (O2, O6).
- Fonctionnement :
  - le host décode les commandes V3 (lectures périodiques, lectures et écritures ponctuelles, `CMD_CLEAR`) ;
  - il configure dans `libe2sim-target` une **liste d'échantillonnage** (adresses relocalisées, tailles) et
    une **période en temps virtuel** ;
  - `libe2sim-target` copie ces zones **dans le contexte scheduler**, à chaque période (événement timer
    interne, jamais au milieu d'une mise à jour applicative), et renvoie les échantillons avec la réponse du quantum ;
  - le host en fait **une trame V3 par échantillon** (`flowId` incrémenté).
- **Taille d'adresse** = celle du build : 4 octets en i686, 8 en x86_64 (`Device.AddressSize` côté eScope).
  Une incohérence est signalée par `ERR_ADDRSIZE`, une adresse refusée par `ERR_ADDR` (contrôle `VirtualQuery`).
- **Période** : `escope.period_us` dans `board.yaml` (défaut 1 ms), à reporter dans `Device.SamplingTime`.
- Le même service d'accès mémoire sert `sim.var()` (§7.2) et l'enregistrement de traces par les scripts.

### 9.2 Axe temps : protocole V3 inchangé
- Comme sur cible, la base de temps est **la cadence du flux** : une trame par période d'échantillonnage
  **en temps virtuel**. L'axe X est juste dans tous les modes ; en mode accéléré, les trames arrivent
  simplement plus vite. Les pertes sont détectées par le `flowId`. Aucun horodatage n'est ajouté.
- **Aucune perte côté e2Sim** : si le socket sature, la simulation est freinée au lieu de jeter des trames.
- **Pause / breakpoint** : plus de trames, `Timeout` d'eScope au bout d'1 s, signalé sur les canaux, puis
  reconfiguration automatique à la reprise. C'est le comportement voulu, sans risque.

### 9.3 Firmware qui embarque déjà eScope (mode secondaire)
- Un firmware qui intègre eScope sur une UART fonctionne **tel quel** : le port `stream` de cette UART est
  exposé en serveur TCP par le **relais générique** d'e2Sim (`tcp: <port>` dans `board.yaml`). Les deux
  endpoints peuvent coexister, sur des ports différents.
- Relais TCP d'un stream (sert aussi pour un terminal ou un outil PC) : octets reçus injectés dans le
  contexte scheduler à la frontière d'un quantum et journalisés (replay exact) ; octets émis envoyés au
  client, jetés sans client ; option `baud:` pour limiter au débit simulé (débordements représentatifs).
- Dans ce mode, c'est le firmware qui lit sa mémoire : son `eScopeCfg.h` de variante PC doit gérer la
  relocation (`ESCOPE_ADDR_TO_PTR` avec `__ImageBase`) et le contrôle d'adresse (`ESCOPE_ADDR_IS_VALID`).
  Le firmware exemple fournit ce modèle de fichier.

### 9.4 Symboles
- **GDB sur le `.exe` directement** (PE + DWARF, `-g`). Le `gdb-multiarch` fourni avec eScope lit un PE
  x86 / x64 : expressions C, complétion, suivi des pointeurs comme sur cible.
- Les adresses données par GDB sont les adresses de link ; la relocation est faite par le host (§9.1)
  ou par le firmware (§9.3). Base de link fixe recommandée (`-Wl,--image-base=<base>`).
- La map GNU ld (`-Wl,-Map`) est aussi générée (mode `map` d'eScope). En i686, les symboles C ont un `_`
  en tête, retiré par eScope.
- Le host utilise le même gdb pour `sim.var()` et la résolution des index de `board.yaml` (§6).
- Les scripts de test peuvent piloter eScope via son API d'automation (REST/MCP).
- Aucune trace « physique » de type VCD n'est générée par e2Sim.

---

## 10. Chaînes de compilation et debug

### 10.1 Fichier de toolchains d'e2Sim
e2Sim a **son propre fichier de configuration**, `e2sim_toolchains.yaml`, lu par lui seul : aucun
couplage avec les autres outils (e2Unit, eScope) ni dépendance de code entre les dépôts.

```yaml
# e2sim_toolchains.yaml (non versionné : propre à la machine) ; modèle : e2sim_toolchains.yaml.example
python: C:/Dev/Tools/Python312/python.exe      # Python du host et des makefiles

toolchains:
  host32:                                       # PC 32 bits (MSYS2 MINGW32)
    arch: i686
    prefix: C:/Dev/Tools/msys64/mingw32/bin/    # -> gcc, ar, objcopy, gdb
    path: [C:/Dev/Tools/msys64/mingw32/bin]     # DLL runtime de MSYS2
  host64:                                       # PC 64 bits (MSYS2 UCRT64)
    arch: x86_64
    prefix: C:/Dev/Tools/msys64/ucrt64/bin/
    path: [C:/Dev/Tools/msys64/ucrt64/bin]

default: host32
```

**Recherche du fichier** (le premier trouvé l'emporte) : variable `E2SIM_TOOLCHAINS` →
`e2sim_toolchains.yaml` dans le dossier courant ou un de ses parents → `~/.e2sim/e2sim_toolchains.yaml`.

**Choix d'une toolchain**, du plus prioritaire au moins prioritaire :
1. ligne de commande : `make TOOLCHAIN=host64`, `e2sim run --toolchain host64`, `pytest --e2sim-toolchain host64` ;
2. projet : clé `toolchain:` dans `board.yaml` ;
3. `default:` du fichier.

**Intégration au build** : GNU make, comme les firmwares. Le fichier est traduit en un fragment
`toolchain-<nom>.mk` (`CC`, `AR`, `OBJCOPY`, `GDB`, `E2SIM_PY`, `PATH`) inclus par `mk/e2sim.mk`, et le
chemin du gdb est reporté dans `.vscode/launch.json`. Les sorties sont séparées par toolchain
(`build/<toolchain>/`).

### 10.2 Architectures 32 et 64 bits : les deux sont supportées
**Exigence** : e2Sim fonctionne **en i686 et en x86_64** ; l'architecture n'est qu'un choix de toolchain.

| Composant | i686 (`host32`) | x86_64 (`host64`) |
|---|---|---|
| `libe2sim-target`, adaptateur, firmware | ✔ | ✔ |
| Endpoint eScope | `AddressSize` 4 | `AddressSize` 8 (`ADDR64_FLAG`) |
| Debug VS Code | gdb `mingw32` | gdb `ucrt64` |

- Le firmware tourne dans son propre process : le host Python (32 ou 64 bits) pilote indifféremment un
  firmware 32 ou 64 bits.
- **Défaut conseillé pour e2Sim : `host32`** (`sizeof(void*) == 4` comme sur MCU).
- **CI sur les deux architectures** : tout écart de résultat révèle un code non portable (pointeur stocké
  dans un entier 32 bits, hypothèse sur `sizeof(void*)`). Sous Windows (LLP64), `long` fait 4 octets
  dans les deux cas, comme sur ARM.
- `libe2sim-target` et les adaptateurs compilent **sans warning dans les deux architectures**.

### 10.3 Flags et debug
| Élément | Choix |
|---|---|
| Flags de fidélité | `-funsigned-char` (char non signé comme sur ARM), `-fshort-enums` si la cible l'utilise, `-g -O0` |
| Flags propres à e2Sim | `-Dmain=e2sim_app_main`, `-shared -static`, `-Wl,--image-base=0x10000000 --disable-dynamicbase`, `-Wl,-Map` ; la DLL est liée à la bibliothèque d'import du runner |
| Flags de diagnostic | warnings identiques à la cible + `-Wconversion` optionnel |
| Debug | **VS Code** + extension C/C++ (gdb de la toolchain choisie) : configurations `launch` et `attach` |
| IntelliSense | `compile_commands.json` généré par une cible make (`make compdb`) |

- Le firmware peut être lancé **depuis le debugger** avec `--wait-host` ; le host s'y connecte avec `e2sim connect`.
- Quand un debugger est attaché, les timeouts (détection de blocage, watchdog) sont suspendus.
- Le debugger reste attaché à travers les resets et les cycles d'alimentation (§4.4).
- La liste des sources est d'abord écrite à la main dans le makefile e2Sim du projet ; un outil
  d'extraction depuis le makefile cible viendra plus tard.

---

## 11. Procédure de portage d'un firmware

**Emplacement de l'adaptateur** : la HAL appartient au firmware, donc l'adaptateur vit **dans le dépôt
firmware**, à côté des implémentations MCU de la HAL. e2Sim fournit `libe2sim-target`, le host et le
**firmware exemple** (§16), dont l'adaptateur sert de modèle à recopier.

1. Écrire l'adaptateur e2Sim de la HAL du projet — une fois par famille de HAL.
2. Créer le makefile e2Sim du projet (modèle : `examples/fan/Makefile`) : sources du projet sans l'implémentation MCU
   de la HAL ni le BSP, includes, defines, `include $(E2SIM_ROOT)/mk/e2sim.mk`.
3. Écrire `board.yaml` : ports (index symboliques de la HAL), modèles, GUI.
4. (Optionnel) Écrire les modèles Python nécessaires ; sinon les ports sont pilotés à la main ou par script.
5. `e2sim run board.yaml` → GUI ; `pytest` → tests ; eScope sur le port de l'instance.

Ce qui reste spécifique au projet : drivers de composants externes (LCD → bloc framebuffer, flash série →
bloc) et éventuels accès registres hors HAL, à signaler comme dette d'architecture.

---

## 12. Gains attendus
- Développement et démos avant disponibilité du matériel ; validation UX avec le marketing.
- Debug PC : pas à pas, watch, attach conservé à travers les resets ; reproduction exacte par replay.
- Tests système en CI (Jenkins, headless, mode `max`) ; endurance accélérée (×100 environ sur l'exemple : 10 min virtuelles en 6 s ; à adapter aux périodes des modèles).
- Injection de fautes difficile sur banc : NVM corrompue, carte voisine muette, trames invalides, reset watchdog.
- Non-régression écran : comparaison du framebuffer avec des références, toutes langues ; captures pour la doc.
- eScope sur tout firmware simulé, sans intégration.
- Couverture de code sur tests système (gcov) ; fuzzing des parseurs de trames.
- Hygiène d'architecture : tout accès matériel hors HAL devient visible.

## 13. Limites assumées
- Pas de vérité sur la charge CPU, la pile, les timings fins (rester sur cible).
- Drivers bas niveau (BSP, registres) non testés.
- Préemption ISR seulement aux yield points : certaines races main/ISR ne sont pas reproduites.
- Reset dans le process : l'état de la libc (tas, stdio) n'est pas réinitialisé (§4.4).
- Différences résiduelles x86/ARM : alignement, `sizeof(long double)`, comportements indéfinis, optimisations.

---

## 14. Phasage

| Version | Contenu | Critère de sortie |
|---|---|---|
| **V0** | `libe2sim-target` (fiber, temps virtuel, timers, IRQ, ports `bit`/`value`/`stream`/`xfer`/`block`/`event`, reset dans le process, accès mémoire IPC), host Python minimal (synchro par quantum, modèles, `sim.var()`, résolution DWARF), **export PNG du framebuffer** (`sim["LCD"].save_png()`, `e2sim snapshot`), fichier `e2sim_toolchains.yaml` + `mk/e2sim.mk`, builds `host32` et `host64` ; **firmware exemple `fan_hmi` seul** avec modèles Python | `fan_hmi` démarre, PNG de l'écran correct, tests `T01–T05` déterministes dans les deux architectures, reset WDT avec debugger attaché |
| **V1** | **Endpoint eScope intégré** (§9.1), relais TCP des streams (§9.3), GUI web générée, record/replay, pytest + JUnit + Excel, CI Jenkins, licence (§17) ; **`fan_motor` + `system.yaml`** ; premier portage d'un produit réel | Tous les tests §16 verts en CI ; eScope trace `fan_motor` en mode `max` ; un produit réel tourne sous e2Sim |
| **V2** | Couverture, fuzzing, bridge vers port COM réel, outil d'extraction makefile, toolchain Linux/WSL avec sanitizers | Couverture publiée ; campagne sanitizers verte |

---

## 15. Positionnement avec e2Unit

| Niveau | Outil | Objet testé | Stimulation |
|---|---|---|---|
| Unitaire | **e2Unit** | une fonction C | vecteurs de stimuli déclarés en YAML |
| Système | **e2Sim** | le firmware complet, en temps virtuel | scénarios pytest, modèles, autres firmwares |
| Cible | e2Unit `jlink` / `emu`, banc | binaire ARM réel | sonde, banc |

Les deux outils sont **indépendants** : chacun son dépôt, sa configuration (toolchains), son code ; aucun
ne lit les fichiers de l'autre. Ils partagent seulement des conventions :
- **pas de recouvrement** : e2Sim ne teste pas des fonctions isolées, e2Unit ne gère pas le temps ni les périphériques ;
- **mêmes conventions** : Python 3.10+, YAML, code retour 0/1/2 (PASS/FAIL/erreur), GNU make ;
- **même modèle de licence** : PolyForm Noncommercial pour l'outil, MIT pour ce qui part dans le firmware (§17) ;
- **même disposition du rapport Excel** (feuilles Summary et Tests, mêmes colonnes) : un test e2Sim porte ses
  exigences (`@e2sim.requirement("FAN-HMI-03")`), `pytest --e2sim-xlsx` produit le rapport (plus une feuille
  Requirements), et les rapports des deux niveaux se rapprochent sans outil commun.

## 16. Projet exemple complet : ventilateur connecté (`examples/fan`)

Code **original**, écrit pour e2Sim et publié avec lui (MIT). C'est la seule référence de code utilisée dans
cette spécification et dans la documentation. Le projet a **deux buts**, avec la même source :

1. **Tester l'ensemble des fonctionnalités d'e2Sim** : chaque fonctionnalité est couverte par au moins un
   test automatique de `tests/`, exécuté en CI dans les deux architectures. C'est le test d'intégration
   d'e2Sim lui-même : une fonctionnalité non couverte par l'exemple n'est pas considérée comme livrée.
2. **Faire la démonstration des fonctionnalités** : `make demo` déroule un scénario commenté, chapitre par
   chapitre, dans la GUI web (et eScope), sur les deux firmwares reliés. La démo n'utilise que l'API publique
   (HTTP JSON de la GUI), et elle est elle-même testée (`make demo-check` : le scénario en mode automatique,
   temps accéléré, avec une vérification par chapitre), pour qu'elle ne casse jamais.

Il sert aussi de **modèle de portage** : HAL d'exemple, adaptateur `hal_e2sim/`, makefile, `board.yaml`,
modèles, tests, configuration VS Code.

### 16.1 Produit fictif
Un ventilateur sur batterie à deux cartes : une **IHM** (boutons, écran, batterie, capteur de
température, mémoire) et une **carte moteur** (PWM, tachymètre, protection courant), reliées par une UART
avec un protocole à CRC.

```
 ┌──────────── fan_hmi ────────────┐   UART_LINK    ┌────────── fan_motor ──────────┐
 │ BTN_POWER, BTN_PLUS, BTN_MINUS  │◄──────────────►│ PWM_MOTOR → modèle moteur      │
 │ LED, SELF_HOLD, MOTOR_EN        │  consigne,     │ TACHO (capture) ← modèle       │
 │ VBAT_ADC ← modèle batterie      │  état, défauts │ CURRENT_ADC ← modèle           │
 │ TEMP_SPI ↔ modèle capteur       │                │ FAULT_IN (EXTI) ← comparateur  │
 │ LCD 128×64 RGB565, EEPROM       │                │ ENABLE ← MOTOR_EN, WDT         │
 │ UART_DEBUG → terminal / TCP     │                │ UART_SCOPE : eScope embarqué   │
 └─────────────────────────────────┘                └────────────────────────────────┘
```

### 16.2 Structure
```
examples/fan/
  hal/            HAL d'exemple : halGpio, halAdc, halPwm, halTimer, halCapture, halExti,
                  halUart, halSpi, halNvm, halLcd, halWdt, halMcu (en-têtes génériques)
  hal_e2sim/      adaptateur HAL → e2sim.h + eScopeCfg.h PC  ← le modèle à recopier dans un dépôt firmware
  fan_hmi/        application IHM (main() superloop, machine d'états, affichage, protocole)
  fan_motor/      application carte moteur (régulation PI, protections, eScope embarqué)
  common/         protocole UART (trames + CRC), utilitaires
  escope/         code cible eScope V3 (copie)
  sim/            hmi.board.yaml, motor.board.yaml, system.yaml, models/*.py
  tests/          tests automatiques (T00…) + images de référence
  demo/           scénario de démonstration (chapitres) + guide DEMO.md
  Makefile        build, test, test-all, demo, demo-check (toolchain : make TOOLCHAIN=…)
  .vscode/        launch / attach gdb, tâches
```

### 16.3 Matrice de couverture : test automatique et démo
Règle : **toute fonctionnalité d'e2Sim a une ligne dans cette matrice**, avec au moins un test automatique ;
une fonctionnalité visible a aussi un chapitre de démo. Une nouvelle fonctionnalité ajoute sa ligne.

| Fonctionnalité e2Sim | Où dans l'exemple | Test | Démo |
|---|---|---|---|
| Superloop `main()` inchangée, yield sur HAL, `e2sim_idle()` | les deux firmwares | tous | 1 |
| Timer périodique + ISR, sections critiques | tick 1 ms, file d'événements boutons | T01 | 2 |
| Port `bit` in / out, verrou d'alimentation | boutons, LED, `SELF_HOLD` | T01, T04 | 1, 10 |
| Bloc framebuffer + PNG, comparaison à une référence | écran 128×64 | T02 | 2 |
| Attente active sur compteur HAL | délai d'init de l'écran | T02 | — |
| Port `stream` + modèle Python | `fan_hmi` seul, carte moteur = modèle `MotorBoard` | T03 | — |
| Bloc NVM persistant | dernière vitesse, compteur de minutes, CRC | T04 | 9, 10 |
| Port `xfer` synchrone | capteur de température SPI | T05 | 5 |
| Port `value` in (ADC brut) | batterie | T05 | 6 |
| Reset dans le process (watchdog) | capteur bloqué → reset WDT | T06 | 8 |
| Port `value` out (PWM) | duty lu par le modèle moteur | T07 | 4 |
| Port `event` (EXTI) | comparateur de courant → coupure immédiate | T08 | 7 |
| Multi-firmware (`system.yaml`) | `fan_hmi` ↔ `fan_motor`, le firmware remplace le modèle | T09 | 2 à 10 |
| Runs longs, temps accéléré | 10 min en quelques secondes | T00, T10 | 9 |
| Injection de fautes | trames corrompues, rotor bloqué, NVM corrompue, capteur absent | T03 à T08 | 5 à 8 |
| Record / replay, sur l'autre architecture | enregistrement d'un scénario, rejoué | T12 | 11 |
| `sim.var()` / `set_var()` | variables des deux firmwares | tous | 3, 9 |
| Endpoint eScope intégré au host | `fan_hmi` sans code eScope | T14 | 3 |
| eScope embarqué + relais TCP d'un stream | `fan_motor` sur `UART_SCOPE` ; `UART_DEBUG` en terminal TCP | T15 | 3 |
| GUI web générée, API JSON | `system.yaml` | GUI | toute la démo |
| Rapport Excel exigences → tests | `pytest --e2sim-xlsx` | CI | — |
| Double architecture | campagne en `host32` et `host64` | CI | — |
| Debug VS Code | `launch` sur un firmware, breakpoint conservé après reset | manuel | annexe du guide |
| Licence | dialogues, bandeau de la GUI, propriété JUnit | CI | — |

### 16.4 Scénario de démonstration (`demo/`)
`make demo` lance la GUI sur `system.yaml` et déroule les chapitres ; chacun s'affiche dans le bandeau de la
GUI et dans la console, et attend Entrée (ou un délai avec `--auto`). Le guide `demo/DEMO.md` donne le texte à
dire et les manipulations à montrer (eScope, debugger).

| # | Chapitre | Ce qu'on montre |
|---|---|---|
| 1 | Mise sous tension | appui POWER : le verrou tient, le firmware démarre sans modification de son code |
| 2 | Deux firmwares | marche, vitesses 1 à 5 : l'IHM commande, la carte moteur régule, l'écran affiche |
| 3 | Observer | ports eScope (endpoint du host et eScope embarqué), `sim.var()` dans la console |
| 4 | Le modèle répond | charge moteur ×1,5 : le PI augmente le rapport cyclique |
| 5 | Capteur SPI | 70 °C : OVER TEMP, moteur arrêté ; retour à 25 °C |
| 6 | Batterie | 9,2 V : BAT LOW |
| 7 | Interruption externe | rotor bloqué : comparateur → coupure dans la milliseconde, MOTOR FAULT, reprise |
| 8 | Watchdog | capteur bloqué : reset WDT dans le même process, WDT RESET affiché |
| 9 | Temps accéléré | vitesse max : les minutes de fonctionnement défilent, sauvées en NVM |
| 10 | Extinction | appui long : sauvegarde, coupure ; rallumage : réglages retrouvés |
| 11 | Rejouer | la démo enregistrée est rejouée sans modèle : mêmes sorties |

### 16.4 Modèles Python
- `Battery` : tension décroissante avec la charge moteur → points ADC ; paramètre `capacity_mAh`.
- `TempSensor` : registres d'un capteur SPI fictif ; paramètres `temp_C`, `no_answer`.
- `Motor` : 1er ordre duty → tr/min, courant ∝ couple ; paramètres `blocked`, `friction`.
- `MotorBoard` (V0 uniquement) : réponse au protocole UART à la place de `fan_motor` ; paramètres
  `no_answer` et `corrupt_crc`.

## 17. Licence

Même modèle qu'e2Unit (et eScope) : l'outil PC est en **source disponible** sous
[PolyForm Noncommercial 1.0.0](../LICENSE.md), et tout ce qui part dans un firmware est sous **MIT**.

### 17.1 Périmètre des licences
| Élément | Licence | Raison |
|---|---|---|
| Host Python (package `e2sim/`, CLI, plugin pytest, GUI web), `mk/`, `docs/` | PolyForm Noncommercial 1.0.0 + licence commerciale | c'est l'outil vendu |
| `libe2sim-target` et `e2sim.h` (`target/`) | MIT | lié au firmware simulé, ne doit imposer aucune contrainte au code du client |
| Firmware exemple (`examples/`), dont l'adaptateur `hal_e2sim/` et le `eScopeCfg.h` PC | MIT | modèles à recopier dans les dépôts firmware (§11) |

Aucun code n'est généré dans le firmware (§6, O2).

Chaque dossier sous MIT a son propre `LICENSE.md` (en-tête d'une ligne + texte MIT), comme `target/`,
`boards/` et `examples/` dans e2Unit. Le `LICENSE.md` racine commence par une note qui délimite les deux
périmètres et se termine par `Required Notice: Copyright Laurent Olive (https://github.com/laurentolive/e2Sim)`.

### 17.2 Types de licence
- **Personnelle** (gratuite) : projets personnels, études, recherche, enseignement ;
- **Démonstration** (gratuite, 1 mois, non renouvelable) : essai en entreprise ;
- **Professionnelle** (abonnement annuel, Lemon Squeezy) : tout usage professionnel.

**Produit Lemon Squeezy distinct** d'e2Unit, dans le même store `esquaresoft` : une clé e2Unit n'active pas
e2Sim et inversement. Une offre groupée éventuelle se fera côté Lemon Squeezy, sans changer le code.

### 17.3 Procédure (reprise d'e2Unit)
Le package `eunit/license/` est **recopié** dans `e2sim/license/` : pas de dépendance de code entre les
dépôts, comme pour le registre de toolchains (§10.1). Seuls changent :
- `product.py` : `PRODUCT_NAME = "e2Sim"`, `PRODUCT_ID` du produit e2Sim (`None` tant qu'il n'est pas en
  vente : aucune clé acceptée), liens d'achat et de portail client ;
- les variables d'environnement, préfixées `E2SIM_` : `E2SIM_LICENSE_KEY`, `E2SIM_NO_DIALOG`, `E2SIM_NO_GUI` ;
- le dossier des fichiers de licence : `%APPDATA%/e2Sim/` (un fichier par type, chiffré DPAPI pour
  l'utilisateur), séparé de celui d'e2Unit.

Le comportement est identique :
- **Vérification au lancement** de `e2sim run` et de `e2sim connect`, et **une fois par session pytest**
  (au chargement du plugin, pas à chaque test). La licence **ne bloque jamais** une simulation : sans choix,
  on retombe sur la Démonstration ; licence expirée → rappel à chaque lancement.
- **Dialogues** : popups, console ou aucun dialogue selon le contexte (§17.4).
- **Poste d'entreprise** (domaine Active Directory ou Entra ID) : une licence Personnelle déclenche un rappel.
- **Professionnelle** : clé activée sur la machine, revalidée en ligne au plus une fois par 24 h, acceptée
  hors ligne 30 jours. `e2sim license deactivate` libère l'activation pour un autre poste.
- **Intégration continue** (variables `CI`, `JENKINS_URL`… détectées) : aucun dialogue. La clé
  Professionnelle est donnée par `E2SIM_LICENSE_KEY` : validée sans être activée (les agents vont et
  viennent), jamais stockée ; agent hors ligne → acceptée pour le run.
- **Commande** : `e2sim license [choose | activate [CLÉ] | deactivate | check | buy | portal]`, sans argument
  elle affiche la licence en cours.

### 17.4 Popups de licence
Reprise telle quelle de `eunit/license/ui.py` : mêmes fenêtres que celles d'eScope, en **tkinter** (livré
avec Python, aucune dépendance), textes en anglais, titre `e2Sim - <fenêtre>`.

**Choix de l'interface**, dans cet ordre :
1. CI détectée ou `E2SIM_NO_DIALOG=1` → **aucun dialogue** : messages sur stderr, chaque fenêtre est
   considérée comme fermée (donc Démonstration) ;
2. affichage disponible (toujours sous Windows) et pas `E2SIM_NO_GUI=1` → **popups** ;
3. stdin sur un terminal → **questions en console**, avec le même enchaînement ;
4. sinon → aucun dialogue, comme en 1.

**Fenêtres** (modales, au premier plan, centrées, adaptées au DPI de l'écran) :
| Fenêtre | Contenu | Fermeture sans valider |
|---|---|---|
| *License Creation* | « How will you use this software? » : 3 boutons radio Personal (Free), Professional (Paid), Demonstration (Free) avec leur description ; bouton Continue | Démonstration |
| *Personal License* | rappel « usage personnel non commercial uniquement » + case à cocher de confirmation obligatoire (avertissement si non cochée) | pas de licence Personnelle → Démonstration |
| *Notice* (poste d'entreprise) | « This computer appears to be managed by an organization… ». Après le choix Personnelle : OK continue, Annuler **revient au choix** ; aux lancements suivants : simple avertissement non bloquant | — |
| *Professional License* | champ de clé, Activate (« Activating… » pendant l'appel Lemon Squeezy, erreur affichée dans la fenêtre sans la fermer), lien *Buy a license*, Cancel / Échap | activation annulée → Démonstration |
| Message | licence expirée, Professionnelle non revalidée depuis 30 jours, erreurs de `e2sim license` | — |

**Enchaînement** au lancement, seulement si aucune licence valide n'est installée : message
d'expiration éventuel → *License Creation* → selon le choix *Notice* + *Personal License*, ou
*Professional License*. Une Démonstration déjà commencée est rechargée, jamais redémarrée.

**Spécificités e2Sim** :
- `e2sim run` : les popups s'affichent **avant** le lancement du firmware et l'ouverture de la GUI web ;
  la simulation ne démarre qu'une fois les fenêtres fermées.
- La **GUI web n'a pas de dialogue de licence** : elle affiche la licence en cours dans son bandeau, avec
  un lien vers l'achat si la licence est expirée.
- **Plugin pytest** : la vérification se fait dans `pytest_configure`, une fois par session. pytest
  capturant stdin, c'est popups si un affichage existe, sinon aucun dialogue ; jamais de question console
  qui bloquerait la session.
- `e2sim connect` (firmware lancé depuis le debugger, §10.3) : popups avant la connexion. Le firmware
  attend en `--wait-host` : pas de timeout pendant le choix.

### 17.5 Traçabilité
La licence en cours apparaît dans la sortie console au lancement, dans les **rapports** (propriété
`license` du JUnit XML, ligne « License » du rapport Excel, §15)
et dans le bandeau de la GUI.

## 18. Suivi
Les actions et points ouverts sont suivis dans les **tickets GitHub** du dépôt
(`https://github.com/laurentolive/e2Sim/issues`), par étiquette : `verification` (à valider sur un
environnement réel), `v1`, `v2`, `example` (projet exemple : tests et démo), `perf`, `doc`.
