# SpillDetector integration tests

This directory contains deterministic RISC-V assembly tests for the corrected
schema-v4 spill metrics. The suite assembles every source in a temporary
directory, runs it with `TimingSimpleCPU`, L1D and L2 caches, parses both
`riscv_spill_stats.txt` and `stats.txt`, and fails on any counter mismatch.

Run from the gem5 root:

```bash
python3 tests/spill_test/run_tests.py
```

Run selected cases or keep artifacts:

```bash
python3 tests/spill_test/run_tests.py tc5_repeated_reload tc11_split_line
python3 tests/spill_test/run_tests.py --keep /tmp/spill-results
```

The default toolchain paths can be overridden with `--gem5`, `--assembler`,
`--linker`, and `--nm`.

## Counter semantics

All instruction counters count successfully completed dynamic instructions.
The `m5_work_begin` and `m5_work_end` marker instructions are excluded from
the ROI. Instructions used to prepare the arguments for `m5_work_end` remain
inside the ROI, as they execute before the marker.

- `total_instructions`, `total_load_insts`, `total_store_insts`: whole-run
  committed instruction counts.
- `roi_instructions`, `roi_load_insts`, `roi_store_insts`: committed counts
  between ROI markers.
- `roi_candidate_stack_store_insts`: stores eligible to start a spill pair.
  In heuristic mode these are SP/FP-relative stack stores; in exact mode they
  are stack stores whose PCs appear in the supplied compiler map.
- `roi_spill_events`: store generations whose first qualifying later load was
  observed. A store followed by three matching loads is one event.
- `roi_spill_load_insts`: every qualifying reload, including repeated reloads.
- `roi_spill_store_insts`: the matched store, counted once when its first
  qualifying reload confirms it.
- `roi_spill_mem_insts`: `roi_spill_load_insts + roi_spill_store_insts`.
- `roi_repeated_spill_load_insts`: qualifying reloads after the first reload
  of the current store generation.
- `roi_nonspill_reuse`: same-address/same-size stack store-to-load reuse that
  is rejected by the SP/FP operand filter in heuristic mode.

The dynamic matching order is **STORE -> later LOAD**. A load followed by a
store is not a spill event. A newer store to the same address starts a new
generation and replaces the previous generation in the map.

## Instruction counts versus cache accesses

One memory instruction can cross a cache-line boundary and become two cache
requests. For this reason the report keeps instruction and access populations
separate:

```text
roi_spill_load_l1_accesses
  = roi_spill_load_insts + roi_spill_load_extra_fragments
  = roi_spill_load_l1_hits + roi_spill_load_l1_misses

roi_spill_store_l1_accesses
  = roi_spill_store_insts + roi_spill_store_extra_fragments
  = roi_spill_store_l1_hits + roi_spill_store_l1_misses
```

The same identities exist for candidate stores. With the suite's two-level
cache configuration:

```text
L2 accesses = L1 misses = L2 hits + L2 misses
```

`system.cpu.dcache.spillStoreHits/Misses` are retained for compatibility, but
they count **candidate** store requests because a future reload is unknown at
store issue time. The schema-v4 `roi_spill_store_l{1,2}_{hits,misses}` fields
are retrospective, confirmed-store results and are the correct headline
store population.

Useful percentages are:

```text
spill instruction share = roi_spill_mem_insts / roi_instructions
L1 hit rate              = L1 hits / (L1 hits + L1 misses)
L2 local hit rate        = L2 hits / (L2 hits + L2 misses)
L2 rescue of L1 total    = L2 hits / L1 accesses
DRAM share of L1 total   = L2 misses / L1 accesses
```

The L2 local hit rate and L2 rescue percentage have different denominators and
must not be compared as though they were the same metric.

## Classification modes

The default output is explicitly labelled:

```text
classification : heuristic_stack_store_reload_match
```

It detects same-address, same-size, stack-resident STORE -> LOAD pairs whose
effective-address base operands are `sp` or `s0/fp`. This is a measurable
heuristic, not proof of a compiler register-allocation spill. Callee-save
traffic can therefore be a heuristic positive.

For compiler-ground-truth experiments, supply a PC map:

```text
# spill_pc_map.txt
store 0x10120
load  0x10154
```

```bash
gem5.opt ... --param "system.cpu[0].spill_pc_map='/path/spill_pc_map.txt'"
```

Only mapped store/load PCs can form a pair in this mode, and the report is
labelled `compiler_pc_map_store_reload_match`. Addresses are runtime virtual
PCs; for position-independent binaries the map generator must apply the load
bias. `tc14_exact_pc_map` builds its map from ELF symbols and verifies that an
unmapped heuristic-looking pair is excluded.

## Coverage

- `tc1`-`tc3`: callee-save-shaped traffic, register pressure, loop reuse.
- `tc4a`-`tc4h`: all eight spill/non-spill load/store eviction-attribution
  boxes using a deterministic one-line L1D.
- `tc5`: repeated reloads of one store generation.
- `tc6`: unmatched candidate store.
- `tc7`: overwrite and two store generations at one slot.
- `tc8`: RISC-V address-base operand correctness (`sd s0, 0(a3)`).
- `tc9`: pre-ROI, in-ROI, and post-ROI separation plus global totals.
- `tc10`: load-before-store and width-mismatch negative cases.
- `tc11`: one cross-line store/load pair, two requests per instruction.
- `tc12`: multiple ROIs and per-ROI reset/append behavior.
- `tc13`: whole-run counters when no ROI exists.
- `tc14`: compiler PC-map exact mode.

For schema-v4 benchmark results, use:

```bash
python3 benchmarks/analyze_spill_metrics.py benchmarks/mcf/m5out_new_train
```
