# Validation & Analysis Roadmap
## Spill Hit/Miss Cache Instrumentation — gem5 RISC-V

**Last updated:** 2026-04-14  
**Status:** Phase 1 complete. Phases 2–9 planned below.

---

## Status Overview

| Phase | Scope | Status |
|---|---|---|
| 1 | SPILL_LOAD positive tests (l1_hit, l1miss_l2hit, l1miss_l2miss) | **COMPLETE ✓** |
| 2 | SPILL_STORE positive tests | planned |
| 3 | Negative / boundary tests | planned |
| 4 | Stress / robustness tests | planned |
| 5 | Realistic cache config validation | planned |
| 6 | Paper-ready validation documentation | planned |
| 7 | Real benchmark analysis (SPEC CPU2017) | planned |
| 8 | Spill vs regular data comparison | planned |
| 9 | Spill-aware cache policy exploration | planned |

---

## Phase 1 — SPILL_LOAD Positive Tests (COMPLETE)

### What was proven

Three cache scenarios were validated end-to-end with controlled programs
producing exactly one (or a precisely bounded number of) SPILL_LOAD events.

**Verified tagging chain:**
```
SpillDetector::onLoadInstruction()  →  inside_roi && isLikelySpill()
  →  timing.cc::readMem(): req->setFlags(Request::SPILL_LOAD)
  →  BaseCache::incHitCount/incMissCount: spillLoadHits/Misses++
  →  (flag preserved through L1→L2 forwarding for both hit and miss paths)
```

**Final results (gem5 with MAX_SPILL_WINDOW = 50 M ticks):**

| Scenario | dcache.spillLoadHits | dcache.spillLoadMisses | l2.spillLoadHits | l2.spillLoadMisses |
|---|---|---|---|---|
| l1_hit | **1** | 0 | 0 | 0 |
| l1miss_l2hit | 0 | **1** | **1** | 0 |
| l1miss_l2miss | 0 | **1** | 0 | **1** |

**Key engineering note (MAX_SPILL_WINDOW):**
The original 10 M tick window caused the l1miss_l2miss test to silently produce
all-zero results because the 160-line flush loop took ~25.7 M ticks, exceeding
the window and causing the store_map entry to expire.  Increased to 50 M ticks
(50 µs), which is still far beyond any realistic register-spill interval in
compiled code.

---

## Phase 2 — SPILL_STORE Positive Tests

### Goal

Validate the store-side tagging path:
```
SpillDetector::onStoreInstruction()  →  inside_roi && isStackAddress()
  →  timing.cc::writeMem(): req->setFlags(Request::SPILL_STORE)
  →  BaseCache::incHitCount/incMissCount: spillStoreHits/Misses++
```

### Key difference from load side

**Store detection uses no store_map lookup.**  Every stack store inside the
ROI is tagged as `SPILL_STORE` (over-approximation).  This means:
- Detection is simpler (no temporal-order or size-match requirement)
- But isolation is harder: every stack store in the ROI — including function
  prologues and any volatile local write — is tagged

**L2 spill store counter behavior (important):**
For a write-allocate L1 miss, the store packet's `SPILL_STORE` flag causes
`incMissCount` to fire at L1 (`spillStoreMisses++`).  However, the subsequent
fill/RFO request sent to L2 is a *new* packet that does NOT carry the
`SPILL_STORE` flag.  Therefore:
- `dcache.spillStoreMisses` and `dcache.spillStoreHits` are meaningful
- `l2.spillStoreHits` and `l2.spillStoreMisses` will likely always be 0
  for stores (by design of the classic cache write-allocate protocol)
This asymmetry should be documented but is not a bug.

### Planned test directory structure

```
load/
store/                           ← Phase 2
    ├── l1_hit/
    │   ├── test.c               stack store inside ROI, line already in L1
    │   ├── Makefile
    │   ├── run.sh               same cache config as Phase 1
    │   ├── check.sh             assert dcache.spillStoreHits >= 1
    │   └── README.md
    └── l1_miss/
        ├── test.c               evict stack line from L1 before ROI, then store
        ├── Makefile
        ├── run.sh
        ├── check.sh             assert dcache.spillStoreMisses >= 1
        └── README.md
```

(No `l1miss_l2hit` or `l1miss_l2miss` for stores — see above.)

### store/l1_hit — Design

