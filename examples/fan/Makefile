#################################
# Fan example - e2Sim build of the firmwares
#   make                       default toolchain of the registry (toolchains.yaml)
#   make TOOLCHAIN=host64      other toolchain
#   make test                  build + pytest, TOOLCHAIN as above
#   make test-all              build + pytest on host32 and host64
#################################
E2SIM_ROOT := ../..
include $(E2SIM_ROOT)/mk/e2sim.mk

HAL_E2SIM := $(wildcard hal_e2sim/*.c)
COMMON    := $(wildcard common/*.c)
INCS      := hal hal_e2sim common

$(eval $(call e2sim_firmware,fan_hmi,$(wildcard fan_hmi/*.c) $(COMMON) $(HAL_E2SIM),fan_hmi $(INCS),))

.DEFAULT_GOAL := all
all: $(E2SIM_FIRMWARES)

test: all
	@"$(E2SIM_PY)" -m pytest tests -q --e2sim-toolchain $(E2SIM_TC) $(PYTEST_OPTS)

test-all:
	@$(MAKE) --no-print-directory test TOOLCHAIN=host32
	@$(MAKE) --no-print-directory test TOOLCHAIN=host64

clean:
	@$(E2SIM) fs rm $(BUILD) out

.PHONY: all test test-all clean
