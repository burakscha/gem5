# ROI markers in the SPEC CPU2017 Fortran sources

The SpillDetector and gem5's own ROI statistics count only between
`m5_work_begin(0, 0)` and `m5_work_end(0, 0)`. The C/C++ benchmarks call them
from C (`#include <gem5/m5ops.h>`); these patches add the same calls to the six
Fortran benchmarks through a `bind(C)` interface to libm5 (linked by
`EXTRA_LIBS = -lm5` in `cpu2017/config/bkaya-riscv.cfg`).

As in the C benchmarks, the ROI starts after input reading and setup and
covers the main computation:

| benchmark | ROI |
|---|---|
| 503.bwaves_r | the time-stepping loop of `shell` (`shell_lam.F`) |
| 548.exchange2_r | the puzzle loop `fine` of `test_work` |
| 549.fotonik3d_r | the run loop around `leapfrog` (time stepping) in `yeemain.F90` |
| 554.roms_r | `ROMS_run`, after `ROMS_initialize` (`ocean.h`, included by `master.F90`) |
| 521.wrf_r | `wrf_run`, after `wrf_init` and `wrf_dfi` |
| 527.cam4_r | `ccsm_run`, after `ccsm_init` |

Apply from `cpu2017/` with `patch -p1 < <benchmark>.patch`, then build with
`runcpu --config=bkaya-riscv --action=build <benchmark>`. wrf and cam4 also
need the `521.wrf_r` / `527.cam4_r` sections of that config
(`-fallow-argument-mismatch` for GCC >= 10, plus SPEC's portability flags).