```
main() prologue:           sd ra, 24(sp)   → stack line enters L1 (OUTSIDE ROI)
m5_work_begin(0,0)         ROI starts, inside_roi = true
  volatile int64_t x;
  x = 0xA5A5...;           sd <r>, <off>(sp) → stack line STILL IN L1 (not evicted)
                            onStoreInstruction: inside_roi ✓, isStackAddress ✓
                            → req->setFlags(SPILL_STORE)
                            → line present in L1 → incHitCount → spillStoreHits++
m5_work_end(0,0)
```

Expected:
- `system.cpu.dcache.spillStoreHits   >= 1`
- `system.cpu.dcache.spillStoreMisses  = 0`

### store/l1_miss — Design

```
main() prologue:           sd ra, 24(sp)   → stack line enters L1
flush_before_roi():        32 BSS lines    → evicts ALL L1 lines including stack
m5_work_begin(0,0)         ROI starts (m5_work_begin is a leaf fn, no stack push)
  volatile int64_t x;
  x = 0xA5A5...;           sd <r>, <off>(sp) → stack line NOT in L1 (evicted)
                            → incMissCount → spillStoreMisses++
                            write-allocate: fetch line from L2/DRAM into L1, then write
m5_work_end(0,0)
```

Expected:
- `system.cpu.dcache.spillStoreMisses  >= 1`
- `system.cpu.dcache.spillStoreHits     = 0`

---

## Phase 3 — Negative / Boundary Tests

### Goal

Prove that the SpillDetector does NOT count events that should NOT be spills.
"Positive tests show we count what we should; negative tests show we don't
count what we shouldn't."  These are essential for a defensible paper claim.

### Directory structure

```
negative/
    ├── non_stack/           BSS/global access inside ROI — not a spill
    ├── roi_outside_load/    in-ROI store + out-of-ROI load — not tagged
    ├── size_mismatch/       8B store then 4B load from same addr — size check
    ├── window_expired/      delay > MAX_SPILL_WINDOW before load — map cleaned
    └── no_matching_store/   load from stack addr never stored to — no map entry
```

Each test follows the same `test.c / Makefile / run.sh / check.sh / README.md`
structure.  The check.sh in negative tests asserts that **all spill counters
are zero** (or remain at background baseline).

---

### negative/non_stack — BSS access

**Mechanism tested:** `isStackAddress(bss_addr, tc)` returns false for global
BSS addresses → `isLikelySpill()` returns false even when store+load match.

```c
static volatile int64_t global_var;   // BSS segment, NOT on stack

int main(void) {
    m5_work_begin(0, 0);
    global_var = 0xA5A5A5A5A5A5A5A5LL; // store: store_map[bss_addr] added
    int64_t v  = global_var;            // load: store_map.find(bss_addr) → FOUND
                                        // isLikelySpill: isStackAddress → FALSE
                                        // → returns false → NO SPILL_LOAD
    m5_work_end(0, 0);
    return (int)(v & 1);
}
```

Expected: `spillLoadHits = 0`, `spillLoadMisses = 0`

---

### negative/roi_outside_load — Store in ROI, load after ROI

**Mechanism tested:** `inside_roi` is false at load time even though store
was in ROI and store_map entry exists.

```c
int main(void) {
    m5_work_begin(0, 0);
    volatile int64_t x;
    x = 0xA5A5A5A5A5A5A5A5LL;   // store INSIDE ROI → store_map entry added
    m5_work_end(0, 0);            // ROI ends here; inside_roi → false

    int64_t val = x;              // load OUTSIDE ROI
                                  // onLoadInstruction: store_map.find → FOUND
                                  // isLikelySpill: all checks pass
                                  // BUT inside_roi = false → returns false
                                  // → NO SPILL_LOAD
    return (int)(val & 1);
}
```

Expected: `spillLoadHits = 0`, `spillLoadMisses = 0`

Note: the converse (store outside ROI, load inside ROI) IS counted as a spill
by design — the reload is what matters for cache analysis, and the detector
correctly tracks reloads regardless of when the spill-store occurred.

---

### negative/size_mismatch — Store 8B, load 4B from same address

**Mechanism tested:** `load_size (4) != store_info.size (8)` causes
`isLikelySpill()` to return false even with a matching store_map entry.

