#################################
# Fan example - e2Sim build of the firmwares
#   make                       default toolchain of e2sim_toolchains.yaml
#   make TOOLCHAIN=host64      other toolchain
#   make test                  build + pytest, TOOLCHAIN as above
#   make test-all              build + pytest on host32 and host64
#   make demo                  demonstration in the GUI, chapter by chapter (DEMO_OPTS="--auto")
#   make demo-check            the demonstration as a test: fast, no browser
#################################
E2SIM_ROOT := ../..
include $(E2SIM_ROOT)/mk/e2sim.mk

COMMON := $(wildcard common/*.c)
INCS   := hal hal_e2sim common escope

# HAL modules used by each board (e2Sim adapter)
HAL_CORE  := halMcu halGpio halAdc halTimer halUart halWdt
HAL_HMI   := $(addprefix hal_e2sim/,$(addsuffix .c,$(HAL_CORE) halSpi halNvm halLcd))
HAL_MOTOR := $(addprefix hal_e2sim/,$(addsuffix .c,$(HAL_CORE) halPwm halCapture halExti))

$(eval $(call e2sim_firmware,fan_hmi,$(wildcard fan_hmi/*.c) $(COMMON) $(HAL_HMI),fan_hmi $(INCS),))
$(eval $(call e2sim_firmware,fan_motor,$(wildcard fan_motor/*.c) escope/eScopeProtocolV3.c $(COMMON) $(HAL_MOTOR),fan_motor $(INCS),))

.DEFAULT_GOAL := all
all: $(E2SIM_FIRMWARES)

test: all
	@"$(E2SIM_PY)" -m pytest tests -q --e2sim-toolchain $(E2SIM_TC) $(PYTEST_OPTS)

demo: all
	@"$(E2SIM_PY)" demo/demo.py --toolchain $(E2SIM_TC) $(DEMO_OPTS)

demo-check: all
	@"$(E2SIM_PY)" demo/demo.py --check --toolchain $(E2SIM_TC)

test-all:
	@$(MAKE) --no-print-directory test TOOLCHAIN=host32
	@$(MAKE) --no-print-directory test TOOLCHAIN=host64

clean:
	@$(E2SIM) fs rm $(BUILD) out

.PHONY: all test test-all demo demo-check clean
