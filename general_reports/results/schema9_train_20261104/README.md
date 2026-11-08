# train results, metric schema 9

Exported 2026-11-04 14:40 by `cache_scripts/export_results.py --schema 9 --input train`.

These are the current results.

| file | content |
|---|---|
| `overview.txt` | status overview (every queued input and configuration) |
| `train_small-2way.txt` | small-2way: cache geometry, tables 1-3 |
| `train_small-fa.txt` | small-fa: cache geometry, tables 1-3 |
| `train_small-dm.txt` | small-dm: cache geometry, tables 1-3 |
| `train_small-4way.txt` | small-4way: cache geometry, tables 1-3 |
| `train_small-8way.txt` | small-8way: cache geometry, tables 1-3 |
| `train_results.csv` | one row per configuration and run: tables 1-3 (ratios and miss rates in percent, without the sign), raw ROI counters, gem5 cache counts, run directory |
| `train_report.pdf` | LaTeX report, one page per configuration (`report_<config>/report.tex` is its source) |

Runs: 155 of 160 completed.

Missing (no completed run of this schema):

- small-2way roms (RUNNING)
- small-fa roms (RUNNING)
- small-dm roms (RUNNING)
- small-4way roms (RUNNING)
- small-8way roms (RUNNING)
