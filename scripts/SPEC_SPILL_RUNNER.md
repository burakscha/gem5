# SPEC spill runner

`spec_spill_runner.sh` runs the available RISC-V SPEC CPU2017 binaries with
the schema-v7 spill detector and keeps per-workload state.

To launch a whole profile without overloading the host, use
`./launch_spill_batch.sh` instead of `start ... all`: it feeds the runner one
benchmark at a time and keeps at most `MAX_JOBS` (default 6) gem5 processes
alive. `start ... all` fires all 17 at once, which is how earlier batches got
OOM-killed on this host.

## Workload profiles

- `test`: 17 jobs. `x264` has no test workload and uses its train bitstream;
  `mcf` uses `inp.in` as the fallback.
- `train`: 18 jobs because `perlbench` has `scrabbl` and `suns` runs.
- `ref`: 19 jobs because `perlbench` has three reference runs. The available
  `cactuBSSN` and `parest` packages use their train inputs as fallbacks.

List every run ID and its actual input:

```bash
./spec_spill_runner.sh list test
./spec_spill_runner.sh list train
./spec_spill_runner.sh list ref
```

## Safe launch sequence

Check the gem5 binary, schema-v7 marker, build freshness, RISC-V binaries,
and input files before spending simulation time:

```bash
./spec_spill_runner.sh check test standard all
```

Launch selected short workloads first:

```bash
./spec_spill_runner.sh start test standard gcc perlbench
```

Launching `all` is explicit because several nominal test workloads still
execute billions of instructions under `TimingSimpleCPU`:

```bash
./spec_spill_runner.sh start test standard all
```

Use `small` instead of `standard` for L1D=4 KiB and L2=32 KiB:

```bash
./spec_spill_runner.sh start test small gcc
```

## Status and control

```bash
./spec_spill_runner.sh status test standard all
./spec_spill_runner.sh log test standard gcc 50
./spec_spill_runner.sh stop test standard gcc
```

States have the following meanings:

- `PENDING`: no run has been launched.
- `STARTING` / `RUNNING`: the worker or gem5 process is active.
- `COMPLETED`: exit code is zero, gem5 statistics are complete, a ROI summary
  exists, and `metric_schema: 7` was found.
- `STOPPED`: stopped through the runner.
- `FAILED`: nonzero exit or a fatal application/simulator message.
- `INVALID_SCHEMA`: spill output is absent or not schema v7.
- `NO_ROI`: the process completed but emitted no ROI summary.
- `INCOMPLETE`: final gem5 statistics are missing.
- `INTERRUPTED`: the recorded worker disappeared without recording a result.

## Results

The single reporting command collects every completed run for a profile/cache,
prints the hit/miss and spill/fill table, and writes `results.csv`,
`report.tex` and the one-page `report.pdf`:

```bash
./spill_report.sh
./spill_report.sh --profile train --cache small
```

To inspect individual runs through the runner instead:

```bash
./spec_spill_runner.sh results test standard gcc
./spec_spill_runner.sh results test standard all
```

Every start creates a timestamped output directory below:

```text
benchmarks/<benchmark>/m5out_<benchmark>/m5out_<run-id>_<HHMM>_<DDMMYYYY>/
```

A `latest_<profile>_<cache>_<run-id>` symlink points to the most recent attempt for
that combination; each run also records its profile, cache, run id and
benchmark under `.runner/`. Each run records its
gem5 Git commit, PIDs, timestamps, exit code, exact command, `nohup.log`,
`stats.txt`, and `riscv_spill_stats.txt`. Existing results are never deleted.
