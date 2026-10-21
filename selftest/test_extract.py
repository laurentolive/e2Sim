"""e2sim extract: sources / includes / defines of a target build, MCU HAL and BSP excluded."""

import json
import subprocess
import sys
from pathlib import Path

from conftest import make_program
from e2sim import extract

TARGET_MAKEFILE = """\
CC := arm-none-eabi-gcc
CFLAGS := -mcpu=cortex-m4 -mthumb -O2 -Iapp -I hal -Ihal/mcu -Ibsp -DPRODUCT=3 -D BOARD_REV=2 -DUSE_FPU
SRCS := app/main.c app/ctrl.c hal/mcu/gpio_mcu.c bsp/startup.c
OBJS := $(SRCS:%.c=build/%.o)
all: build/fw.elf
build/fw.elf: $(OBJS)
\t@$(CC) $(CFLAGS) -T bsp/link.ld -o $@ $^
build/%.o: %.c
\t@mkdir -p $(dir $@)
\t@$(CC) $(CFLAGS) -c $< -o $@
"""


def tree(tmp: Path) -> Path:
    fw = tmp / "fw"
    for f in ("app/main.c", "app/ctrl.c", "hal/mcu/gpio_mcu.c", "bsp/startup.c", "e2sim_hal/gpio_e2sim.c"):
        (fw / f).parent.mkdir(parents=True, exist_ok=True)
        (fw / f).write_text("int x;\n")
    (fw / "Makefile").write_text(TARGET_MAKEFILE)
    return fw


def check(text: str):
    srcs = text[text.index("SRCS :="):text.index("INCS :=")]
    incs = text[text.index("INCS :="):text.index("DEFS :=")]
    defs = text[text.index("DEFS :="):text.index("$(eval")]
    assert "app/main.c" in srcs and "app/ctrl.c" in srcs and "e2sim_hal/gpio_e2sim.c" in srcs
    assert "gpio_mcu.c" not in srcs and "startup.c" not in srcs, "MCU HAL and BSP excluded"
    assert "app" in incs and "hal \\" in incs and "hal/mcu" not in incs and "bsp" not in incs
    assert "PRODUCT=3" in defs and "BOARD_REV=2" in defs and "USE_FPU" not in defs
    assert "mcpu" not in text
    assert "$(eval $(call e2sim_firmware,fw,$(FW_SRCS),$(FW_INCS),$(FW_DEFS)))" in text


def test_extract_from_make(tmp_path):
    fw = tree(tmp_path)
    compiles = extract.from_make(make_program(), fw)  # dry mode: no ARM compiler needed
    assert len(compiles) == 4
    text = extract.make_fragment(compiles, "fw", fw, exclude=["*/hal/mcu*", "*/bsp*"],
                                 adapter=[fw / "e2sim_hal"], drop_defines=["USE_FPU"])
    check(text)


def test_extract_from_compdb(tmp_path):
    fw = tree(tmp_path)
    db = [{"directory": str(fw), "file": f, "command": f"arm-none-eabi-gcc -mcpu=cortex-m4 -Iapp -I hal -Ihal/mcu "
           f"-Ibsp -DPRODUCT=3 -D BOARD_REV=2 -DUSE_FPU -c {f} -o x.o"}
          for f in ("app/main.c", "app/ctrl.c", "hal/mcu/gpio_mcu.c", "bsp/startup.c")]
    (fw / "compile_commands.json").write_text(json.dumps(db))
    out = fw / "e2sim" / "e2sim_sources.mk"
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "e2sim_cli.py"), "extract", "--compdb", str(fw / "compile_commands.json"),
                        "--exclude", "*/hal/mcu*", "--exclude", "*/bsp*", "--adapter", str(fw / "e2sim_hal"),
                        "--drop-define", "USE_FPU", "--name", "fw", "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = out.read_text()
    check(text)
    assert "../app/main.c" in text, "paths relative to the fragment"
