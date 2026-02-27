# Register Spill Detection — Test Guide

This document covers the complete workflow for building gem5, compiling test
programs, running simulations, and reading spill detection results.

---

## Project Layout

```
gem5/
├── src/cpu/simple/
│   ├── spill_detector.hh          # SpillDetector class definition
│   ├── spill_detector.cc          # SpillDetector implementation
│   ├── BaseTimingSimpleCPU.py     # SimObject params (incl. spill_verbose)
│   ├── timing.hh                  # TimingSimpleCPU + SpillDetector member
│   ├── timing.cc                  # Load/Store/Instruction hooks + param wiring
│   └── SConscript                 # Build configuration
├── tests/spill_test/
│   ├── README.md                  # This file
│   ├── spill_exact/               # Exact-count ASM tests
│   │   ├── spill_exact.S          # 4 spills, no ROI (baseline)
│   │   └── roi_zero_spill.S       # 0 ROI spills (false-positive check)
│   ├── roi_test_asm/              # ROI ASM tests
│   │   ├── roi_spill_exact.S      # 4 ROI spills (minimal ROI)
│   │   ├── roi_loop_spills.S      # 16 ROI spills (looped, 8 iter x 2)
│   │   └── roi_multi_roi.S        # Two ROI windows: 3 + 5 spills
│   ├── roi_test/                  # C ROI tests
│   │   ├── spill_test_roi.c       # Heavy register pressure inside ROI
│   │   └── spill_test_no_roi.c    # Same without ROI markers
│   ├── spill_c_test/              # C spill pressure test
│   │   └── spill_test.c
│   └── spill_vs_loop/             # Loop vs. spill contrast tests
│       ├── spill_vs_loop.S        # Loop stores WITHOUT reload → 0 loop spills
│       └── loop_reload_spills.S   # Loop stores WITH reload  → 10 loop spills
└── build/RISCV/
    └── gem5.opt                   # Simulator binary (x86-64 host, RISC-V target)
```

---

## How SpillDetector Works

1. **Store tracking** — every `sd`/`sw` writes the address into `std::unordered_map`
2. **Load check** — every `ld`/`lw` looks up that address in the map
3. **Spill detected** — if load finds a recent store at the same stack address → **SPILL**
4. **Filters** (all must pass):
   - Load tick > store tick (temporal order)
   - Load width == store width (same access size)
   - Address is inside the stack region (SE-mode `stackBase`/`stackMin` check)

ROI markers (`m5_work_begin` / `m5_work_end`) gate which spills are counted.
`enterROI()` clears the store map and resets ROI counters; `exitROI()` writes
the output summary.

| Hook in `timing.cc`  | SpillDetector method        | Triggered by          |
|----------------------|-----------------------------|-----------------------|
| `initiateMemRead()`  | `onLoadInstruction()`       | Every load            |
| `writeMem()`         | `onStoreInstruction()`      | Every store           |
| `advanceInst()`      | `onInstructionExecute()`    | Every instruction     |
| `pseudo_inst.cc`     | `enterROI()` / `exitROI()`  | `m5_work_begin/end`   |

---

## Step 0 — Environment

All commands below assume you are in the gem5 root:

```bash
cd /cta/users/bkaya/riscv-spec-register-spilling/gem5
```

Toolchain paths used throughout:

```bash
AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
GCC=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-gcc
GEM5ENV=/cta/users/bkaya/miniconda3/envs/gem5_env
```

---

## Step 1 — Build gem5 (RISC-V simulator)

> Skip this step if `build/RISCV/gem5.opt` is already up to date.
> Only needed after changing any `.cc` / `.hh` / `.py` source file.

```bash
GEM5ENV=/cta/users/bkaya/miniconda3/envs/gem5_env

PATH=$GEM5ENV/bin:$PATH \
scons build/RISCV/gem5.opt -j$(nproc) \
    CC=$GEM5ENV/bin/x86_64-conda-linux-gnu-gcc \
    CXX=$GEM5ENV/bin/x86_64-conda-linux-gnu-g++ \
    PYTHON_CONFIG=$GEM5ENV/bin/python3-config
```

