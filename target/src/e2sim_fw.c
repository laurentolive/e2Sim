/*
 * e2Sim - API version of a firmware build (MIT)
 *
 * Compiled into every firmware DLL / .so by mk/e2sim.mk (no code in the firmware): the runner reads it and the
 * host refuses a firmware built with another major version of e2sim.h, with a clear message.
 */
#include "e2sim.h"

#ifdef _WIN32
#define E2SIM_FW_EXPORT /* MinGW exports every symbol of a DLL without dllexport */
#else
#define E2SIM_FW_EXPORT __attribute__((visibility("default")))
#endif

E2SIM_FW_EXPORT const uint32_t e2sim_fw_api_version = E2SIM_API_VERSION;
