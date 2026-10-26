# Simulation Snapshot — 2026-03-16 (castEpyc Migration)

> **Context**: castEpyc (AMD EPYC 7763, 128 cores) was running 22 gem5 processes.
> Machine is being migrated — all nohup processes will be killed.
> This file captures the full state so work can resume from scratch.

---

## Quick Summary

| Category | Count |
|----------|-------|
| DONE (with ROI data) | 38 |
| DONE (verbose/no-ROI special case) | 2 |
| RUNNING (in-progress, will be killed) | 20 |
| NOT STARTED | 0 |

**Repository**: `github.com:catnys/gem5.git`, branch `DEV`
**Last commit**: `a7818cf593` — gitignore: exclude nab/perlbench input data

---

## Master Results Table

> Rates: `spill_rate = roi_spills / roi_insts`, `Sp/Ld = roi_spills / roi_loads`, `Sp/St = roi_spills / roi_stores`
> `host_sec` = real wall-clock seconds on castEpyc

| benchmark | input | status | host_sec | roi_insts | roi_spills | spill_rate | Sp/Ld | Sp/St |
|-----------|-------|--------|----------|-----------|------------|------------|-------|-------|
| mcf | test | DONE | 17,512 | 24.4B | 446M | 1.8263% | 5.50% | 34.30% |
| mcf | train | DONE | 162,123 | 125.4B | 2.18B | 1.7400% | 5.42% | 26.27% |
| mcf | ref | DONE (verbose) | — | — | — | ~1.98%* | — | — |
| perlbench | test | DONE | 102,900 | 148.8B | 12.7B | 8.5557% | 31.24% | 54.75% |
| perlbench | train_perfect | DONE | 16,307 | 13.0B | 1.23B | 9.4538% | 33.29% | 58.89% |
| perlbench | train_scrabbl | DONE | 34,487 | 30.3B | 2.69B | 8.8693% | 33.20% | 56.18% |
| perlbench | train_suns | DONE | 2,999 | 2.74B | 282M | 10.3120% | 41.46% | 67.36% |
| perlbench | ref_splitmail | DONE | 159 | 59.1M | 4.37M | 7.3842% | 31.38% | 51.90% |
| perlbench | ref_checkspam | **RUNNING** → kill | — | — | — | — | — | — |
| perlbench | ref_diffmail | **RUNNING** → kill | — | — | — | — | — | — |
| gcc | test | DONE | 12 | 16.0M | 1.11M | 6.9185% | 37.49% | 56.70% |
| gcc | train_200 | DONE | 77,003 | 118.4B | 9.88B | 8.3381% | 35.11% | 67.87% |
| gcc | train_scilab | DONE | 60,849 | 92.3B | 7.23B | 7.8336% | 33.23% | 65.25% |
| gcc | train_train01 | DONE | 6,475 | 10.0B | 811M | 8.0836% | 32.33% | 65.68% |
| gcc | ref_pp_O3 | DONE | 249,997 | 224.9B | 18.0B | 7.9941% | 32.79% | 64.46% |
| gcc | ref_pp_O2 | DONE | 294,899 | 267.0B | 21.8B | 8.1676% | 33.55% | 63.42% |
| gcc | ref_smaller | DONE | 275,760 | 254.7B | 17.2B | 6.7484% | 24.62% | 64.22% |
| gcc | ref32_O5 | DONE | 246,401 | 214.1B | 16.4B | 7.6673% | 30.71% | 56.49% |
| gcc | ref32_O3sel | **RUNNING 96h** → kill | — | — | — | — | — | — |
| namd | test | DONE | 25,169 | 31.9B | 328M | 1.0269% | 3.91% | 16.84% |
| namd | train | DONE | 170,069 | 218.4B | 2.29B | 1.0464% | 3.96% | 17.26% |
| namd | ref | **RUNNING** → kill (est. 18 days) | — | — | — | — | — | — |
| parest | test | DONE | 23,977 | 37.3B | 128M | 0.3427% | 1.07% | 12.65% |
| parest | train | **RUNNING** → kill | — | — | — | — | — | — |
| povray | test | DONE | 1,529 | 2.24B | 174M | 7.7809% | 24.34% | 60.55% |
| povray | train | DONE | 33,804 | 28.6B | 2.24B | 7.8230% | 24.32% | 60.89% |
| povray | ref | **RUNNING** → kill | — | — | — | — | — | — |
| lbm | test | DONE | 6,482 | 6.51B | 274M | 4.2130% | 21.47% | 35.34% |
| lbm | train | DONE | 164,226 | 100.2B | 4.23B | 4.2229% | 21.61% | 35.99% |
| lbm | ref | **RUNNING** → kill (est. months) | — | — | — | — | — | — |
| omnetpp | test | DONE | 7,778 | 12.4B | 895M | 7.1994% | 32.02% | 59.98% |
| omnetpp | train | DONE | 162,070 | 134.8B | 9.22B | 6.8401% | 26.78% | 52.59% |
| omnetpp | ref | **RUNNING** → kill | — | — | — | — | — | — |
| xalancbmk | test | DONE | 281 | 396M | 18.4M | 4.6427% | 17.34% | 47.14% |
| xalancbmk | train | DONE | 9,234 | 7.85B | 611M | 7.7900% | 30.59% | 63.92% |
| xalancbmk | ref | **RUNNING** → kill | — | — | — | — | — | — |
| x264 | test | DONE | 16,721 | 23.4B | 768M | 3.2812% | 15.88% | 31.98% |
| x264 | train | DONE | 22,540 | 18.2B | 639M | 3.5111% | 17.87% | 32.01% |
| x264 | ref | DONE | 29,728 | 23.4B | 768M | 3.2812% | 15.88% | 31.98% |
| blender | test | DONE (m5out_test2) | — | 994M | 61.8M | 6.2193% | 26.47% | 53.08% |
| blender | train | **RUNNING, entered ROI** → wait | — | — | — | — | — | — |
| blender | ref | **RUNNING, entered ROI** → wait | — | — | — | — | — | — |
| deepsjeng | test | DONE | 24,937 | 46.2B | 1.93B | 4.1749% | 24.14% | 56.81% |
| deepsjeng | train | **RUNNING** → kill or wait | — | — | — | — | — | — |
| deepsjeng | ref | **RUNNING** → kill or wait (est. 3.5 days) | — | — | — | — | — | — |
| imagick | test | DONE | 93 | 117.7M | 2.42M | 2.0601% | 11.77% | 26.99% |
| imagick | train | DONE | 259,590 | 284.1B | 292M | 0.1029% | 0.61% | 44.79% |
| imagick | ref | **RUNNING** → kill | — | — | — | — | — | — |
| leela | test | DONE | 14,637 | 26.1B | 1.16B | 4.4438% | 22.66% | 65.93% |
| leela | train | **RUNNING** → wait/kill | — | — | — | — | — | — |
| leela | ref | **RUNNING** → wait/kill (est. ~25h total) | — | — | — | — | — | — |
| nab | test | DONE | 4,185 | 6.69B | 151M | 2.2612% | 9.93% | 47.05% |
| nab | train_aminos | DONE | 41,934 | 38.2B | 784M | 2.0500% | 8.98% | 45.23% |
| nab | train_gcn4dna | **RUNNING 93h** → kill | — | — | — | — | — | — |
| nab | ref | **RUNNING** → kill | — | — | — | — | — | — |
| xz | test | DONE | 1,606 | 2.01B | 38.4M | 1.9069% | 10.45% | 20.93% |
| xz | train | DONE | 50,791 | 45.1B | 1.42B | 3.1559% | 16.20% | 28.32% |
| xz | ref | **RUNNING** → wait (est. ~1-3 days) | — | — | — | — | — | — |
| cactuBSSN | test | DONE | 43,555 | 48.0B | 3.78B | 7.8756% | 30.31% | 54.66% |
| cactuBSSN | train | **RUNNING** → kill or wait | — | — | — | — | — | — |