**Why the PATH prefix?** `~/bin/gcc` is a conda wrapper that calls
`x86_64-conda-linux-gnu-gcc`. Prepending `gem5_env/bin` puts that compiler
in PATH so the wrapper resolves it. The explicit `CC=` / `CXX=` then override
SCons's default detection to use it directly.

Expected output ends with:
```
[    LINK]  -> RISCV/gem5.opt
scons: done building targets.
```

Build time: ~5 min incremental / ~40 min from scratch.

---

## Step 2 — Compile a test binary

### ASM tests (assemble + link directly)

```bash
AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
BASE=tests/spill_test

# Example: roi_loop_spills
$AS -o $BASE/roi_test_asm/roi_loop_spills.o  $BASE/roi_test_asm/roi_loop_spills.S
$LD -o $BASE/roi_test_asm/roi_loop_spills.riscv $BASE/roi_test_asm/roi_loop_spills.o
```

### C tests (compile with m5ops)

```bash
GCC=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-gcc
INCLUDE=util/m5/src   # path to m5op.h

$GCC -O0 -static \
    -I include \
    tests/spill_test/roi_test/spill_test_roi.c \
    -o tests/spill_test/roi_test/spill_test_roi.riscv
```

> `-O0` keeps spills predictable by disabling the compiler's register allocator
> optimisations. `-static` avoids dynamic linker issues inside gem5 SE mode.

---

## Step 3 — Run a simulation

### Summary mode (default — always safe)

No extra flags needed. The output file stays tiny (~300 bytes) regardless of
how many spills occur. Use this for all real benchmark runs.

```bash
./build/RISCV/gem5.opt \
    --outdir=<output_directory> \
    configs/deprecated/example/se.py \
    --cmd=<path/to/binary.riscv> \
    --cpu-type=TimingSimpleCPU \
    --caches
```

### Verbose mode (small tests only)

Adds one `SPILL,...` CSV line per detected event to the output file, followed
by the summary. **Warning: can produce tens of GB for long workloads.**

```bash
./build/RISCV/gem5.opt \
    --outdir=<output_directory> \
    configs/deprecated/example/se.py \
    --cmd=<path/to/binary.riscv> \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --param "system.cpu[0].spill_verbose=True"
```

---

## Step 4 — Read the results

```bash
cat <output_directory>/riscv_spill_stats.txt
```

### Summary mode output

```
# ================================================
# ROI SUMMARY  ISA=RISC-V  workid=0
# (summary mode - set spill_verbose=True for per-spill lines)
# ------------------------------------------------
# entry_total_insts  : 6          <- global insts when ROI started
# entry_total_spills : 1          <- global spills when ROI started
# roi_instructions   : 78         <- instructions executed inside ROI
# roi_stores         : 16         <- stores inside ROI
# roi_loads          : 16         <- loads inside ROI
# roi_spills         : 16         <- spills detected inside ROI
# spill_rate         : 20.5128%   <- roi_spills / roi_instructions * 100
# ================================================
```

Multiple ROI windows produce multiple blocks — one per `m5_work_begin/end` pair.

### Verbose mode output

```
# Register Spill Detection Log - RISC-V (VERBOSE MODE)
# Format: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,...
# =================================

# ROI_BEGIN  workid=0  entry_total_insts=6  entry_total_spills=1
SPILL,100dc,100e0,7ffffffffffffea0,202000,204000,2000,11,12
SPILL,100e8,100ec,7ffffffffffffea8,207000,209000,2000,14,15
...
# ROI SUMMARY  ISA=RISC-V  workid=0
# roi_spills : 16
# ================================================
```

| SPILL field        | Description                              |
|--------------------|------------------------------------------|
| `store_pc`         | PC of the store instruction (hex)        |
| `load_pc`          | PC of the load instruction (hex)         |
| `memory_address`   | Stack address of the spill (hex)         |
| `store_tick`       | Simulation tick of the store             |
| `load_tick`        | Simulation tick of the load              |
| `tick_diff`        | `load_tick - store_tick`                 |
| `store_inst_count` | Global instruction counter at store      |
| `load_inst_count`  | Global instruction counter at load       |

---

## Test Suite

All binaries are pre-built. Re-compile only if the `.S` source changes.

### Run all tests (summary mode)

