/* Example HAL on e2Sim - NVM: persistent block (file *.nvm.bin) (MIT) */
#include <string.h>

#include "halCfg.h"
#include "halNvm.h"
#include "halE2sim.h"

static uint8_t *s_nvm;

void halNvm_Init(void)
{
    e2sim_yield();
    s_nvm = e2sim_block(HALSIM_BLOCK_NVM, HAL_NVM_SIZE);
}

size_t halNvm_Size(void) { return HAL_NVM_SIZE; }

void halNvm_Read(uint32_t addr, void *data, size_t len)
{
    e2sim_yield();
    if ((s_nvm != NULL) && (addr + len <= HAL_NVM_SIZE))
    {
        memcpy(data, &s_nvm[addr], len);
    }
}

void halNvm_Write(uint32_t addr, const void *data, size_t len)
{
    e2sim_yield();
    if ((s_nvm != NULL) && (addr + len <= HAL_NVM_SIZE))
    {
        memcpy(&s_nvm[addr], data, len);
    }
}