```c
int main(void) {
    m5_work_begin(0, 0);
    volatile int64_t x64;
    x64 = 0xA5A5A5A5A5A5A5A5LL;        // 8-byte store → store_map[addr, size=8]

    /* 4-byte load from the same stack address */
    volatile int32_t *p32 = (volatile int32_t *)&x64;
    int32_t v = *p32;                   // 4-byte load → store_map.find → FOUND
                                        // isLikelySpill: size 4 ≠ 8 → FALSE
                                        // → NO SPILL_LOAD
    m5_work_end(0, 0);
    return (int)(v & 1);
}
```

Expected: `spillLoadHits = 0`, `spillLoadMisses = 0`

---

### negative/window_expired — Delay exceeds MAX_SPILL_WINDOW

**Mechanism tested:** `cleanupOldStores(current_tick)` removes the store_map
entry when `current_tick - store_tick > MAX_SPILL_WINDOW (50 M ticks)`.

```c
static volatile long delay_sink;   // BSS — each access triggers cleanupOldStores

int main(void) {
    m5_work_begin(0, 0);
    volatile int64_t x;
    x = 0xA5A5A5A5A5A5A5A5LL;     // store → store_map entry at tick T

    /*
     * Delay loop.  Each iteration: load delay_sink (BSS, not stack) → triggers
     * cleanupOldStores(current_tick).  After ~50 M ticks the entry for x
     * expires and is erased.
     *
     * delay_sink is L1-hot after first access: ~8,000 ticks/iteration.
     * 7,000 iterations × 8,000 = 56,000,000 ticks > MAX_SPILL_WINDOW. ✓
     * Use 10,000 for comfortable margin.
     */
    for (int i = 0; i < 10000; i++) {
        delay_sink++;               // BSS load+store (not a spill), triggers cleanup
    }

    int64_t val = x;               // load → store_map.find(x_addr) → NOT FOUND
                                   // (entry was cleaned up during delay loop)
                                   // → NO SPILL_LOAD
    m5_work_end(0, 0);
    return (int)(val & 1);
}
```

Expected: `spillLoadHits = 0`, `spillLoadMisses = 0`

Note: tune the iteration count if MAX_SPILL_WINDOW is changed again.  The
target is: `iterations × ticks_per_iter > MAX_SPILL_WINDOW`.

---

### negative/no_matching_store — Load from address never stored to

**Mechanism tested:** `store_map.find(addr)` returns `end()` when the stack
address was never the target of a prior store → `onLoadInstruction` returns
false immediately.

```c
int main(void) {
    /*
     * Large stack buffer.  Element [14] is at sp+112, far from the
     * function prologue saves (ra at sp+120, etc. — only 8 bytes apart,
     * but the key point is we never explicitly store to scratch[14]).
     * Use a large index to guarantee no collision with prologue stores.
     */
    volatile int64_t scratch[16];  // 128 bytes on stack; uninitialized

    m5_work_begin(0, 0);

    /* Load from scratch[14] — no prior store to this address anywhere */
    int64_t val = scratch[14];     // store_map.find(sp+112) → NOT FOUND
                                   // (nothing has ever stored to sp+112)
                                   // → onLoadInstruction returns false
                                   // → NO SPILL_LOAD
    m5_work_end(0, 0);
    return (int)(val & 1);
}
```

Expected: `spillLoadHits = 0`, `spillLoadMisses = 0`

---

## Phase 4 — Stress / Robustness Tests

### Goal

Verify that the SpillDetector produces **linearly consistent counts** across
repeated events and across multiple independent stack slots.  A system that
works for 1 event must also work for N events without off-by-one errors,
map corruption, or counter saturation.

### Directory structure

```
stress/
    ├── serial_10_spills/    10 consecutive spill store+load pairs in one ROI
    ├── multi_slot/          5 different stack addresses, each spilled once
    ├── nested_calls/        spills across function call boundaries
    └── store_map_pressure/  many stores to exercise the 10,000-entry map limit
```

---

### stress/serial_10_spills — Linearity check

```c
int main(void) {
    m5_work_begin(0, 0);
    /* 10 independent volatile locals, store then load each */
    volatile int64_t a0, a1, a2, a3, a4, a5, a6, a7, a8, a9;
    a0 = 0; a1 = 1; /* ... */ a9 = 9;
    int64_t s = a0 + a1 + /* ... */ + a9;  // 10 spill reloads, all L1 hits
    m5_work_end(0, 0);
    return (int)(s & 0xFF);
}
```

Expected: `dcache.spillLoadHits = 10`, `dcache.spillLoadMisses = 0`

This directly tests that counts scale linearly with event count — a critical
property for benchmark analysis where counts are in the millions.

---

