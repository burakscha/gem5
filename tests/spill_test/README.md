# SpillDetector integration tests

Deterministic RISC-V assembly tests for the metric-schema-10 spill counters.
The suite assembles every source in a temporary directory, runs it with
`TimingSimpleCPU`, L1D and L2 caches, parses both `riscv_spill_stats.txt` and
`stats.txt`, and fails on any counter mismatch.

Run from the gem5 root:

```bash
python3 tests/spill_test/run_tests.py
```

Run selected cases or keep artifacts:

```bash
python3 tests/spill_test/run_tests.py tc5_repeated_reload tc11_split_line
python3 tests/spill_test/run_tests.py --keep /tmp/spill-results
```

The default gem5 is `build/RISCV_SCHEMA10/gem5.opt`; it and the toolchain
paths can be overridden with `--gem5`, `--assembler` and `--linker`.

## Counter semantics

Names follow one convention (`general_reports/action_plan/COUNTER_NAMING.md`):
`total_` = whole simulation, `roi_` = inside the ROI, `diag_` = technical
diagnostic; cache outcomes are `roi_<population>_<l1|l2>_<hits|misses>`.
Ratios and differences are left to the report scripts.

All instruction counters count successfully completed dynamic instructions.
The `m5_work_begin` and `m5_work_end` marker instructions are excluded from
the ROI. Instructions used to prepare the arguments for `m5_work_end` remain
inside the ROI, as they execute before the marker.

**Global (whole simulation)**, in the `GLOBAL SUMMARY` block:
`total_insts`, `total_load`, `total_store`, committed instruction counts for
the entire run, ROI and non-ROI alike.

**ROI**, in each `ROI SUMMARY` block:

- `roi_total_insts`, `roi_load`, `roi_store`: committed counts between the ROI
  markers. gem5's own `simOps` and `commitStats0.numLoadInsts/numStoreInsts`
  cover the same window (workbegin/workend dump and reset the statistics), so
  they serve as an independent cross-check. Expect a small store-side
  difference: gem5 counts `isStore() || isAtomic()` while the detector counts
  only `isStore()`, so the delta is the ROI's atomic instructions.

### Spill detection (schema 10)

A spill is found from effective addresses alone. No compiler information
(the `-dP` map) and no base-register test (`sp`/`s0`) takes part. In the
thesis this is called *runtime-detected stack store-load reuse*: an
operational definition, not necessarily compiler-generated spill code.

| | Store side |
|---|---|
| S1 | a store instruction, not a store-conditional (atomics are out of scope, below) |
| S2 | inside the ROI |
| S3 | address in the process stack region (`stackMin <= addr < stackBase`; the first access to an unmapped stack page faults and re-executes after gem5 grows the stack, see `tc26`) |
| S4 | completed without a fault |

Every store passing S1-S4 is a **spill store**, read back later or not:
these are the store conditions of a spill, and the stack condition is one of
them. It is recorded in
`store_map`, which owns the bytes `[address, address + size)` of each store.
A newer store drops the entries whose every byte it overwrites; where it
overlaps an older one only partly, the older keeps its other bytes and the
newer owns the overlap.

| | Load side |
|---|---|
| L1 | a load instruction, not a load-reserved |
| L2 | inside the ROI |
| L3 | address in the stack region |
| L4 | a spill store in `store_map` covers the load's start address, `store_addr <= load_addr < store_addr + store_size`; the newest such store is taken |
| L5 | the store came first (`load_tick > store_tick`) |
| L6 | that store is still the newest owner when the load commits |
| L7 | completed without a fault |

A load passing L1-L7 is a **spill load**. The spill store it reads back is a
store of a **spill event**: one event per store, at its first reload,
however often it is read back. The widths
may differ: two 4-byte stores read back by one 8-byte load pair with the
first store; the upper half of an 8-byte store read by `lw` pairs with it.
Only the owner of the load's start byte is read back: when a load also
reads bytes of other stores, those are not counted (start-address rule).
A partly overwritten store stays in `store_map` as long as it owns bytes;
a store whose every byte was overwritten, by one newer store or by several,
is never read back. Storing the same value again (a silent store) is a new
spill store.

Stores before the ROI are not tracked, so a reload of one is not a pair.
In a SimPoint run the ROI is the simulated interval, opened and closed by
Python between two instructions (`restoreSimpointCheckpoint` in
`configs/common/Simulation.py`): stores of the warmup do not pair either.
The dynamic order is **STORE -> later LOAD**: a load followed by a store is
not a pair.

