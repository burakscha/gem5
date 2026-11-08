# ref results, metric schema 9

Exported 2026-11-04 14:41 by `cache_scripts/export_results.py --schema 9 --input ref --simpoint`.

These are the current results.

| file | content |
|---|---|
| `overview.txt` | status overview (every queued input and configuration) |
| `ref_small-2way.txt` | small-2way: cache geometry, tables 1-3 |
| `ref_small-fa.txt` | small-fa: cache geometry, tables 1-3 |
| `ref_small-dm.txt` | small-dm: cache geometry, tables 1-3 |
| `ref_small-4way.txt` | small-4way: cache geometry, tables 1-3 |
| `ref_small-8way.txt` | small-8way: cache geometry, tables 1-3 |
| `ref_results.csv` | one row per configuration and run: tables 1-3 (ratios and miss rates in percent, without the sign), raw ROI counters, gem5 cache counts, run directory |
| `ref_report.pdf` | LaTeX report, one page per configuration (`report_<config>/report.tex` is its source) |

Ref values are SimPoint estimates (`cache_scripts/simpoint.sh`): per run up to 30 simulation points of 100M instructions after a 500M-instruction warmup, weighted by SimPoint; every counter is ROI instructions * sum(w_i * c_i / n_i). The points and weights of a run are in its directory's `simpoint.txt`.

Runs: 180 of 180 completed.