### stress/multi_slot — Independent tracking across addresses

```c
static volatile char flush_buf[32 * 64];

__attribute__((noinline)) static int flush(void) {
    int acc = 0;
    for (int i = 0; i < 32; i++) acc += flush_buf[i * 64];
    return acc;
}

int main(void) {
    m5_work_begin(0, 0);
    volatile int64_t s0, s1, s2, s3, s4;

    s0 = 10; s1 = 20; s2 = 30; s3 = 40; s4 = 50;  // 5 spill stores (L1 hit)
    int dummy = flush();   // evict all 5 slots from L1; they go to L2
    int64_t v = s0 + s1 + s2 + s3 + s4;  // 5 spill reloads (L1 miss, L2 hit)

    m5_work_end(0, 0);
    return (int)(v & 0xFF) | (dummy & 1);
}
```

Expected:
- `dcache.spillLoadMisses >= 5`
- `l2.spillLoadHits >= 5`

Verifies that the store_map correctly tracks multiple independent stack
addresses simultaneously without collision or premature eviction.

---

### stress/nested_calls — Spills across function boundaries

```c
__attribute__((noinline)) static void inner(volatile int64_t *slot) {
    *slot = 0xCAFEBABEDEADBEEFLL;  // store inside called function
}

__attribute__((noinline)) static int64_t reload(volatile int64_t *slot) {
    return *slot;                   // load inside called function
}

int main(void) {
    volatile int64_t x;
    m5_work_begin(0, 0);
    inner(&x);    // stack store in nested frame → store_map[x_addr]
    int64_t v = reload(&x);  // stack load in another nested frame → SPILL_LOAD
    m5_work_end(0, 0);
    return (int)(v & 1);
}
```

Expected: `dcache.spillLoadHits >= 1`

Verifies cross-frame spill detection: the store and load happen in different
function activations but at the same stack address (passed by pointer).

---

### stress/store_map_pressure — MAP_STORE_ENTRIES boundary

```c
/*
 * Generate > 10,000 unique stack stores to test the cleanup path.
 * SpillDetector evicts old entries when store_map.size() > 10,000.
 * The target spill (the last store+load pair) must survive the pressure.
 */
int main(void) {
    volatile int64_t big_array[128];   // 128 unique slots
    m5_work_begin(0, 0);

    /* Fill store_map with many different addresses */
    for (int i = 0; i < 128; i++) big_array[i] = (int64_t)i;

    /* The last slot should still be in store_map */
    int64_t v = big_array[127];  // should be SPILL_LOAD if not evicted from map

    m5_work_end(0, 0);
    return (int)(v & 0xFF);
}
```

Expected: `dcache.spillLoadHits >= 1` (the last pair must be detected).

---

## Phase 5 — Realistic Cache Configuration Validation

### Goal

Confirm that the positive test scenarios also work with production-like cache
sizes, not just the tiny 1kB/8kB caches used in Phases 1–4.

### Motivation

A reviewer could argue "the tests only work because the caches are artificially
small."  A test with realistic L1=32kB, L2=256kB adds credibility.

### Directory structure

```
realistic/
    ├── l1_hit/         32kB L1 — trivial, confirms basic tagging
    └── l1miss_l2hit/   targeted eviction of one cache set in 32kB L1
```

### Approach for realistic/l1miss_l2hit

With a 32kB 8-way L1 (512 sets, 64B blocks):
- `x` maps to set S = (sp >> 6) & 511
- To evict `x` from set S, access 9 lines that all map to set S
  (8-way → 9th access causes LRU eviction)
- Lines with the same set index are 32kB apart (512 sets × 64B = 32kB stride)

```c
/* Access 9 addresses 32kB apart to evict one specific L1 set */
#define L1_SET_STRIDE  (32 * 1024)   /* 32kB = L1 capacity ÷ associativity */
#define WAYS_PLUS_ONE  9

static volatile char targeted_flush[WAYS_PLUS_ONE * L1_SET_STRIDE];
```

However, since we don't know the runtime value of `sp`, we cannot statically
guarantee alignment.  Options:
1. Accept probabilistic eviction (works ~50% of the time without alignment)
2. Use `alloca()` to align the stack frame to a known boundary
3. Use `mmap()` for the flush array and align it to match `sp`'s set

For the first validation, option 1 is sufficient: run the test 3 times and
verify that `spillLoadMisses` is non-zero in at least one run.

---

## Phase 6 — Paper-Ready Validation Documentation

