# Register Spill Detection — Test Suite

This directory contains three RISC-V assembly test cases that deliberately
trigger register spills and verify the gem5 SpillDetector counts them correctly.
Each test has a deterministic, hand-verified expected `roi_spills` value.

---

## Directory Layout

```
tests/spill_test/
├── README.md                          # This file
├── tc1_callee_save/
│   ├── tc1_callee_save.S              # Source
│   ├── tc1_callee_save.riscv          # Pre-built binary
│   └── out/riscv_spill_stats.txt      # Last run result
├── tc2_reg_pressure/
│   ├── tc2_reg_pressure.S
│   ├── tc2_reg_pressure.riscv
│   └── out/riscv_spill_stats.txt
└── tc3_loop_spill/
    ├── tc3_loop_spill.S
    ├── tc3_loop_spill.riscv
    └── out/riscv_spill_stats.txt
```

---

## Test Cases

### TC1 — Callee-Save Register Spill (`tc1_callee_save`)

**Scenario**: Simulates a real function prologue/epilogue.
Every non-leaf function in the RISC-V ABI must preserve the caller's s-registers
(s0–s5). It saves them to the stack at entry, uses them for computation,
then restores them before returning. Each save+restore pair is one spill.

**Key property**: Store and load are *not* adjacent — real arithmetic separates
them. This tests that `store_map` retains entries across a multi-instruction
basic block, which is the behaviour that matters for real benchmark workloads.

```
ROI:
  sd s0-s5 to stack    ← 6 stores (prologue)
  li / add / mul …     ← body: no stack access
  ld s0-s5 from stack  ← 6 loads (epilogue) → 6 SPILLS
```

**Expected**: `roi_spills = 6`, `roi_stores = 6`, `roi_loads = 6`

---

### TC2 — Register Pressure Spill (`tc2_reg_pressure`)

**Scenario**: Simulates the register allocator spilling the entire live set.
When there are more live values than physical registers, the compiler emits
a "spill-out" phase (all stores) followed by a "spill-in" phase (all reloads).

**Key property**: All 8 stores complete *before* any load — the `store_map`
holds 8 live entries simultaneously. This is the hallmark of genuine register
pressure and cannot happen in a simple store-immediately-followed-by-load test.

```
ROI:
  Phase 1 (spill-out):
    li t0,11  sd t0, 0(sp)
    li t1,22  sd t1, 8(sp)
    …         …                ← 8 stores, store_map grows to 8 entries
    li a2,88  sd a2,56(sp)

  Phase 2 (spill-in):
    ld t0, 0(sp)   add t0,t0,t1   ← SPILL #1
    ld t1, 8(sp)   add t0,t0,t2   ← SPILL #2
    …                             ← … 8 total
    ld a2,56(sp)   add t0,t0,a2   ← SPILL #8
```

**Expected**: `roi_spills = 8`, `roi_stores = 8`, `roi_loads = 8`

---

### TC3 — Loop Body Spill (`tc3_loop_spill`)

**Scenario**: Simulates a loop whose body requires more live registers than
are available, so the compiler spills 3 values per iteration.
5 iterations × 3 spills/iteration = 15 ROI spills.

**Key property**: Each iteration's load erases the `store_map` entry for that
slot, so the next iteration's store re-enters cleanly → every iteration produces
exactly 3 fresh spills. Slot addresses are reused across iterations, which
correctly models how loop bodies share the same stack slots each time around.

```
ROI:
  loop (i = 0 … 4):
    addi t0, s0, 10   sd t0, 16(sp)   ld t1, 16(sp)   ← SPILL A
    slli t2, s0,  2   sd t2, 24(sp)   ld t3, 24(sp)   ← SPILL B
    add  s2, s2, …    sd s2, 32(sp)   ld t5, 32(sp)   ← SPILL C
    i++
```

**Expected**: `roi_spills = 15`, `roi_stores = 15`, `roi_loads = 15`

---

## Quick Reference

| Test                | Expected `roi_spills` | Pattern                          |
|---------------------|-----------------------|----------------------------------|
| `tc1_callee_save`   | 6                     | s0-s5 save/restore (non-adjacent)|
| `tc2_reg_pressure`  | 8                     | all-store-then-all-reload         |
| `tc3_loop_spill`    | 15                    | 5 iters × 3 spills/iter           |

---

## How to Re-Build Binaries

```bash
AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
BASE=tests/spill_test

for tc in tc1_callee_save tc2_reg_pressure tc3_loop_spill; do
  $AS -o $BASE/$tc/$tc.o  $BASE/$tc/$tc.S
  $LD -o $BASE/$tc/$tc.riscv $BASE/$tc/$tc.o
  echo "Built: $tc.riscv"
done
```

---

## How to Run All Tests

Run from the gem5 root (`/cta/users/bkaya/riscv-spec-register-spilling/gem5`):

```bash
GEM5=./build/RISCV/gem5.opt
CFG=configs/deprecated/example/se.py
BASE=tests/spill_test

$GEM5 --outdir=$BASE/tc1_callee_save/out  $CFG --cmd=$BASE/tc1_callee_save/tc1_callee_save.riscv  --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/tc2_reg_pressure/out $CFG --cmd=$BASE/tc2_reg_pressure/tc2_reg_pressure.riscv --cpu-type=TimingSimpleCPU --caches 2>/dev/null
$GEM5 --outdir=$BASE/tc3_loop_spill/out   $CFG --cmd=$BASE/tc3_loop_spill/tc3_loop_spill.riscv     --cpu-type=TimingSimpleCPU --caches 2>/dev/null
```

Inspect results:

```bash
for tc in tc1_callee_save tc2_reg_pressure tc3_loop_spill; do
  echo "=== $tc ==="
  cat tests/spill_test/$tc/out/riscv_spill_stats.txt
done
```

### Verbose mode (per-spill lines)

Add `--param "system.cpu[0].spill_verbose=True"` to log each individual spill:

```bash
$GEM5 --outdir=$BASE/tc1_callee_save/out_v $CFG \
  --cmd=$BASE/tc1_callee_save/tc1_callee_save.riscv \
  --cpu-type=TimingSimpleCPU --caches \
  --param "system.cpu[0].spill_verbose=True" 2>/dev/null
```

---

## How SpillDetector Works

1. **Store tracking** — every `sd`/`sw` writes the address into `store_map`
2. **Load check** — every `ld`/`lw` looks up that address in `store_map`
3. **Spill detected** — if the load finds a recent store at the same stack address

Filters that must all pass:
- Load tick > store tick (temporal order)
- Load width == store width (same access size)
- Address is inside the stack region (`stackBase` / `stackMin`)

ROI markers gate which spills are counted:
- `m5_work_begin` (`.long 0xb400007b`) → `enterROI()`: clears `store_map`, resets ROI counters
- `m5_work_end`   (`.long 0xb600007b`) → `exitROI()`: writes summary to `riscv_spill_stats.txt`

---

## Building gem5

Only needed after changing source files under `src/cpu/simple/`.

```bash
GEM5ENV=/cta/users/bkaya/miniconda3/envs/gem5_env

PATH=$GEM5ENV/bin:$PATH \
scons build/RISCV/gem5.opt -j$(nproc) \
    CC=$GEM5ENV/bin/x86_64-conda-linux-gnu-gcc \
    CXX=$GEM5ENV/bin/x86_64-conda-linux-gnu-g++ \
    PYTHON_CONFIG=$GEM5ENV/bin/python3-config
```