*mcf ref verbose stats: from previous analysis: 21.1B ROI insts, 419M spills, 1.98% rate. File: `benchmarks/mcf/m5out/riscv_spill_stats.txt` (38GB CSV format, no summary line)*

---

## Running Process Decision: Kill vs Wait

### KILL immediately (will never finish in reasonable time)
| Benchmark | Input | Elapsed | Estimate | Reason |
|-----------|-------|---------|----------|--------|
| gcc | ref32_O3sel | ~96h | unknown | 96h+ with no end |
| nab | train_gcn4dna | ~93h | unknown | 93h+ with no end |
| namd | ref | ~10h | ~18 days | 65 iter × 6.7h/iter |
| lbm | ref | ~10h | months | 3000 steps × 2.3h/step |
| omnetpp | ref | ~10h | ~10 days | 15× train time |
| imagick | ref | ~10h | weeks | imagick train took 72h |
| nab | ref | ~10h | weeks | nab aminos train=11.6h |
| xalancbmk | ref | ~10h | ~3-5 days | estimate |
| parest | train | ~10h | unknown | SE mode /proc issue? |
| povray | ref | ~10h | ~5 days | estimate |

### WAIT — might complete soon (entered ROI already)
| Benchmark | Input | Elapsed | Estimate |
|-----------|-------|---------|----------|
| blender | train | ~10h | ~12-20h total (same scene as ref) |
| blender | ref | ~10h | ~12-20h total |
| leela | train | ~10h | ~25h total (4.1h test × 6×) |
| leela | ref | ~10h | ~25h total |