```bash
GEM5=./build/RISCV/gem5.opt
CFG=configs/deprecated/example/se.py
BASE=tests/spill_test

$GEM5 --outdir=$BASE/spill_exact/out    $CFG --cmd=$BASE/spill_exact/spill_exact.riscv             --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/roi_test_asm/out1  $CFG --cmd=$BASE/roi_test_asm/roi_spill_exact.riscv         --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/roi_test_asm/out2  $CFG --cmd=$BASE/roi_test_asm/roi_loop_spills.riscv         --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/roi_test_asm/out3  $CFG --cmd=$BASE/roi_test_asm/roi_multi_roi.riscv           --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/spill_exact/out2   $CFG --cmd=$BASE/spill_exact/roi_zero_spill.riscv           --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/spill_vs_loop/out1 $CFG --cmd=$BASE/spill_vs_loop/spill_vs_loop.riscv          --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/spill_vs_loop/out2 $CFG --cmd=$BASE/spill_vs_loop/loop_reload_spills.riscv     --cpu-type=TimingSimpleCPU --caches 2>/dev/null
```

### Expected results

| Test binary              | roi_spills | Notes                                   |
|--------------------------|------------|-----------------------------------------|
| `spill_exact`            | —          | No ROI → no stats file created          |
| `roi_spill_exact`        | 4          | Minimal ROI, 4 direct spills            |
| `roi_loop_spills`        | 16         | 8 iterations × 2 spills/iter            |
| `roi_multi_roi`          | 3 + 5      | Two independent ROI windows             |
| `roi_zero_spill`         | 0          | No false positives (orphan loads/stores)|
| `spill_vs_loop`          | 4          | 5 loop stores (no reload) = 0 loop spills|
| `loop_reload_spills`     | 10         | 10 iterations × 1 spill/iter (reload)  |

### Re-compile all ASM tests from source

```bash
AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
BASE=tests/spill_test

for src in \
  $BASE/spill_exact/spill_exact.S \
  $BASE/spill_exact/roi_zero_spill.S \
  $BASE/roi_test_asm/roi_spill_exact.S \
  $BASE/roi_test_asm/roi_loop_spills.S \
  $BASE/roi_test_asm/roi_multi_roi.S \
  $BASE/spill_vs_loop/spill_vs_loop.S \
  $BASE/spill_vs_loop/loop_reload_spills.S
do
  obj="${src%.S}.o"
  bin="${src%.S}.riscv"
  $AS -o "$obj" "$src"
  $LD -o "$bin" "$obj"
  echo "Built: $bin"
done
```

---

## m5ops Encoding (RISC-V)

The ROI boundary instructions are encoded as raw 32-bit words:

| Operation       | Raw encoding   | gem5 C API        |
|-----------------|----------------|-------------------|
| `m5_work_begin` | `.long 0xb400007b` | `m5_work_begin(workid, threadid)` |
| `m5_work_end`   | `.long 0xb600007b` | `m5_work_end(workid, threadid)`   |

In ASM:
```asm
li    a0, 0          # workid
li    a1, 0          # threadid
.long 0xb400007b     # m5_work_begin → triggers enterROI()

# ... code to measure ...

li    a0, 0
li    a1, 0
.long 0xb600007b     # m5_work_end → triggers exitROI(), writes summary
```

In C (with `#include <gem5/m5ops.h>`):
```c
m5_work_begin(0, 0);
// ... code to measure ...
m5_work_end(0, 0);
```

---

## Key Implementation Files

| File | Role |
|------|------|
| `src/cpu/simple/spill_detector.hh` | Class definition, `StoreInfo`, `SpillEvent` structs |
| `src/cpu/simple/spill_detector.cc` | Detection logic, file output, ROI entry/exit |
| `src/cpu/simple/BaseTimingSimpleCPU.py` | `spill_verbose` SimObject parameter |
| `src/cpu/simple/timing.hh` | `SpillDetector spillDetector` member |
| `src/cpu/simple/timing.cc` | Hook calls + `spillDetector.setVerbose(p.spill_verbose)` |
| `src/sim/pseudo_inst.cc` | Calls `enterROI()` / `exitROI()` on m5ops |