Atomic memory operations (LR/SC, AMO) are out of scope: they are never
spill stores or spill loads, and they are not tagged for the caches. A
successful SC or an AMO still owns the bytes it wrote, so a later load does
not pair through it with an older store. A failed SC (extra data 0, set by
the ISA or the cache) wrote nothing and changes nothing.

Counters:

- `roi_spill_store`: every spill store (S1-S4), read back later or not.
- `roi_spill_event`: the spill stores read back at least once inside the ROI:
  one event per store, made at its first reload. Read back again, a store
  stays one event; another store, to the same address or not, read back
  makes another event.
- `roi_spill_load`: every spill load, repeats included.

```text
roi_spill_event <= roi_spill_store <= roi_store   (a store may be written and never read back)
roi_spill_event <= roi_spill_load  <= roi_load    (a store may be read back many times)
spill stores never read back in the ROI = roi_spill_store - roi_spill_event
stores that are no spill store          = roi_store - roi_spill_store
repeat reloads                          = roi_spill_load - roi_spill_event
```

### Cache outcomes

TimingSimpleCPU tags every spill store (request flag `STACK_STORE`) and every
spill load (`SPILL_LOAD`), so the caches count their hits and misses. Whether
a spill store starts a spill event is known only at its first reload, so each
store keeps its own cache outcome in `store_map`, and the spill-event tally
adds it then, once per store: `roi_spill_event_l1_misses` is the store's own
L1D result when it executed, counted at the later load that makes it a spill
event. Three
populations, each with `_l1_hits`, `_l1_misses`, `_l2_hits`, `_l2_misses`,
`_split_insts`:

| detector field prefix | population | gem5 statistic (`system.cpu.dcache`, `system.l2`) |
|---|---|---|
| `roi_spill_store` | every spill store | `stackStoreHits/Misses` (equal, asserted) |
| `roi_spill_event` | the read-back spill stores, once each | none: the cache cannot know at the store |
| `roi_spill_load` | every spill load | `spillLoadHits/Misses` (equal, asserted) |

gem5's own statistic names are not changed: they are the independent side of
the cross-check. One memory instruction can cross a cache-line boundary and
become two cache requests (never more), so instruction and access counts are
kept apart:

```text
<p>_l1_hits + <p>_l1_misses = instructions + <p>_split_insts
<p>_l2_hits + <p>_l2_misses = <p>_l1_misses            (L2 accesses = L1 misses)
```

### Technical diagnostics

- `diag_store_map_evicted`: store-table entries dropped at the size cap. A
  nonzero value means some pairs were censored and the counts are low.
- `diag_load_after_stack_release`: spill loads whose byte lay below `sp` at
  some point after its store, i.e. the stack there was released (a frame
  popped) and may have been reused: suspicious pairs, not necessarily
  wrong. `diag_event_after_stack_release`: spill events whose
  first spill load is such a load. They are what a frame-lifetime rule
  would take from `roi_spill_load` and `roi_spill_event`. The detector
  reads `sp` at every committed ROI instruction for this, and only for
  this: `sp` never decides whether an access is a spill. A store written
  below `sp` counts as released from the start. The CPU parameter
  `spill_track_stack_release` (default `True`) turns it off; the lines are
  then absent. Only `tc25` has such a pair.
- `roi_<p>_split_insts`: cross-line instructions (above).

The instructions before the ROI are not a detector counter: gem5's pre-ROI
statistics block (`simInsts`) holds them. The store-to-reload distance
histogram was dropped on 2026-11-09.

## Coverage

- `tc1`: callee-saved save/restore of s0-s5: six pairs.
- `tc2`, `tc3`: register-pressure and loop reuse shapes.
- `tc5`: repeated reloads of one store: one event, three spill loads.
- `tc6`: a spill store never read back: no event.
- `tc7`: overwrite and two store generations at one slot.
- `tc8`: a store through `a3` (`sd s0, 0(a3)`) and its reload pair: the base
  register plays no part.
- `tc9`: pre-ROI, in-ROI, and post-ROI separation plus global totals.
- `tc10`: loads that do not read a store back: load before the store, a load
  at the store's end address, a load starting below the store.
