# Scripts

Every script for building gem5, running the SPEC CPU2017 spill experiments and
reporting on them. All of them work out of the repository root and can be
called from there:

```bash
./scripts/<name>
```

| Script | Purpose |
| --- | --- |
| `build_gem5_riscv.sh` | Build `build/RISCV/gem5.opt` through the conda toolchain shim. `--clean` rebuilds from scratch. |
| `spec_spill_runner.sh` | Run and track individual SPEC workloads. Owns the workload manifest and the per-run state machine. |
| `launch_spill_batch.sh` | Launch a whole profile through the runner while capping concurrency. **Use this instead of `spec_spill_runner.sh start ... all`.** |
| `spill_report.sh` | One command: collect every completed run, print the table, write CSV + LaTeX + PDF. |
| `spill_report.py` | The reporting engine behind `spill_report.sh`. Can also analyse individual output directories. |
| `spill_table.sh` | Numbered per-benchmark table: instruction and spill counts, the spill ratios against both the ROI and the whole run, and L1/L2/DRAM behaviour. `--csv` also writes a CSV, `--wide` adds the raw cache counts. |

`SPEC_SPILL_RUNNER.md` documents the runner's workload profiles, states and
per-run directory layout in detail.

## Typical session

```bash
# 1. Build (only after changing the detector or the cache model)
./scripts/build_gem5_riscv.sh

# 2. Check that binaries and inputs are in place
./scripts/spec_spill_runner.sh check test standard all

# 3. Launch the whole profile, at most MAX_JOBS (default 6) at a time
setsid nohup ./scripts/launch_spill_batch.sh test standard \
    > logs/batch_test_standard.log 2>&1 < /dev/null &

# 4. Watch progress
./scripts/spec_spill_runner.sh status test standard all

# 5. Report once the runs are COMPLETED
./scripts/spill_table.sh          # numbered table of counts and ratios
./scripts/spill_report.sh         # table + CSV + LaTeX + one-page PDF
```

## Concurrency and memory

`launch_spill_batch.sh` keeps at most `MAX_JOBS` gem5 processes alive
(default 6, override with the environment variable). This matters on this
host: 12 cores, 32 GB of RAM, no swap, and a ZFS ARC that holds roughly half
of memory, which leaves about 7-9 GB actually available. Starting all 17
workloads at once has caused OOM kills before.

## Where the output goes

| Path | Contents |
| --- | --- |
| `benchmarks/<bench>/` | The benchmark binary and its input files. |
| `benchmarks/<bench>/m5out_<bench>/m5out_<run_id>_<HHMM>_<DDMMYYYY>/` | One simulation run: `stats.txt`, `riscv_spill_stats.txt`, `nohup.log` and the `.runner/` state directory. Existing results are never overwritten. |
| `benchmarks/<bench>/m5out_<bench>/latest_<profile>_<cache>_<run_id>` | Symlink to that combination's most recent run. |
| `benchmarks/<bench>/reports/` | Per-benchmark analysis documents. |
| `general_reports/results/` | Cross-benchmark result reports: table CSV, LaTeX source and one-page PDF. |
| `general_reports/definitions/` | Methodology documents, e.g. the spill definition executive summary. |
| `ARCHIVED/` | Results and reports from earlier metric schemas. Not comparable with current numbers. |
| `logs/` | Batch launcher logs. |
