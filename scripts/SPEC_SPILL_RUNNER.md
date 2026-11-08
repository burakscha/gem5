# SPEC spill runner

`spec_spill_runner.sh` runs the available RISC-V SPEC CPU2017 binaries with
the schema-v7 spill detector and keeps per-workload state.

To launch a whole profile without overloading the host, use
`./launch_spill_batch.sh` instead of `start ... all`: it feeds the runner one
benchmark at a time and keeps at most `MAX_JOBS` (default 6) gem5 processes
alive. `start ... all` fires all 17 at once, which is how earlier batches got
OOM-killed on this host.

## Workload profiles

`test` and `train` follow SPEC's own command lines, one run ID per SPEC
invocation (checked against `runcpu --fake` and, under qemu, against SPEC's
expected outputs on 2026-10-08):

- `test`: 35 runs. All 13 `xz` invocations. `perlbench` runs `makerand.pl`
  only: SPEC's `test.pl` forks and execs a new perl for each of its 316 tests,
  which a one-CPU SE-mode gem5 cannot run. `x264` encodes SPEC's test video,
  decoded natively to `BuckBunny_test.yuv`. The six Fortran benchmarks:
  `bwaves` (2 runs), `exchange2`, `fotonik3d`, `roms`, `wrf`, `cam4`
  (ROI patches in `spec_roi/`).
- `train`: 25 runs. Every invocation of `gcc` (3), `nab` (2), `xz` (2) and
  `perlbench` (5); `x264` encodes the train video (`BuckBunny_train.yuv`);
  `xalancbmk` uses SPEC's train stylesheet (`xalanc_train.xsl`). No Fortran
  yet.
- `ref`: 19 runs, not yet checked against SPEC (`x264` still runs the
  decoder, `mcf` the test input, `cactuBSSN` and `parest` train inputs).

A manifest entry's options may end in `< FILE` (the program's standard
input, as in SPEC; passed to se.py as `--input`). An entry with a run
directory (the last field, e.g. `benchmarks/perlbench`) runs in a private copy
of it under the run's outdir, `run/`, with SPEC's own relative arguments and
a relative `argv[0]` (the binary is linked in): small files are copied,
large files and directories linked.

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

### Cache profiles

The CACHE argument is `SIZE` or `SIZE-ORG`. SIZE sets the capacities, ORG the
organisation of L1D and L2; L1I is 32 KiB 2-way in every profile.

| SIZE | L1D | L1I | L2 |
| --- | --- | --- | --- |
| `standard` | 64 KiB | 32 KiB | 2 MiB |
| `small` | 4 KiB | 32 KiB | 32 KiB |

| ORG | L1D | L2 | se.py options |
| --- | --- | --- | --- |
| *(none)* | 2-way | 8-way | se.py defaults, as in all schema-7 runs |
| `2way` | 2-way | 8-way | `--l1d_assoc=2 --l2_assoc=8`: same caches as *(none)*, separate run directories |
| `dm` | direct-mapped | direct-mapped | `--l1d_assoc=1 --l2_assoc=1` |
| `nway` | 8-way | 16-way | `--l1d_assoc=8 --l2_assoc=16` |
| `fa` | fully associative | fully associative | `--l1d_tags=FALRU --l2_tags=FALRU` |

So the six organisation profiles are `standard-dm`, `standard-nway`,
`standard-fa`, `small-dm`, `small-nway` and `small-fa`, e.g.:

```bash
./launch_spill_batch.sh test small-fa
```

All profiles use LRU replacement. Fully associative caches use gem5's FALRU
tag store; a set-associative store with a single set would search every way
(32,768 for the 2 MiB L2) on each access. The `--l*_tags` options are added
in `configs/common/Options.py` and applied in `configs/common/CacheConfig.py`;
`cache_options()` in `spec_spill_runner.sh` maps profile names to options.
gem5 v25.1's FALRU crashed on the first insertion (no tag extractor was
registered on its blocks); `src/mem/cache/tags/fa_lru.cc` and the temp-block
setup in `src/mem/cache/base.cc` carry the fix.

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
