# 508.namd_r — gem5 Spill Detection

NAMD is a molecular dynamics simulation benchmark. It simulates the ApoA1
lipid-protein system. The ROI wraps the main iteration loop in `spec_namd.C`.

---

## Input Sizes

| Dataset  | Iterations | File          | Notes                          |
|----------|-----------|---------------|--------------------------------|
| test     | 1         | apoa1.input   | Quick verification run         |
| train    | 8         | apoa1.input   | Medium run                     |
| refrate  | 65        | apoa1.input   | Full benchmark measurement     |

Same `apoa1.input` file for all — only `--iterations` changes.

---

## Last Run Results (test — 1 iteration)

```
roi_instructions : 31,914,751,100
roi_stores       : 1,945,521,360
roi_loads        : 8,380,476,926
roi_spills       : 327,718,955
spill_rate       : 1.0269%
simSeconds       : 68.73
hostSeconds      : 25169  (~7 hours)
```

---

## Step-by-Step: Run Without Manual Intervention

### Step 1 — Go to gem5 root

```bash
cd /cta/users/bkaya/riscv-spec-register-spilling/gem5
```

### Step 2 — Launch simulation in background

```bash
nohup ./build/RISCV/gem5.opt \
    --outdir=benchmarks/namd/m5out_test \
    configs/deprecated/example/se.py \
    --cmd=benchmarks/namd/namd_r.riscv \
    --options="--input benchmarks/namd/apoa1.input --iterations 1 --output benchmarks/namd/apoa1.test.output" \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --mem-size=4GB \
    > benchmarks/namd/namd_test_run.log 2>&1 &
echo "PID: $!"
```

For refrate (65 iterations), replace `--iterations 1` with `--iterations 65`
and `--outdir` with `benchmarks/namd/m5out_refrate`.

### Step 3 — Check if still running

```bash
ps aux | grep gem5 | grep -v grep
```

No output → finished (or never started).

### Step 4 — Watch live log

```bash
tail -f benchmarks/namd/namd_test_run.log
```

Press `Ctrl+C` to stop watching (does not kill the simulation).
Done when log ends with: `Exiting @ tick ... because exiting with last active thread context`

### Step 5 — Check if ROI was reached

```bash
ls benchmarks/namd/m5out_test/riscv_spill_stats.txt
```

File exists → ROI was triggered and results written.
File missing → simulation ended before reaching `m5_work_begin`.

### Step 6 — Read results

```bash
cat benchmarks/namd/m5out_test/riscv_spill_stats.txt
```

Expected output format:
```
# ROI SUMMARY  ISA=RISC-V  workid=0
# roi_instructions   : ...
# roi_stores         : ...
# roi_loads          : ...
# roi_spills         : ...
# spill_rate         : ...%
```

### Step 7 — Read timing stats

```bash
grep -E "simSeconds|hostSeconds" benchmarks/namd/m5out_test/stats.txt
```

---

## One-Liner Status Check

```bash
ps aux | grep gem5 | grep -v grep \
  && cat benchmarks/namd/m5out_test/riscv_spill_stats.txt 2>/dev/null \
  || echo "Not finished yet"
```

---

## ROI Location in Source

File: `cpu2017/benchspec/CPU/508.namd_r/src/spec_namd.C`

The ROI markers wrap the main iterations for-loop:
```cpp
m5_work_begin(0, 0);
for (int i = 0; i < iterations; i++) { ... }
m5_work_end(0, 0);
```