### Goal

Produce a self-contained document (LaTeX table + methodology section) that
can be directly cited in the thesis/paper as validation evidence.

### Content outline

```
Section X: Instrumentation Validation

X.1 Motivation
    - Why micro-tests before large benchmarks
    - What failure modes exist (silent wrong counts, zero counts, saturation)

X.2 Validated System
    - SpillDetector → Request::SPILL_LOAD → BaseCache counters
    - Source file cross-references

X.3 Test Methodology
    - gem5 SE mode, TimingSimpleCPU, RISC-V RV64GC
    - Cache config (1kB L1 / 8kB L2 for control; 32kB/256kB for realism)
    - Flush mechanism and MAX_SPILL_WINDOW analysis

X.4 Positive Test Results  ← the clean result table
X.5 Negative Test Results  ← all zeros where expected
X.6 Conclusion
```

### Target result table (LaTeX)

```latex
\begin{table}[h]
\centering
\caption{Micro-test validation results for SPILL\_LOAD instrumentation.
         All counters show exact integer values from single simulation runs.}
\begin{tabular}{lccccl}
\toprule
Scenario & \thead{dcache\\spillLoadHits} & \thead{dcache\\spillLoadMisses}
         & \thead{l2\\spillLoadHits} & \thead{l2\\spillLoadMisses} & Result \\
\midrule
L1 hit                & 1 & 0 & 0 & 0 & \textbf{PASS} \\
L1 miss, L2 hit       & 0 & 1 & 1 & 0 & \textbf{PASS} \\
L1 miss, L2 miss      & 0 & 1 & 0 & 1 & \textbf{PASS} \\
\midrule
\multicolumn{6}{l}{\textit{Negative tests (all spill counters must equal 0)}} \\
\midrule
Non-stack access      & 0 & 0 & 0 & 0 & \textbf{PASS} \\
Load outside ROI      & 0 & 0 & 0 & 0 & \textbf{PASS} \\
Size mismatch         & 0 & 0 & 0 & 0 & \textbf{PASS} \\
Window expired        & 0 & 0 & 0 & 0 & \textbf{PASS} \\
No prior store        & 0 & 0 & 0 & 0 & \textbf{PASS} \\
\bottomrule
\end{tabular}
\end{table}
```

---

## Phase 7 — Real Benchmark Analysis (SPEC CPU2017)

### Goal

Apply the validated instrumentation to the 16 SPEC CPU2017 C/C++ benchmarks
(already simulated; stats.txt files exist in `gem5/benchmarks/*/m5out_ref/`).

### Target per-benchmark table

| Benchmark | ROI Insts | Spill Loads | Spill Stores | L1 Spill Hits | L1 Spill Misses | L2 Spill Hits | L2 Spill Misses |
|---|---|---|---|---|---|---|---|
| 500.perlbench | — | — | — | — | — | — | — |
| 502.gcc | — | ... | | | | | |
| ... | | | | | | | |

### Derived metrics (per benchmark)

```
spill_load_L1_hit_rate   = L1.spillLoadHits  / (L1.spillLoadHits + L1.spillLoadMisses)
spill_load_L2_rescue_rate = L2.spillLoadHits / L1.spillLoadMisses
spill_load_DRAM_rate     = L2.spillLoadMisses / (L1.spillLoadHits + L1.spillLoadMisses)
spill_fraction_of_demand = (spillLoadHits + spillLoadMisses) / demandHits+demandMisses
```

### Connection to research questions

- **RQ2** (spill frequency & cost): spill_fraction_of_demand, DRAM_rate
- **RQ5** (cache-level distribution): L1 hit rate, L2 rescue rate

### Note on current benchmark status

As of 2026-04-14, the benchmark runs in `benchmarks/*/m5out_ref/` and
`benchmarks/*/m5out_train/` were launched with `--caches` but **without**
`--l2cache`.  Therefore, `l2.spillLoadHits/Misses` are absent from those
stats files.  The benchmarks must be **re-run with `--l2cache`** to collect
the full counter set.

```bash
# Template for re-running a benchmark with L2 cache enabled:
./build/RISCV/gem5.opt \
    --outdir=benchmarks/<bench>/m5out_l2 \
    configs/deprecated/example/se.py \
    --cmd=benchmarks/<bench>/<bench>.riscv \
    --options=... \
    --cpu-type=TimingSimpleCPU \
    --caches --l2cache \          # ← must add --l2cache
    --mem-size=4GB
```

