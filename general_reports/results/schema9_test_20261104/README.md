# test results, metric schema 9

Exported 2026-11-04 14:40 by `cache_scripts/export_results.py --schema 9 --input test`.

These are the current results.

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

Runs: 175 of 175 completed.
