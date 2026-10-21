#!/usr/bin/env bash
# e2Sim - development environment in WSL (Ubuntu 24.04 or Debian 12): Linux port and sanitizers (docs/dev-setup.md)
set -euo pipefail

sudo apt-get update
sudo apt-get install -y build-essential gcc g++ gdb make gcc-multilib g++-multilib \
    python3 python3-pip python3-venv python3-yaml python3-pytest python3-openpyxl git

mkdir -p ~/.e2sim
if [ ! -f ~/.e2sim/e2sim_toolchains.yaml ] || [ "${1:-}" = "--force" ]; then
    cat > ~/.e2sim/e2sim_toolchains.yaml <<'YAML'
# Toolchains of e2Sim under Linux (WSL)
toolchains:
  linux64:
    arch: x86_64
    prefix: /usr/bin/
  linux32:            # 32 bits builds: gcc -m32 (gcc-multilib)
    arch: i686
    prefix: /usr/bin/
    flags: [-m32]
  linux64-asan:       # sanitizers: AddressSanitizer + UndefinedBehaviorSanitizer
    arch: x86_64
    prefix: /usr/bin/
    flags: ["-fsanitize=address,undefined", -fno-omit-frame-pointer, -fno-sanitize-recover=undefined]
default: linux64
YAML
    echo "created ~/.e2sim/e2sim_toolchains.yaml"
fi

gcc --version | head -1
gdb --version | head -1
python3 -c "import yaml, pytest; print('python ok')"
echo "e2Sim WSL environment ready"