- `tc11`: one cross-line store/load pair, two requests per instruction.
- `tc12`: multiple ROIs and per-ROI reset/append behavior.
- `tc13`: whole-run counters when no ROI exists.
- `tc14`: a source that still carries schema-9 `spill_store`/`csave_store` labels:
  they change nothing, every pair is found by address.
- `tc15`: the detector ROI against gem5's own ROI. The same binary runs under
  se.py, under the stdlib with `exit_on_work_items=False`, and under the
  stdlib default. In the first two, gem5's ROI statistics block must equal
  the detector ROI plus the `work_end` marker instruction, the work-item tick
  histogram must equal the block's `simTicks`, and the blocks must add up to
  the detector's `total_insts`. Under the stdlib default, gem5's ROI must be
  exact and `Simulator.get_roi_ticks()` must match it; the detector sees no
  ROI there, because `workbegin()` returns before the detector hook. That is
  asserted, so the behavior cannot change unnoticed.
- `tc16`: same-address store/load reuse on a non-stack (`.bss`) address is
  not counted.
- `tc17`: pinned cache outcomes of three pairs with a one-line L1D and a
  1 KiB direct-mapped L2: L1 hit; L1 miss -> L2 hit; L1 miss -> L2 miss. `sp`
  is aligned first, because the initial stack pointer moves with the binary
  path length.
- `tc18`: a pair 120,003 instructions apart is still paired (no time window).
- `tc19`: every store/reload form a rv64gc binary uses for stack slots
  (compressed and 32-bit, integer and FP, `sp` and `s0` based), one ROI each.
- `tc21`: reloads narrower or wider than their store: two `sw` read back by
  one `ld` (pairs with the first store, the second stays unpaired: the
  start-address rule), the upper half of an `sd` read by `lw`, two bytes of
  an `sd` read by `lh`, and the newest of two overlapping stores owning the
  overlap while the older keeps its other bytes.
- `tc22`: an `sd` overwritten by two `sw` (no single newer store covers it)
  is never read back, each `sw` pairs with its own reload; a silent store is
  a new spill store.
- `tc23`: atomics. `lr.d` is not a spill load; after a successful `sc.d` or
  an AMO the reload is not a pair with the older `sd`; after a failed `sc.d`
  it is; an AMO over half an `sd` leaves the other half paired. The program
  exits with status 1 if an SC does not succeed/fail as intended.
- `tc24`: a SimPoint point as `cache_scripts/simpoint.sh` runs it: se.py takes
  the checkpoint of interval 1 (length 40, warmup 20) with AtomicSimpleCPU,
  then restores it into TimingSimpleCPU with caches. A warmup store read back
  inside the interval does not pair; the interval's first instruction is
  counted; gem5's interval block equals the detector ROI exactly (no marker
  offset). AtomicSimpleCPU takes the checkpoint one instruction late (it
  services the instruction-count event at the start of its next tick and
  still executes that instruction), which the program's layout accounts for.
- `tc25`: frames reused by later calls (`call`/`ret`). A function's store to
  a slot that a later function writes again and reads pairs with the later
  store; a stack-passed argument read by the callee pairs (its frame is
  alive). Known limitation, asserted: a function that reads a slot it never
  wrote pairs with the store of an earlier, already returned frame, because
  a store ends only when a newer store overwrites it.
- `tc26`: the first store to a stack page gem5 has not mapped yet lies below
  `stackMin`; its translation faults, the attempt is discarded, gem5 grows
  the stack and the store re-executes. It is counted once and paired; the
  case also checks gem5's "Increasing stack size by one page" message.
- `tc20_cache_organization_{dm,nway,fa}`: one program under the three L1D/L2
  organisations of the runner's `small-*` profiles. Two reloads are preceded
  by one resp. eight conflicting lines, so the L1 reload outcome is miss/miss
  under direct-mapped, hit/miss under 8-way and hit/hit under fully
  associative (FALRU). A mis-configured profile fails here.

The eviction-attribution tests `tc4a`-`tc4h` were retired with schema 10,
together with the statistics they checked; see `retired_schema9/`.

For benchmark results, use the reporting commands:

```bash
./scripts/spill_table.sh     # numbered table of counts and ratios
./scripts/spill_report.sh    # table + CSV + LaTeX + one-page PDF
```

To analyse individual gem5 output directories instead:

```bash
python3 scripts/spill_report.py --no-files \
    benchmarks/mcf/m5out_mcf/latest_test_small-2way_mcf
```