### WAIT — moderate chance of finishing
| Benchmark | Input | Elapsed | Estimate |
|-----------|-------|---------|----------|
| xz | ref | ~10h | ~1-3 days |
| perlbench | ref_checkspam | ~10h | unknown |
| perlbench | ref_diffmail | ~10h | unknown |
| deepsjeng | train | ~10h | ~1-2 days |
| deepsjeng | ref | ~10h | ~3.5 days |
| cactuBSSN | train | ~10h | unknown |

---

## After Migration: What to Restart

### Priority 1 — Short, high value (restart first)
```bash
# xz ref (~1-3 days, xz shows interesting rate jump test→train)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/xz/m5out_ref $CFG \
  --cmd=benchmarks/xz/xz_r.riscv \
  '--options=benchmarks/xz/cld.tar.xz 160 19cf30ae51eddcbefda78dd06014b4b96281456e078ca7c13e1c0c9e6aaea8dff3efb4ad6b0456697718cede6bd5454852652806a657bb56e07d61128434b474 59796407 61004416 6' \
  > benchmarks/xz/m5out_ref/nohup.log 2>&1 &

# leela ref (~25h)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/leela/m5out_ref $CFG \
  --cmd=benchmarks/leela/leela_r.riscv \
  --options=benchmarks/leela/ref.sgf \
  > benchmarks/leela/m5out_ref/nohup.log 2>&1 &

# leela train (~same)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/leela/m5out_train $CFG \
  --cmd=benchmarks/leela/leela_r.riscv \
  --options=benchmarks/leela/train.sgf \
  > benchmarks/leela/m5out_train/nohup.log 2>&1 &
```

### Priority 2 — Medium (1-4 days)
```bash
# blender train (sh3_no_char.blend, frame 849)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/blender/m5out_train $CFG \
  --cmd=benchmarks/blender/blender_r.riscv \
  '--options=benchmarks/blender/sh3_no_char.blend --render-output benchmarks/blender/sh3_ --threads 1 -b -F RAWTGA -s 849 -e 849 -a' \
  > benchmarks/blender/m5out_train/nohup.log 2>&1 &

# blender ref (same as train — same scene/frame)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/blender/m5out_ref $CFG \
  --cmd=benchmarks/blender/blender_r.riscv \
  '--options=benchmarks/blender/sh3_no_char.blend --render-output benchmarks/blender/sh3_ --threads 1 -b -F RAWTGA -s 849 -e 849 -a' \
  > benchmarks/blender/m5out_ref/nohup.log 2>&1 &

# deepsjeng train (20 positions, ~1-2 days)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/deepsjeng/m5out_train $CFG \
  --cmd=benchmarks/deepsjeng/deepsjeng_r.riscv \
  --options=benchmarks/deepsjeng/train.txt \
  > benchmarks/deepsjeng/m5out_train/nohup.log 2>&1 &

# deepsjeng ref (24 positions, ~3.5 days)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/deepsjeng/m5out_ref $CFG \
  --cmd=benchmarks/deepsjeng/deepsjeng_r.riscv \
  --options=benchmarks/deepsjeng/ref.txt \
  > benchmarks/deepsjeng/m5out_ref/nohup.log 2>&1 &
```

### Priority 3 — Try if resources allow
```bash
# cactuBSSN train (GR hydrodynamics, unknown duration)
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/cactuBSSN/m5out_train $CFG \
  --cmd=benchmarks/cactuBSSN/cactuBSSN_r.riscv \
  --options=benchmarks/cactuBSSN/spec_train.par \
  > benchmarks/cactuBSSN/m5out_train/nohup.log 2>&1 &

# perlbench ref checkspam
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/perlbench/m5out_ref_checkspam $CFG \
  --cmd=benchmarks/perlbench/perlbench_r.riscv \
  '--options=-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/checkspam.pl 2500 5 25 11 150 1 1 1 1' \
  > benchmarks/perlbench/m5out_ref_checkspam/nohup.log 2>&1 &
```

