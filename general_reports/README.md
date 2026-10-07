# General reports

Everything that is *not* tied to a single benchmark. Per-benchmark simulation
output stays where it is produced, under
`benchmarks/<bench>/m5out_<bench>/m5out_<run_id>_<HHMM>_<DDMMYYYY>/`.

| Directory | Contents |
| --- | --- |
| `definitions/` | Methodology documents. `spill_definition.tex` / `.pdf` is the executive summary of how a spill is defined and measured — the rule sets and the counter definitions. |
| `results/` | Cross-benchmark result reports produced by `./scripts/spill_report.sh`: one directory per profile/cache/date with `results.csv`, `report.tex` and the one-page `report.pdf`. |
| `notes/` | Working notes kept from earlier experiment rounds. |

Superseded material from earlier metric schemas lives in `ARCHIVED/` at the
repository root, not here. Its counter names (`roi_spills`,
`roi_candidate_*`, …) were retired in schema 5 and its numbers must not be
compared with current results.

## Rebuilding a document

```bash
# Definition report
tectonic --outdir general_reports/definitions \
    general_reports/definitions/spill_definition.tex

# Result report (regenerates the table from the completed runs)
./scripts/spill_report.sh
```
