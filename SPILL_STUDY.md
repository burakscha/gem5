# Register Spill Study — Entry Point

Measuring register spill behaviour and its cache cost, on RISC-V SPEC CPU2017
under gem5's `TimingSimpleCPU`. This file is the map; each area has its own
README.

**Metric schema 10** (2026-11-04, refined 2026-11-05). Spills are found at
run time from effective addresses alone: no compiler information and no
base-register test. In the thesis this is *runtime-detected stack
store-load reuse*: an operational definition, not necessarily
compiler-generated spill code. Counter names: `total_` = whole simulation,
`roi_` = inside the ROI, `diag_` = diagnostic
([`general_reports/action_plan/COUNTER_NAMING.md`](general_reports/action_plan/COUNTER_NAMING.md)
has the migration from the earlier names).
Schema 9 (2026-10-14) took spill stores from GCC's `-dP` map and callee saves
from CFI, and required an `sp`/`s0` base register for the other stack pairs;
its results remain readable (`--schema 9`) but are not comparable. Schema 10
runs use their own build, `build/RISCV_SCHEMA10/gem5.opt`; `build/RISCV` keeps
the schema-9 binary. Results produced under schema 4 or older live in
`ARCHIVED/`.

## What a spill is here

| | Rule |
| --- | --- |
| spill store | a store inside the region of interest whose address lies in the process stack (not atomic, no fault): the store conditions of a spill; read back or not |
| spill load | a later load inside the ROI whose start address lies in the bytes `[address, address + size)` of the spill store that last wrote them; after a partial overwrite the newest store owns the overlap; widths may differ |
| spill event | a spill store read back by at least one spill load: one event per store, at its first reload |

Stores before the region of interest are not tracked; in a SimPoint run the
ROI is the simulated interval, so stores of the warmup do not pair either.
Only the owner of a load's start byte is read back. A store read back `n`
times is one spill event and `n` spill loads. LR/SC and AMOs are out of scope
(never spill stores or spill loads); a successful SC or an AMO still owns the
bytes it wrote, a failed SC changes nothing.

| Counter | Meaning |
| --- | --- |
| `total_insts`, `total_load`, `total_store` | Whole simulation. |
| `roi_total_insts`, `roi_load`, `roi_store` | Every instruction, load and store inside the ROI. |
| `roi_spill_store` | Every spill store of the ROI, read back later or not. |
| `roi_spill_event` | The spill stores read back at least once inside the ROI: one event per store. |
| `roi_spill_load` | Every spill load inside the ROI. Repeats count. |
| `roi_spill_store_*`, `roi_spill_event_*`, `roi_spill_load_*` | L1D/L2 hits and misses of each population (`_l1_hits`, `_l1_misses`, `_l2_hits`, `_l2_misses`, `_split_insts`). A store's cache outcome is known when it executes, but whether it starts a spill event only at its first reload, so `roi_spill_event_*` holds each event's store's own outcome, counted once. |
| `diag_store_map_evicted` | Store-table entries dropped at the size cap (non-zero: censored pairs). |
| `diag_load_after_stack_release`, `diag_event_after_stack_release` | Spill loads (events) whose stack bytes were released between store and load: suspicious pairs, measured below 0.02 %. |

`roi_spill_event ≤ roi_spill_store ≤ roi_store` and
`roi_spill_event ≤ roi_spill_load ≤ roi_load`. The reports also show the
spill stores never read back (`roi_spill_store - roi_spill_event`) and the
other stores (`roi_store - roi_spill_store`); L2 miss rates are local
(denominator: the L1D misses of that kind).

gem5 reports `stackStoreHits/Misses` and `spillLoadHits/Misses` at L1D and L2
(names unchanged); they equal the detector's `roi_spill_store_*` and
`roi_spill_load_*`. The full rules
are in [`tests/spill_test/README.md`](tests/spill_test/README.md); the
schema-10 plan and the list of removed counters are in
[`general_reports/action_plan/README.md`](general_reports/action_plan/README.md).

## Running an experiment

