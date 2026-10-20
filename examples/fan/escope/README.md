# eScope target code (copy)

Unmodified copy of the eScope protocol V3 and UART transport target code (eScope, `targetExamples/`, MIT
License, Copyright Laurent Olive), branch `issue-1-pc-simulation` (64 bits addresses, `ESCOPE_ADDR_TO_PTR`,
`ESCOPE_ADDR_IS_VALID`). Used by `fan_motor` to show a firmware that embeds eScope on one of its UARTs,
relayed to TCP by e2Sim (spec §9.3). The configuration of the PC variant is in `../hal_e2sim/eScopeCfg.h`.

Most firmwares do not need it: the eScope endpoint of the e2Sim host works without any code in the firmware
(spec §9.1).
