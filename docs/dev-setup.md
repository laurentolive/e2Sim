# Development environment of e2Sim

**English** | [Français](dev-setup.fr.md)

Everything needed to develop e2Sim itself and run all its tests: Windows (main platform) and WSL (Linux port,
sanitizers, ticket #20). Versions in use when this page was written (2026-10): known to work, newer ones should too.

## Windows

| Tool | Version | Used for |
|---|---|---|
| Python | 3.12 (≥ 3.10) | host, tests, makefile helpers |
| pip packages | `pyyaml` 6, `pytest` 7+ (9.1), `openpyxl` 3.1 | board files, tests, Excel report |
| GNU make | 4.0 (`C:/Dev/Tools/make.exe`) | builds |
| MSYS2 | `mingw-w64-i686-gcc` / `-gdb` / `-binutils` (13.2 / 14.1 / 2.41) | `host32` toolchain, gdb of the host |
| MSYS2 | `mingw-w64-ucrt-x86_64-gcc` / `-gdb` / `-binutils` | `host64` toolchain |
| git, GitHub CLI `gh` | 2.51, 2.101 | repository, issues |
| VS Code + extension C/C++ (ms-vscode.cpptools) | 1.142 | debug (launch / attach with gdb) |
| Node.js (optional) | 24 | syntax check of the page of the web GUI (`node --check`) |
| eScope (optional) | branch `issue-1-pc-simulation` | traces (tickets #2, #3) |

Steps (or run [tools/setup-windows.ps1](../tools/setup-windows.ps1), which does 2 and 3):

1. Install Python 3.12 (with `py` launcher), Git, GitHub CLI (`gh auth login`), VS Code, MSYS2 (in
   `C:/Dev/Tools/msys64` here, any path works) and GNU make for Windows.
2. MSYS2 packages:
   ```
   pacman -S --needed mingw-w64-i686-gcc mingw-w64-i686-gdb mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-gdb
   ```
3. Python packages: `python -m pip install pyyaml pytest openpyxl`
   (or `pip install -e ".[test,report]"` in the repository: e2sim installed in development mode).
4. Toolchains: copy `e2sim_toolchains.yaml.example` to `e2sim_toolchains.yaml` at the root of the repository and
   adapt the paths (`python`, `prefix`, `path` of each toolchain).
5. Check:
   ```
   python e2sim_cli.py toolchain list
   cd selftest/blink && make && make TOOLCHAIN=host64 && cd ..
   python -m pytest -q . && python -m pytest -q . --e2sim-toolchain host64
   # example project: fan-demo, against this working copy (next to e2Sim)
   cd ../../fan-demo && make E2SIM_ROOT=../e2Sim test-all demo-check
   ```

Notes:
- The license procedure runs with the tests: set `E2SIM_NO_DIALOG=1` to avoid the dialogs; to keep your own
  license untouched while testing, point `APPDATA` to a scratch directory (but `gh` keeps its login in `APPDATA`:
  do not change it for `gh` commands).
- `make` must find the system Python through `e2sim_toolchains.yaml` (`python:`): the `PATH` of a toolchain
  puts the MSYS2 Python first.

## WSL (Linux port, sanitizers)

1. In an administrator PowerShell: `wsl --install -d Ubuntu-24.04` or `wsl --install -d Debian` (Debian 12:
   Python 3.11, gcc 12, same packages), reboot, create the Linux user.
2. In the Linux distribution, from the repository (`/mnt/c/Dev/esquaresoft/e2Sim`):
   ```
   bash tools/setup-wsl.sh
   ```
   It installs: `build-essential gcc gdb make gcc-multilib g++-multilib` (i686 builds), `python3 python3-pip
   python3-venv python3-yaml python3-pytest python3-openpyxl`, `git` (gcov comes with gcc), and
   creates `~/.e2sim/e2sim_toolchains.yaml` with the `linux64` (x86_64) and `linux32` (`-m32`) toolchains.
3. Work in the Linux file system for speed (`git clone` in `~/`), or directly in `/mnt/c/...` (slower).

Then, in the repository (the Windows `e2sim_toolchains.yaml` at its root would be found first):
```
export E2SIM_TOOLCHAINS=~/.e2sim/e2sim_toolchains.yaml E2SIM_NO_DIALOG=1
cd selftest/blink && make && make TOOLCHAIN=linux32 && make TOOLCHAIN=linux64-asan && cd ..
python3 -m pytest -q . && python3 -m pytest -q . --e2sim-toolchain linux64-asan
cd ../../fan-demo && make E2SIM_ROOT=../e2Sim test-all && make E2SIM_ROOT=../e2Sim TOOLCHAIN=linux64-asan test
```
Tested (2026-10-21): Debian 13, gcc 14.2, gdb 16.3, make 4.4, Python 3.13.
