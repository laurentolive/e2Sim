# e2Sim - development environment on Windows: MSYS2 packages and Python packages (docs/dev-setup.md)
# Prerequisites installed by hand: Python 3.12, Git, GitHub CLI, VS Code, MSYS2, GNU make.
param(
    [string]$Msys2 = "C:\Dev\Tools\msys64",
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"

& "$Msys2\usr\bin\bash.exe" -lc "pacman -S --noconfirm --needed mingw-w64-i686-gcc mingw-w64-i686-gdb mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-gdb"
& $Python -m pip install --upgrade pyyaml pytest openpyxl

$root = Split-Path -Parent $PSScriptRoot
$cfg = Join-Path $root "e2sim_toolchains.yaml"
if (-not (Test-Path $cfg)) {
    Copy-Item (Join-Path $root "e2sim_toolchains.yaml.example") $cfg
    Write-Output "created $cfg : check the paths"
}
& $Python (Join-Path $root "e2sim_cli.py") toolchain list