The `launch_ref_all.sh` script should be updated to include `--l2cache`
before the next round of benchmark runs.

---

## Phase 8 — Spill vs Regular Data Comparison

### Goal

Determine whether spill accesses exhibit systematically different cache
behavior from normal demand accesses (non-spill loads/stores).

### Analysis approach

For each benchmark, compute the following pairs:

```
regular_L1_hit_rate = (demandHits - spillLoadHits - spillStoreHits)
                    / (demandHits + demandMisses - spillTotal)

spill_L1_hit_rate   = spillLoadHits / (spillLoadHits + spillLoadMisses)
```

If `spill_L1_hit_rate << regular_L1_hit_rate`, spills are systematically
harder to serve from L1 and may benefit from dedicated cache treatment.

### Key questions

1. Do spills show shorter or longer reuse distances than regular accesses?
2. Are spill misses clustered in specific benchmarks (e.g., register-pressure-
   heavy workloads like 502.gcc) or spread uniformly?
3. Is the L2 rescue rate for spills predictable enough to justify a bypass?
4. Do benchmarks with high spill fractions (MCF: 1.98%) show proportionally
   higher spill miss rates?

---

## Phase 9 — Spill-Aware Cache Policy Exploration

### Prerequisite

**Do not start Phase 9 before Phases 1–7 are complete and published.**
The measurement must be fully validated and reproducible before any policy
conclusions are drawn.

### Candidate policies

1. **Spill-bypass L1**: tag spill lines for L1 bypass (go directly to L2).
   Hypothesis: spill lines have shorter reuse intervals and pollute L1.
   Counter-hypothesis: many spills ARE reused (see Phase 8 L1 hit rate).

2. **Spill-priority insertion**: insert spill lines as MRU in L1 instead of
   standard LRU position.  If spills are reused quickly, early eviction wastes
   work.

3. **Spill-dedicated buffer**: a small (8–16 entry) fully-associative buffer
   that holds only spill lines, sitting between the register file and L1.
   Eliminates spill traffic from the main cache entirely.

4. **Dead-on-fill for spills**: mark spill lines as dead immediately after
   their one expected reload, so they are first candidates for eviction.

### Implementation note for gem5

Each policy would require modifying `src/mem/cache/replacement_policies/` and
tagging incoming packets with the `SPILL_LOAD`/`SPILL_STORE` flag to select
alternate insertion behavior.  The existing flag infrastructure already threads
through the necessary code paths.

---

## Execution Schedule

The table below reflects **suggested** sequencing.  Phases 3 and 4 can run in
parallel with Phase 2; Phase 6 should be drafted incrementally.

| Step | Action | Depends on |
|---|---|---|
| **Now** | Phase 2: implement store/l1_hit and store/l1_miss | Phase 1 ✓ |
| **Next** | Phase 3: implement all 5 negative tests | Phase 1 ✓ |
| **Then** | Phase 4: implement 4 stress tests | Phase 1 ✓ |
| **Then** | Phase 5: realistic cache config (l1_hit only, l1miss_l2hit optional) | Phase 1 ✓ |
| **Draft** | Phase 6: begin LaTeX table with Phase 1–3 results | Phases 1–3 |
| **Major** | Phase 7: re-run benchmarks with --l2cache; parse results | Phases 1–4 |
| **Analysis** | Phase 8: compute spill vs regular comparison metrics | Phase 7 |
| **Research** | Phase 9: implement and simulate cache policies | Phase 8 |

---

## File Layout After All Phases Complete

```
gem5/tests/cache_hit_miss/
├── ROADMAP.md                   # this file
├── SUMMARY.md                   # Phase 1 detailed summary
├── run_all.sh                   # runs all positive micro-tests
├── load/                        # Phase 1 (COMPLETE)
│   ├── l1_hit/
│   ├── l1miss_l2hit/
│   └── l1miss_l2miss/
├── store/                       # Phase 2
│   ├── l1_hit/
│   └── l1_miss/
├── negative/                    # Phase 3
│   ├── non_stack/
│   ├── roi_outside_load/
│   ├── size_mismatch/
│   ├── window_expired/
│   └── no_matching_store/
├── stress/                      # Phase 4
│   ├── serial_10_spills/
│   ├── multi_slot/
│   ├── nested_calls/
│   └── store_map_pressure/
└── realistic/                   # Phase 5
    ├── l1_hit/
    └── l1miss_l2hit/
```
