#################################
# e2Sim - common build rules
#
# A firmware makefile only needs:
#   E2SIM_ROOT := ../..
#   include $(E2SIM_ROOT)/mk/e2sim.mk
#   $(eval $(call e2sim_firmware,<name>,<sources>,<include dirs>,<defines>))
#
# Builds, for the selected toolchain, in $(BUILD)/<toolchain>/:
#   e2sim_runner.exe      generic runner (one per toolchain)
#   <name>.dll / .map     the firmware, main() renamed e2sim_app_main
#
# Variables: TOOLCHAIN (default: 'default:' of e2sim_toolchains.yaml, spec §10.1), BUILD, PY.
#################################

ifndef E2SIM_ROOT
$(error E2SIM_ROOT must be set before including e2sim.mk)
endif

-include $(E2SIM_ROOT)/e2sim.local.mk

PY        ?= $(if $(E2SIM_PY),$(E2SIM_PY),python)
BUILD     ?= build
TOOLCHAIN ?=

E2SIM := "$(PY)" $(E2SIM_ROOT)/e2sim_cli.py

# toolchain fragment generated from e2sim_toolchains.yaml (CC, OBJCOPY, GDB, E2SIM_TC, PATH...)
E2SIM_TC_MK := $(shell $(E2SIM) toolchain mk $(TOOLCHAIN) --dir $(BUILD))
ifeq ($(E2SIM_TC_MK),)
$(error e2sim: toolchain configuration error, see above)
endif
include $(E2SIM_TC_MK)
E2SIM := "$(E2SIM_PY)" $(E2SIM_ROOT)/e2sim_cli.py
export E2SIM_PY

OUT := $(BUILD)/$(E2SIM_TC)

E2SIM_WARN   := -Wall -Wextra -Wshadow -Wpointer-arith -Wstrict-prototypes -Wundef
E2SIM_CFLAGS ?= -std=c11 -g3 -O0 -funsigned-char $(E2SIM_WARN)  # -g3: macros in the DWARF (board.yaml)

# fixed image base: stable addresses build after build (eScope, sim.var)
E2SIM_DLL_BASE ?= 0x10000000
ifeq ($(E2SIM_PTR_SIZE),8)
E2SIM_ARCH_LDFLAGS := -Wl,--disable-high-entropy-va
endif

#################################
# runner (generic, one per toolchain)
RUNNER_DIR  := $(E2SIM_ROOT)/target
RUNNER_SRCS := $(RUNNER_DIR)/src/e2sim_runner.c $(RUNNER_DIR)/src/e2sim_wire.c
RUNNER_HDRS := $(wildcard $(RUNNER_DIR)/include/*.h $(RUNNER_DIR)/src/*.h)
RUNNER      := $(OUT)/e2sim_runner.exe
RUNNER_LIB  := $(OUT)/libe2sim_runner.a

E2SIM_INCS := -I$(RUNNER_DIR)/include

$(RUNNER): $(RUNNER_SRCS) $(RUNNER_HDRS) $(E2SIM_TC_MK)
	@echo e2sim: building $@
	@$(E2SIM) fs mkdir $(@D)
	@"$(CC)" $(E2SIM_CFLAGS) -Wconversion $(E2SIM_INCS) -o $@ $(RUNNER_SRCS) \
		-static -Wl,--out-implib,$(RUNNER_LIB) -lws2_32

$(RUNNER_LIB): $(RUNNER) ;

runner: $(RUNNER)

#################################
# firmware DLL: $(call e2sim_firmware,name,sources,include dirs,defines)
define e2sim_firmware
$(OUT)/$(1).dll: $(2) $(wildcard $(addsuffix /*.h,$(3))) $(RUNNER_LIB)
	@echo e2sim: building $$@
	@$$(E2SIM) fs mkdir $$(@D)
	@"$$(CC)" $$(E2SIM_CFLAGS) -Dmain=e2sim_app_main -DE2SIM_DLL_BASE=$$(E2SIM_DLL_BASE) $(addprefix -D,$(4)) $$(E2SIM_INCS) $(addprefix -I,$(3)) \
		-shared -static -o $$@ $(2) $(RUNNER_LIB) \
		-Wl,--image-base=$$(E2SIM_DLL_BASE) -Wl,--disable-dynamicbase $$(E2SIM_ARCH_LDFLAGS) \
		-Wl,-Map=$$(OUT)/$(1).map

.PHONY: $(1)
$(1): $(OUT)/$(1).dll $(RUNNER)
E2SIM_FIRMWARES += $(1)
endef

.PHONY: runner clean
