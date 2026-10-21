# Changelog

Semantic versioning: the version of the package (`e2sim --version`) and the tag `vX.Y.Z`. The target API
(`E2SIM_API_VERSION` in `e2sim.h`) has its own major.minor: a new major breaks the firmware builds (rebuild with
`make`), the host refuses a firmware of another major with a clear message.

## 1.0.0 - 2026-10-22

First version. API 1.0, runner protocol 5.

- Firmware run on the PC unchanged: DLL (Windows) or `.so` (Linux) loaded by a generic runner, `main()` in a
  fiber, superloop, virtual time synchronised per quantum, timers and interrupts, critical sections.
- Ports `bit`, `value`, `stream`, `xfer`, `block`, `event`; NVM blocks, framebuffers with PNG comparison; line
  rate (`baud:`), force / release of an input driven by a model; indexes of `board.yaml` by enum or `#define`.
- Reset in the process (DLL reloaded, debugger kept) or by a new process; power latch.
- Several firmwares linked in a `system.yaml`; Python models at HAL data level.
- eScope: V3 endpoint in the host for every firmware, embedded eScope through a TCP relay, 32 / 64 bits addresses;
  fixed ports with fallback (reusable eScope workspaces).
- Web GUI generated from `board.yaml` (product image `gui: skin`), JSON API, real time / ×10 / max, pause, step;
  `gui --connect` for a firmware started by the debugger.
- pytest plugin, JUnit, Excel report requirements → tests; record / replay (also on the other architecture);
  hang diagnosis with the stack; gcov coverage; fuzzing of frame parsers; `e2sim extract` from the target build.
- Toolchains of the machine in `e2sim_toolchains.yaml` (independent of the other tools); i686 and x86_64
  (Windows MSYS2), i686 and x86_64 (Linux), AddressSanitizer / UBSan / LeakSanitizer reports.
- License: PolyForm Noncommercial for the tool, MIT for the target side; demonstration license by default.
- Example project and coverage matrix: [fan-demo](https://github.com/laurentolive/fan-demo).
