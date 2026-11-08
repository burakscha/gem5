# test results, metric schema 8

Exported 2026-10-15 10:22 by `cache_scripts/export_results.py --schema 8 --input test`.

Superseded: the current detector writes schema 9. Schema 8 paired a reload with its store only at the same address and width, so it missed partial and merged reloads (up to 15% of the spill reloads in bwaves, 8.5% in leela, 3% in x264, under 0.1% in most benchmarks). Its instruction counts, spill stores and cache behaviour of the reloads it did pair remain valid; spill_load, spill_event and the other_stack counts are lower than under the current rule.

| file | content |
|---|---|
| `overview.txt` | status overview (every queued input and configuration) |
| `test_small-2way.txt` | small-2way: cache geometry, tables 1-3 |
| `test_small-fa.txt` | small-fa: cache geometry, tables 1-3 |
| `test_small-dm.txt` | small-dm: cache geometry, tables 1-3 |
| `test_small-4way.txt` | small-4way: cache geometry, tables 1-3 |
| `test_small-8way.txt` | small-8way: cache geometry, tables 1-3 |
| `test_results.csv` | one row per configuration and run: tables 1-3 (ratios and miss rates in percent, without the sign), raw ROI counters, gem5 cache counts, run directory |
| `test_report.pdf` | LaTeX report, one page per configuration (`report_<config>/report.tex` is its source) |

Runs: 170 of 175 completed.

Missing (no completed run of this schema):

- small-4way wrf (MISSING)
- small-4way cam4 (MISSING)
- small-8way cactuBSSN (MISSING)
- small-8way wrf (MISSING)
- small-8way cam4 (MISSING)
