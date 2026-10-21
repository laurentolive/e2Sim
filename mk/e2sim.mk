#################################
# e2Sim - common build rules
#
# A firmware makefile only needs:
#   E2SIM_ROOT := ../..
#   include $(E2SIM_ROOT)/mk/e2sim.mk
#   $(eval $(call e2sim_firmware,<name>,<sources>,<include dirs>,<defines>))
#
# Builds, for the selected toolchain, in $(BUILD)/<toolchain>/:
#   e2sim_runner(.exe)    generic runner (one per toolchain)
#   <name>.dll|.so / .map the firmware (DLL on Windows, shared object on Linux), main() renamed e2sim_app_main
#
# Variables: TOOLCHAIN (default: 'default:' of e2sim_toolchains.yaml, spec §10.1), BUILD, PY.
#################################

ifndef E2SIM_ROOT
$(error E2SIM_ROOT must be set before including e2sim.mk)
endif

-include $(E2SIM_ROOT)/e2sim.local.mk

ifeq ($(OS),Windows_NT)
E2SIM_WIN := 1
endif
PY        ?= $(if $(E2SIM_PY),$(E2SIM_PY),$(if $(E2SIM_WIN),python,python3))
BUILD     ?= build
TOOLCHAIN ?=

# command line: script of the repository, else the installed package (pip)
E2SIM_CLI := $(if $(wildcard $(E2SIM_ROOT)/e2sim_cli.py),$(E2SIM_ROOT)/e2sim_cli.py,-m e2sim)
E2SIM := "$(PY)" $(E2SIM_CLI)

# toolchain fragment generated from e2sim_toolchains.yaml (CC, OBJCOPY, GDB, E2SIM_TC, PATH...)
E2SIM_TC_MK := $(shell $(E2SIM) toolchain mk $(TOOLCHAIN) --dir $(BUILD))
ifeq ($(E2SIM_TC_MK),)
$(error e2sim: toolchain configuration error, see above)
endif
include $(E2SIM_TC_MK)
E2SIM := "$(E2SIM_PY)" $(E2SIM_CLI)
export E2SIM_PY

OUT := $(BUILD)/$(E2SIM_TC)

E2SIM_WARN   := -Wall -Wextra -Wshadow -Wpointer-arith -Wstrict-prototypes -Wundef
E2SIM_CFLAGS ?= -std=c11 -g3 -O0 -funsigned-char $(E2SIM_WARN)  # -g3: macros in the DWARF (board.yaml)

# COVERAGE=1: gcov counters, written when the DLL is unloaded (reset, end); report: e2sim coverage $(OUT)
ifeq ($(COVERAGE),1)
E2SIM_FW_FLAGS += --coverage
endif
# the DLLs are rebuilt when the options change (COVERAGE, defines...)
E2SIM_STAMP := $(OUT)/firmware.flags
$(shell $(E2SIM) fs stamp $(E2SIM_STAMP) "$(E2SIM_CFLAGS) $(E2SIM_FW_FLAGS)")

comma := ,
ifdef E2SIM_WIN
# fixed image base: stable addresses build after build (eScope, sim.var)
E2SIM_DLL_BASE ?= 0x10000000
E2SIM_EXE      :=.exe
E2SIM_LIB_EXT  :=.dll
ifeq ($(E2SIM_PTR_SIZE),8)
E2SIM_ARCH_LDFLAGS := -Wl,--disable-high-entropy-va
endif
E2SIM_FW_LINK = -shared -static $(RUNNER_LIB) -Wl,--image-base=$(E2SIM_DLL_BASE) -Wl,--disable-dynamicbase $(E2SIM_ARCH_LDFLAGS)
else
# Linux: the firmware is a shared object (-fPIC) resolving e2sim_* in the runner (-rdynamic)
E2SIM_DLL_BASE ?= 0
E2SIM_EXE      :=
E2SIM_LIB_EXT  :=.so
E2SIM_FW_LINK  = -shared -fPIC
endif

#################################
# runner (generic, one per toolchain)
RUNNER_DIR  := $(E2SIM_ROOT)/target
RUNNER_SRCS := $(RUNNER_DIR)/src/e2sim_runner.c $(RUNNER_DIR)/src/e2sim_wire.c \
               $(RUNNER_DIR)/src/e2sim_os_win.c $(RUNNER_DIR)/src/e2sim_os_posix.c
RUNNER_HDRS := $(wildcard $(RUNNER_DIR)/include/*.h $(RUNNER_DIR)/src/*.h)
RUNNER      := $(OUT)/e2sim_runner$(E2SIM_EXE)
RUNNER_LIB  := $(if $(E2SIM_WIN),$(OUT)/libe2sim_runner.a)
RUNNER_LINK := $(if $(E2SIM_WIN),-static -Wl$(comma)--out-implib$(comma)$(RUNNER_LIB) -lws2_32,-rdynamic -ldl -lpthread)

E2SIM_INCS := -I$(RUNNER_DIR)/include

$(RUNNER): $(RUNNER_SRCS) $(RUNNER_HDRS) $(E2SIM_TC_MK)
	@echo e2sim: building $@
	@$(E2SIM) fs mkdir $(@D)
	@"$(CC)" $(E2SIM_ARCH_FLAGS) $(E2SIM_CFLAGS) -Wconversion $(E2SIM_INCS) -o $@ $(RUNNER_SRCS) \
		$(RUNNER_LINK)

ifdef E2SIM_WIN
$(RUNNER_LIB): $(RUNNER) ;
endif

runner: $(RUNNER)

#################################
# firmware DLL: $(call e2sim_firmware,name,sources,include dirs,defines)
define e2sim_firmware
$(OUT)/$(1)$(E2SIM_LIB_EXT): $(2) $(wildcard $(addsuffix /*.h,$(3))) $(RUNNER_LIB) $$(E2SIM_STAMP)
	@echo e2sim: building $$@
	@$$(E2SIM) fs mkdir $$(@D)
	@"$$(CC)" $$(E2SIM_ARCH_FLAGS) $$(E2SIM_CFLAGS) $$(E2SIM_FW_FLAGS) -Dmain=e2sim_app_main -DE2SIM_DLL_BASE=$$(E2SIM_DLL_BASE) $(addprefix -D,$(4)) $$(E2SIM_INCS) $(addprefix -I,$(3)) \
		-o $$@ $(2) $$(E2SIM_FW_LINK) -Wl,-Map=$$(OUT)/$(1).map

.PHONY: $(1)
$(1): $(OUT)/$(1)$(E2SIM_LIB_EXT) $(RUNNER)
E2SIM_FIRMWARES += $(1)
endef

.PHONY: runner clean