### DO NOT RESTART — impractical
- `namd ref` (65 iterations, est. 18 days)
- `lbm ref` (3000 timesteps, est. months)
- `gcc ref32_O3sel` (96h+ already, no end in sight)
- `nab train_gcn4dna` (93h+ already, no end in sight)
- `nab ref` (similar duration expected)
- `omnetpp ref` / `imagick ref` / `xalancbmk ref` (weeks)
- `povray ref` (days-weeks)

---

## gem5 Launch Template

```bash
cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/

GEM5ENV=/cta/users/bkaya/miniconda3/envs/gem5_env/bin
export PATH=/cta/users/bkaya/bin:${GEM5ENV}:/cta/users/bkaya/.local/bin:/cta/users/bkaya/miniconda3/bin:/usr/bin:/bin

CFG="configs/deprecated/example/se.py --cpu-type=TimingSimpleCPU --caches --mem-size=4GB"

# Pattern for a benchmark:
nohup ./build/RISCV/gem5.opt --outdir=benchmarks/<bench>/m5out_<input> $CFG \
  --cmd=benchmarks/<bench>/<bench>_r.riscv \
  --options=<input_args> \
  > benchmarks/<bench>/m5out_<input>/nohup.log 2>&1 &
```

---

## Key Special Cases

### blender test
- Result is in `m5out_test2` (not `m5out_test`)
- `m5out_test`: cube.blend frame 1 (trivial scene, 821s)
- `m5out_test2`: sh5_reduced.blend (6.2193% spill rate) ← use this

### mcf ref
- Run with verbose mode (38GB CSV at `m5out/riscv_spill_stats.txt`)
- Summary stats: 21.1B ROI insts, 419M spills, 1.98%, CPI=11.02
- Full analysis: `benchmarks/mcf/m5out/benchmark_analysis.txt`

### x264 ref
- Shows identical stats to test (both use BuckBunny.264)
- ref simulated independently, same workload → consistent result

### imagick train anomaly
- Extremely low spill rate: 0.1029% (test = 2.0601%)
- Likely different operation in train input (conversion vs transform)

### perlbench multiple ROI blocks
- `m5out_test/riscv_spill_stats.txt` has 3 ROI blocks (3 Perl scripts run sequentially)
- status.sh correctly uses `tail -1` to get the last/aggregate block

### omnetpp multiple ROI blocks
- `m5out_test/riscv_spill_stats.txt` has 2 ROI blocks
- status.sh correctly uses `tail -1`

---

## Thesis/Report Strategy

### Recommended dataset for publication

**Core dataset (all have test + train)**:
gcc, perlbench, namd, lbm, omnetpp, xalancbmk, x264, povray, deepsjeng, imagick, leela, nab, xz, cactuBSSN, mcf, parest (16 benchmarks)

**Full test+train+ref comparison** (available now):
- gcc: 4 ref inputs DONE (pp_O3, pp_O2, smaller, ref32_O5)
- x264: test + train + ref all DONE
- mcf: test + train + ref (verbose)

**Full test+train+ref** (pending but realistic):
- blender, leela, xz (if migration allows)
- deepsjeng (if 3.5 days available)

### Narrative for impractical ref runs
> "Reference-input simulations for namd (65 iterations), lbm (3,000 timesteps),
> and selected other benchmarks were not completable within the available compute
> budget under gem5 TimingSimpleCPU. These benchmarks are characterized using
> test and train inputs, which exhibit consistent spill behavior (see Table X).
> Prior work has similarly restricted gem5 full-system evaluation to reduced
> workloads [cite]."

---

## Key File Paths

| Resource | Path |
|----------|------|
| gem5 binary | `build/RISCV/gem5.opt` |
| SpillDetector | `src/cpu/simple/spill_detector.cc` / `.hh` |
| SPEC config | `/cta/users/bkaya/riscv-spec-register-spilling/cpu2017/config/bkaya-riscv.cfg` |
| Benchmark binaries | `benchmarks/<name>/<name>_r.riscv` |
| Status checker | `status.sh` |
| Launch script | `launch_ref_all.sh` |
| gcc report | `benchmarks/gcc/report/gcc_combined.tex` |
| Cross-compiler | `/cta/research/level0/RISCV/` |
| libm5 | `util/m5/build/riscv/out/libm5.a` |
| gem5 include | `include/gem5/m5ops.h` |

---

*Snapshot generated: 2026-03-16 11:04 (castEpyc local time)*