```bash
BUILD_DIR=build/RISCV_SCHEMA10 ./scripts/build_gem5_riscv.sh   # only after changing the detector
./scripts/spec_spill_runner.sh check test standard all

setsid nohup ./scripts/launch_spill_batch.sh test standard \
    > logs/batch_test_standard.log 2>&1 < /dev/null &

./scripts/spec_spill_runner.sh status test standard all
```

The second argument is the cache profile: `standard` or `small` (capacities),
optionally with an organisation suffix `-dm`, `-nway` (L1D 8-way, L2 16-way)
or `-fa` (fully associative), e.g. `small-fa`. See
[`scripts/SPEC_SPILL_RUNNER.md`](scripts/SPEC_SPILL_RUNNER.md#cache-profiles).

`launch_spill_batch.sh` caps concurrency at `MAX_JOBS` (default 6). Do not use
`spec_spill_runner.sh start ... all`: it fires all 17 workloads at once, which
has caused OOM kills on this host.

## Reporting

```bash
./scripts/spill_table.sh                 # numbered per-benchmark table + ratios
./scripts/spill_table.sh --csv out.csv   # same, plus CSV
./scripts/spill_report.sh                # table + CSV + LaTeX + one-page PDF
```

## Layout

```
scripts/            build, run and report tooling          -> scripts/README.md
benchmarks/<b>/     binary + inputs (+ the schema-9 <binary>.stack_pc_map, unused now)
  m5out_<b>/        one directory per run,
                    m5out_<run_id>_<HHMM>_<DDMMYYYY>/
  reports/          per-benchmark analysis documents
general_reports/    everything not tied to one benchmark   -> general_reports/README.md
  definitions/      the spill definition report
  results/          cross-benchmark result reports
ARCHIVED/           schema ≤4 results and reports
logs/               batch launcher logs
tests/spill_test/   27 hand-verified assembly cases        -> tests/spill_test/README.md
```

## Verifying the detector

```bash
python3 tests/spill_test/run_tests.py
```

27 deterministic RISC-V assembly cases with exact expected counts. They also
assert that the gem5 cache statistics and the detector counters agree at both
cache levels, for spill stores and spill loads. `tc15` also checks the
detector's ROI against gem5's own ROI statistics, under se.py and under the
stdlib; `tc24` runs a SimPoint checkpoint/restore and checks the interval the
same way; `tc23` covers LR/SC and AMOs.

## Known limitations

- **Address-only detection: spill-like memory traffic, not a bound.** A
  spill store read back later makes a spill event whatever its purpose:
  register spills, callee-saved register saves, stack-passed arguments and
  memory-resident locals (arrays, structs, buffers reached through
  pointers) all count. Real compiler spills are missed when their store
  lies before the ROI or their reload after it, or when they are never read
  back. The counts are therefore neither an upper nor a lower bound of
  compiler spill traffic: *runtime-detected stack store-load reuse
  (spill-like memory traffic)*.
- **Popped frames.** A store stays readable until a newer store overwrites
  its bytes; returning from its function does not end it. A later function
  that reads a slot it never wrote (an uninitialized local, or uninitialized
  bytes of a copied struct) pairs with the dead store (`tc25`, asserted).
  Correct code reads its own slots after writing them, so it pairs with its
  own stores. `diag_load_after_stack_release` measures how often a pair's
  stack bytes were released in between (a diagnostic; the counts do not
  change).
- **Atomics are out of scope.** LR/SC and AMOs are never spill stores or
  spill loads; they only end older stores' ownership of the bytes they write.
  `roi_store` counts `isStore()` (SCs included) while gem5's
  `commitStats0.numStoreInsts` counts `isStore() || isAtomic()`; the reports
  surface that delta as a cross-check column.
- **Start-address rule.** A load that also reads bytes of other stores reads
  back only the owner of its start byte. Counting every owner is a possible
  extension, not implemented.
- **Benchmarks run from the repository root.** The worker does `cd $ROOT_DIR`,
  so a few inputs must stay there: `hkrdenq/`, `1am0/` and `aminos/` are
  required by nab and must not be moved or deleted.
- **TimingSimpleCPU only**, single core, SE mode.
