# Register Spill Study — Entry Point

Measuring register spill behaviour and its cache cost, on RISC-V SPEC CPU2017
under gem5's `TimingSimpleCPU`. This file is the map; each area has its own
README.

**Metric schema 7** (2026-09-16). Results produced under schema 4 or older use
retired counter names and are *not* comparable — those live in `ARCHIVED/`.

## What a spill is here

One `spill_event` is a stack store issued SP/FP-relative inside the region of
interest that is later read back from the same address at the same access
width.

| Counter | Meaning |
| --- | --- |
| `spill_store` | Write side: every SP/FP-relative stack store in the ROI, read back later or not. |
| `spill_load` | Read-back side: every load that reads such a store back. Repeats count. |
| `spill_event` | One (store, first read-back) pair — one *potential* spill. |
| `total_spill_insts` | `spill_store + spill_load`. |
| `spill_store_unpaired` | `spill_store − spill_event`: written, never read back inside the ROI. |
| `repeat_spill_load` | `spill_load − spill_event`. |

Two identities hold in every run: `spill_event ≤ spill_store` (a value may be
written and never read back) and `spill_load ≥ spill_event` (a value may be
read back many times).

These are *potential* spills: at the microarchitectural level they cannot be
separated from ABI callee-save traffic or ordinary scalar stack locals, so the
figures are an upper bound on true register-allocator spilling. The full rule
sets (S1–S3 on the store side, L1–L6 on the load side) and the caveats are in
**[`general_reports/definitions/spill_definition.pdf`](general_reports/definitions/spill_definition.pdf)**.

## Running an experiment

```bash
./scripts/build_gem5_riscv.sh                         # only after changing the detector
./scripts/spec_spill_runner.sh check test standard all

setsid nohup ./scripts/launch_spill_batch.sh test standard \
    > logs/batch_test_standard.log 2>&1 < /dev/null &

./scripts/spec_spill_runner.sh status test standard all
```

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
benchmarks/<b>/     binary + inputs
  m5out_<b>/        one directory per run,
                    m5out_<run_id>_<HHMM>_<DDMMYYYY>/
  reports/          per-benchmark analysis documents
general_reports/    everything not tied to one benchmark   -> general_reports/README.md
  definitions/      the spill definition report
  results/          cross-benchmark result reports
ARCHIVED/           schema ≤4 results and reports
logs/               batch launcher logs
tests/spill_test/   25 hand-verified assembly cases        -> tests/spill_test/README.md
```

## Verifying the detector

```bash
python3 tests/spill_test/run_tests.py
```

25 deterministic RISC-V assembly cases with exact expected counts. They also
assert that the gem5 cache statistics and the detector counters agree at both
cache levels, in both directions (`SPILL_LOAD` ↔ `spill_load`,
`SPILL_STORE` ↔ `spill_store`). `tc15` also checks the detector's ROI against
gem5's own ROI statistics, under se.py and under the stdlib.

## Known limitations

- **Heuristic classification.** The store/reload rules cannot separate compiler
  register spills from callee-save traffic or scalar locals. The detector
  accepts a compiler-generated PC map (`spill_pc_map`) that replaces the
  heuristic tests with exact instruction addresses; that path is implemented
  and covered by `tc14_exact_pc_map`, but no map has been generated yet. This
  is the highest-value next step.
- **L2 eviction attribution mislabels stores.** `BaseCache::incMissCount()`
  classifies by `pkt->isRead()`. At the L1 a store is a `WriteReq`, but it
  reaches the L2 as a `ReadExReq`, so every L2 store miss lands in a *load*
  box. Visible in the data: `system.l2.spillStoreEvictedBy*` and
  `nonSpillStoreEvictedBy*` are exactly zero while `system.l2.spillStoreMisses`
  is not. The L1 eight-box table is unaffected.
- **Eviction attribution is not ROI-scoped.** The ledger and the eight
  counters accumulate from the first instruction of the simulation, while the
  `SPILL_*` tags only exist inside the ROI, so the non-spill control boxes
  include start-up traffic that the spill boxes cannot.
- **Atomics are not tracked.** `initiateMemAMO()` has no detector hook, so
  `roi_store` counts only `isStore()` while gem5's `commitStats0.numStoreInsts`
  counts `isStore() || isAtomic()`. The reports surface that delta as a
  cross-check column.
- **Benchmarks run from the repository root.** The worker does `cd $ROOT_DIR`,
  so a few inputs must stay there: `hkrdenq/`, `1am0/` and `aminos/` are
  required by nab and must not be moved or deleted.
- **TimingSimpleCPU only**, single core, SE mode.
