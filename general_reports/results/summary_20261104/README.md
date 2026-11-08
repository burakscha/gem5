# Status and percentage tables, metric schema 9

Built 2026-11-04 14:45 by `cache_scripts/summary_tables.py`. Only completed runs contribute numbers; rebuild the files at any time.

| set | config | completed | running | pending | other | remaining |
|---|---|---|---|---|---|---|
| test input, full runs | small-2way | 35/35 | 0 | 0 | 0 | 0 |
| test input, full runs | small-fa | 35/35 | 0 | 0 | 0 | 0 |
| test input, full runs | small-dm | 35/35 | 0 | 0 | 0 | 0 |
| test input, full runs | small-4way | 35/35 | 0 | 0 | 0 | 0 |
| test input, full runs | small-8way | 35/35 | 0 | 0 | 0 | 0 |
| train input, full runs | small-2way | 31/32 | 1 | 0 | 0 | 1 |
| train input, full runs | small-fa | 31/32 | 1 | 0 | 0 | 1 |
| train input, full runs | small-dm | 31/32 | 1 | 0 | 0 | 1 |
| train input, full runs | small-4way | 31/32 | 1 | 0 | 0 | 1 |
| train input, full runs | small-8way | 31/32 | 1 | 0 | 0 | 1 |
| ref input, SimPoint estimates | small-2way | 36/36 | 0 | 0 | 0 | 0 |
| ref input, SimPoint estimates | small-fa | 36/36 | 0 | 0 | 0 | 0 |
| ref input, SimPoint estimates | small-dm | 36/36 | 0 | 0 | 0 | 0 |
| ref input, SimPoint estimates | small-4way | 36/36 | 0 | 0 | 0 | 0 |
| ref input, SimPoint estimates | small-8way | 36/36 | 0 | 0 | 0 | 0 |
| ref input, full runs | small-2way | 0/15 | 8 | 7 | 0 | 15 |
| ref input, full runs | small-fa | 0/15 | 8 | 7 | 0 | 15 |
| ref input, full runs | small-dm | 0/15 | 8 | 7 | 0 | 15 |
| ref input, full runs | small-4way | 0/15 | 8 | 7 | 0 | 15 |
| ref input, full runs | small-8way | 0/15 | 8 | 7 | 0 | 15 |

| file | content |
|---|---|
| `spill_tables_20261104.pdf` | every set and configuration in one document: tables and percentages only |
| `<set>_<config>.pdf` | one set and configuration: completion, program percentages, miss rates (`.tex` is the source) |

Detailed reports with counts: `general_reports/results/schema<N>_<input>[_simpoint]_<date>/` (`cache_scripts/export_results.py --pdf`) and per benchmark `benchmarks/<bench>/<input>/report/` (`cache_scripts/benchmark_reports.py`).
