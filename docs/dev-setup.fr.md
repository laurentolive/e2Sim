# Environnement de développement d'e2Sim

[English](dev-setup.md) | **Français**

Tout ce qu'il faut pour développer e2Sim et lancer tous ses tests : Windows (plateforme principale) et WSL
(portage Linux, sanitizers, ticket #20). Versions utilisées à l'écriture de cette page (2026-10) : elles
fonctionnent, des versions plus récentes devraient aussi.

## Windows

| Outil | Version | Sert à |
|---|---|---|
| Python | 3.12 (≥ 3.10) | host, tests, aides des makefiles |
| paquets pip | `pyyaml` 6, `pytest` 7+ (9.1), `openpyxl` 3.1 | fichiers board, tests, rapport Excel |
| GNU make | 4.0 (`C:/Dev/Tools/make.exe`) | builds |
| MSYS2 | `mingw-w64-i686-gcc` / `-gdb` / `-binutils` (13.2 / 14.1 / 2.41) | toolchain `host32`, gdb du host |
| MSYS2 | `mingw-w64-ucrt-x86_64-gcc` / `-gdb` / `-binutils` | toolchain `host64` |
| git, GitHub CLI `gh` | 2.51, 2.101 | dépôt, tickets |
| VS Code + extension C/C++ (ms-vscode.cpptools) | 1.142 | debug (launch / attach avec gdb) |
| Node.js (facultatif) | 24 | vérification de syntaxe de la page de la GUI web (`node --check`) |
| eScope (facultatif) | branche `issue-1-pc-simulation` | traces (tickets #2, #3) |

Étapes (ou lancer [tools/setup-windows.ps1](../tools/setup-windows.ps1), qui fait 2 et 3) :

1. Installer Python 3.12 (avec le lanceur `py`), Git, GitHub CLI (`gh auth login`), VS Code, MSYS2 (ici dans
   `C:/Dev/Tools/msys64`, tout chemin convient) et GNU make pour Windows.
2. Paquets MSYS2 :
   ```
   pacman -S --needed mingw-w64-i686-gcc mingw-w64-i686-gdb mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-gdb
   ```
3. Paquets Python : `python -m pip install pyyaml pytest openpyxl`
   (ou `pip install -e ".[test,report]"` dans le dépôt : e2sim installé en mode développement).
4. Toolchains : copier `e2sim_toolchains.yaml.example` en `e2sim_toolchains.yaml` à la racine du dépôt et adapter
   les chemins (`python`, `prefix`, `path` de chaque toolchain).
5. Vérifier :
   ```
   python e2sim_cli.py toolchain list
   cd selftest/blink && make && make TOOLCHAIN=host64 && cd ..
   python -m pytest -q . && python -m pytest -q . --e2sim-toolchain host64
   cd ../examples/fan && make test-all && make demo-check
   ```

Remarques :
- La procédure de licence tourne avec les tests : `E2SIM_NO_DIALOG=1` évite les dialogues ; pour ne pas toucher
  à votre propre licence pendant les tests, pointer `APPDATA` vers un dossier de travail (mais `gh` garde sa
  connexion dans `APPDATA` : ne pas le changer pour les commandes `gh`).
- `make` doit trouver le Python système par `e2sim_toolchains.yaml` (`python:`) : le `PATH` d'une toolchain
  met le Python de MSYS2 en premier.

## WSL (portage Linux, sanitizers)

1. Dans un PowerShell administrateur : `wsl --install -d Ubuntu-24.04`, redémarrer, créer l'utilisateur Linux.
2. Dans Ubuntu, depuis le dépôt (`/mnt/c/Dev/esquaresoft/e2Sim`) :
   ```
   bash tools/setup-wsl.sh
   ```
   Il installe : `build-essential gcc gdb make gcc-multilib g++-multilib` (builds i686), `python3 python3-pip
   python3-venv python3-yaml python3-pytest python3-openpyxl`, `git` (gcov est fourni avec gcc), et crée
   `~/.e2sim/e2sim_toolchains.yaml` avec les toolchains `linux64` (x86_64) et `linux32` (`-m32`).
3. Travailler dans le système de fichiers Linux pour la vitesse (`git clone` dans `~/`), ou directement dans
   `/mnt/c/...` (plus lent).

Le portage Linux lui-même (ucontext à la place des fibers, `dlopen`, `shm_open`,
`-fsanitize=address,undefined`) est l'objet du ticket #20.
