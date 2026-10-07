# SpillDetector integration tests

This directory contains deterministic RISC-V assembly tests for the corrected
schema-v6 spill metrics. The suite assembles every source in a temporary
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
The counters come in three tiers.

**Global (whole simulation)**, in the `GLOBAL SUMMARY` block:

- `total_insts`, `total_load`, `total_store`: committed instruction counts for
  the entire run, ROI and non-ROI alike.
- `total_spill_event`: spill events across every ROI in the run.

**ROI**, in each `ROI SUMMARY` block:

- `roi_total_insts`, `roi_load`, `roi_store`: committed counts between the ROI
  markers. gem5's own `simOps` and `commitStats0.numLoadInsts/numStoreInsts`
  cover the same window (workbegin/workend dump and reset the statistics), so
  they serve as an independent cross-check. Expect a small store-side
  difference: gem5 counts `isStore() || isAtomic()` while the detector counts
  only `isStore()`, so the delta is the ROI's atomic instructions.

**Spill**, in each `ROI SUMMARY` block. These exist only inside a ROI, because
the detector clears its store map on ROI entry and matches nothing outside:

- `spill_store`: the **write side**. Every stack store issued SP/FP-relative
  inside the ROI, whether or not the value is ever read back. This is exactly
  the population the `SPILL_STORE` request flag tags.
- `spill_load`: the **read-back side**. Every load that reads a value written
  by such a store, from the same address at the same width. Repeats count, so
  a value reloaded three times contributes three.
- `spill_event`: one `(spill_store, first spill_load)` **pair** — one
  potential spill.
- `total_spill_insts`: `spill_store + spill_load`, the dynamic memory
  instructions the spill population is responsible for.
- `spill_store_unpaired`: `spill_store - spill_event`, values written inside
  the ROI and never read back there.
- `repeat_spill_load`: `spill_load - spill_event`, the read-backs after the
  first for the current store generation.

The store side and the load side are decided at different times, which is why
all three counters differ:

```text
spill_event <= spill_store   (a value may be written and never read back)
spill_load  >= spill_event   (a value may be read back many times)
```

The matching rules, in the order the detector applies them:

| | Store side, checked when the store executes |
|---|---|
| S1 | inside the ROI |
| S2 | address in the process stack region (`stackMin <= addr < stackBase`) |
| S3 | effective-address base register is `sp`/`x2` or `s0`/`fp`/`x8` |

A store passing S1-S3 is counted in `spill_store`, tagged `SPILL_STORE`, and
recorded in `store_map[address]`. A newer store to the same address replaces
the entry, so the older generation can no longer pair.

| | Load side, checked when the load executes |
|---|---|
| L1 | inside the ROI |
| L2 | address in the stack region |
| L3 | `store_map` holds an entry at exactly this address |
| L4 | `load_tick > store_tick` — the store came first |
| L5 | `load_size == store_size` — same access width |
| L6 | the load and its matched store are both SP/FP-relative |

A load passing L1-L6 is counted in `spill_load` and tagged `SPILL_LOAD`; the
first such load for a store generation also increments `spill_event`.

These are **potential** spills. The rules prove that a stack slot was written
SP/FP-relative and, for a `spill_event`, later read back at the same width;
they do not prove that a register allocator ran out of registers. ABI
callee-save save/restore pairs and ordinary scalar stack locals satisfy
exactly the same tests, so the counts are an upper bound on true
register-allocator spilling. `spill_store` is the looser of the two sides: at
store time a later read-back is unknowable, so it only has to pass S1-S3.
Use `spill_pc_map` (see Classification modes) when an exact answer is needed.

Diagnostic counters are prefixed `diag_` and are never mixed into the headline
numbers:

- `diag_paired_store_l1_*` / `diag_paired_store_l2_*`: cache behaviour of just
  the paired subset of `spill_store`, captured per store and attributed when
  the pairing happens. The headline `spill_store_l1_*` fields cover the whole
  write side instead.
- `diag_nonspill_reuse`: same-address/same-size stack store-to-load reuse that
  passes L1-L5 but fails L6 (stack arrays, structs and buffers reached through
  computed pointers).
- `diag_store_map_live/peak/evicted`: detector map occupancy. A nonzero
  `evicted` means some pairs were censored and the counts are low.

The dynamic matching order is **STORE -> later LOAD**. A load followed by a
store is not a spill event. A newer store to the same address starts a new
generation and replaces the previous generation in the map.

## Instruction counts versus cache accesses

One memory instruction can cross a cache-line boundary and become two cache
requests. For this reason the report keeps instruction and access populations
separate:

```text
spill_load_l1_accesses
  = spill_load + spill_load_extra_fragments
  = spill_load_l1_hits + spill_load_l1_misses

spill_store_l1_accesses
  = spill_store + spill_store_extra_fragments
  = spill_store_l1_hits + spill_store_l1_misses
```

The same identities exist for `diag_paired_store_*`. With the suite's two-level
cache configuration:

```text
L2 accesses = L1 misses = L2 hits + L2 misses
```

The gem5 cache statistics and the detector counters deliberately cover
different store populations:

- `system.cpu.dcache.spillLoadHits/Misses` == `spill_load_l1_hits/misses`. The
  `SPILL_LOAD` flag is only set once the matcher has confirmed the pairing, so
  the two agree exactly, and `spill_report.py` asserts it.
- `system.cpu.dcache.spillStoreHits/Misses` == `diag_stack_store_l1_*`, **not**
  `spill_store_l1_hits/misses`. Whether a store will ever be read back is unknown at
  issue time, so the flag has to tag the whole superset. The
  `spill_store_l1_*` fields are captured per store and attributed
  retrospectively when the pairing happens, which makes them the correct
  headline store population.

Useful percentages are:

```text
spill instruction share = total_spill_insts / roi_total_insts
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

For benchmark results, use the single reporting command, which prints the
hit/miss and spill/fill table and writes `results.csv`, `report.tex` and the
one-page `report.pdf`:

```bash
./scripts/spill_table.sh     # numbered table of counts and ratios
./scripts/spill_report.sh    # table + CSV + LaTeX + one-page PDF
```

To analyse individual gem5 output directories instead:

```bash
python3 scripts/spill_report.py --no-files \
    benchmarks/mcf/m5out_mcf/latest_test_standard_mcf
```
