# Counter naming (metric schema 10)

Decided by the user on 2026-11-05; the spill-event name on 2026-11-08; the
spill-store name on 2026-11-09. The renames change names only: every count,
hit and miss keeps its value (verified on all test cases each time, see the
end). gem5's own `stats.txt` names (`system.cpu.dcache.spillLoadHits`,
`stackStoreHits`, ...) stay as they are; they serve the gem5/detector
cross-check.

## Convention

| Prefix | Meaning |
|---|---|
| `total_` | counted over the whole simulation |
| `roi_` | counted only between the ROI begin and end (SimPoint: the interval) |
| `diag_` | technical diagnostic: checks the simulation and the matching, not a result |

Cache outcomes: `roi_<population>_<l1|l2>_<hits|misses>`.
Ratios and differences are not counters: the report scripts compute them.

## Definitions

- `roi_spill_store`: every store that meets the store conditions of a spill:
  inside the ROI, to the process stack, not an atomic operation, no fault.
  Read back or not (the stack condition is one of the spill conditions, so
  there is no separate "stack store" count).
- `roi_spill_event`: the spill stores read back at least once inside the ROI.
  One event per store, made at its first reload; a store read back n times is
  one event and n spill loads; another store, to the same address or not,
  read back makes another event.
- `roi_spill_load`: load instructions inside the ROI that read back an earlier
  valid spill store of the ROI; repeats included.
- Operational definition: these are not necessarily compiler-generated spill
  instructions (runtime-detected stack store-load reuse, spill-like memory
  traffic).
- `roi_spill_event_l1_misses` (and the other `roi_spill_event_*` outcomes) is
  the store side of each event: the store's own result when it executed,
  added at the first reload, once per store. `roi_spill_store_*` holds every
  spill store's outcome.

## Detector output (`riscv_spill_stats.txt`)

| Before 2026-11-05 | 11-05 .. 07 | 11-08 | Now (11-09) |
|---|---|---|---|
| `total_insts`, `total_load`, `total_store` | same | same | same |
| `roi_total_insts`, `roi_load`, `roi_store` | same | same | same |
| `stack_store` | `roi_stack_store` | `roi_stack_store` | **`roi_spill_store`** |
| `spill_store`, `spill_event` (always equal) | `roi_spill_store` (!) | `roi_spill_event` | **`roi_spill_event`** |
| `spill_load` | `roi_spill_load` | `roi_spill_load` | `roi_spill_load` |
| `stack_store_l1_hits`, ... | `roi_stack_store_l1_hits`, ... | same | `roi_spill_store_l1_hits`, ... |
| `spill_store_l1_hits`, ... | `roi_spill_store_l1_hits`, ... (!) | `roi_spill_event_l1_hits`, ... | `roi_spill_event_l1_hits`, ... |
| `spill_load_l1_hits`, ... | `roi_spill_load_l1_hits`, ... | same | same |
| `<p>_split_insts` | `roi_<p>_split_insts` | same | same (`<p>` renamed as above) |
| `<p>_extra_fragments` | removed (always equal to `split_insts`) | | |
| `spill_reuse_log2[k]` | `roi_spill_store_reuse_log2[k]` | `roi_spill_event_reuse_log2[k]` | removed (11-09, unused) |
| `entry_total_insts` | `diag_insts_before_roi` | same | removed (11-09: gem5's pre-ROI block has it) |
| `diag_store_map_evicted` | same | same | same |
| | `diag_load_after_stack_release` (11-06) | same | same |
| | `diag_store_first_reload_after_stack_release` (11-06) | `diag_event_after_stack_release` | same |
| `metric_schema` 10 | 10 | 10 | 10 |

(!) The name `roi_spill_store` meant the spill events from 2026-11-05 to 07
and means every spill store now. Those outputs exist only in test work
directories and `logs/validation_diag_20261106/`; they are recognized by
their `roi_stack_store` field (`cache_status.canonical()`,
`spill_report.canonical_roi()`, `spill_table.sh`). No schema-10 campaign
result exists in an older format.

The identities the tests assert:

```text
roi_spill_event <= roi_spill_store <= roi_store
roi_spill_event <= roi_spill_load  <= roi_load
roi_<p>_l1_hits + roi_<p>_l1_misses = <p count> + roi_<p>_split_insts
roi_<p>_l2_hits + roi_<p>_l2_misses = roi_<p>_l1_misses
roi_spill_event_* <= roi_spill_store_*
gem5 stackStoreHits/Misses = roi_spill_store_l1/l2_hits/misses
gem5 spillLoadHits/Misses  = roi_spill_load_l1/l2_hits/misses
```

## Report and CSV names (schema 10)

| Name | Meaning |
|---|---|
| `roi_spill_store`, `roi_spill_event`, `roi_spill_load` | as above |
| `roi_unread_spill_store` | computed: `roi_spill_store - roi_spill_event` |
| `roi_non_spill_store`, `roi_other_store` | computed: `roi_store - roi_spill_store` |
| ratios | `spill/roi`, `spill_load/load`, `spill_store/store`, `spill_event/store`, `spill_event/spill_store`, `spill/mem` (formulas in `cache_status.RATIO_FORMULAS_10`) |
| miss rates | `spill_st_*` (spill stores), `spill_event_*` (their read-back part), `unread_st_*` (never read back), `other_st_L1miss` (no spill store), `spill_ld_*`, `other_ld_L1miss`, L2 local |
| `spill_table.sh` | SP_STORE, SP_EVENT, SPEV%SP_ST |

Retired report names: `roi_spills`, `roi_matched_stack_store`,
`roi_unmatched_stack_store`, `roi_non_stack_store`, `roi_total_load`,
`roi_total_store`, `matched_st_*`, `unmatched_st_*`, `non_stack_st_*`,
ratios `stack_store/store`, `spill_event/stack_store`,
`unmatched_stack_store/store`, `non_stack_store/store`.

Results of schema 9 keep their own names and meaning: `spill_store` are the
compiler-labelled spill stores, read back or not, `spill_event` those read
back, `stack_store` the sp/s0-based stores; the same structure as schema 10
(spill stores, their read-back part, spill loads).

## Files that use the names

| File | What changed |
|---|---|
| `src/cpu/simple/spill_detector.cc/.hh` | the ROI summary, definitions block, member names |
| `tests/spill_test/run_tests.py`, `README.md` | expected keys, identities, retired-name check |
| `cache_scripts/cache_status.py` | `canonical()`, counts, ratios, miss rates, overview |
| `cache_scripts/summary_tables.py`, `compare_inputs.py`, `benchmark_reports.py`, `export_results.py` | column keys, CSV fields |
| `scripts/spill_report.py` | `canonical_roi()`, values, table, CSV, LaTeX |
| `scripts/spill_table.sh` | field names, older formats |
| `cache_scripts/simpoint_combine.py` | `diag_insts_before_roi` (still read from older outputs) |
| `SPILL_STUDY.md`, `cache_scripts/README.md` | documentation |

Unchanged on purpose: historical documents (`ARCHIVED/`, snapshots,
`general_reports/results/schema8_*`, `tests/spill_test/retired_schema9/`).

## Verification

Each rename: the 27 test cases run with the binary before and after it, in
work directories of the same path length (the path is in argv, on the
stack, and its length moves cache lines); every field of every ROI and
GLOBAL block, mapped old name -> new name, and every `stats.txt` line except
the host times must be equal. 2026-11-08 and 2026-11-09: 29 spill logs,
1123 fields each, no difference.
