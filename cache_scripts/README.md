# Cache organisation experiment

SPEC CPU2017 workloads under several L1D/L2 organisations with the same small
capacities (L1D 4 KiB = 64 lines, L1I 32 KiB 2-way, L2 32 KiB = 512 lines,
64 B lines, LRU everywhere). The queue is defined in `start_all.sh` (`QUEUE`,
entries `INPUT:CACHE[:RUN,RUN,...]`); it runs the `test` input, then `train`,
each under the configurations below, with x264 (the longest run) started first:

| Config | L1D | L2 | se.py options |
| --- | --- | --- | --- |
| `small-2way` | 2-way, 32 sets × 2 lines | 8-way, 64 sets × 8 lines | `--l1d_assoc=2 --l2_assoc=8` |
| `small-4way` | 4-way, 16 sets × 4 lines | 8-way, 64 sets × 8 lines | `--l1d_assoc=4 --l2_assoc=8` |
| `small-8way` | 8-way, 8 sets × 8 lines | 8-way, 64 sets × 8 lines | `--l1d_assoc=8 --l2_assoc=8` |
| `small-fa` | fully associative, 1 set × 64 lines | fully associative, 1 set × 512 lines | `--l1d_tags=FALRU --l2_tags=FALRU` |
| `small-dm` | direct-mapped, 64 sets × 1 line | direct-mapped, 512 sets × 1 line | `--l1d_assoc=1 --l2_assoc=1` |

One gem5 binary serves all of them: the organisation is a run-time option, not
a build option. At most 8 runs at a time (6 cores / 12 threads, ~8 GB free
memory).

## Scripts

| Script | What it does |
| --- | --- |
| `start_all.sh` | Starts the `QUEUE` as one queue, at most `MAX_JOBS` (8) gem5 runs at a time, in order. Detached, so closing the terminal, Claude Code or the laptop does not stop it. Running it again resumes: running or completed runs are skipped. `--restart` replaces a running queue with the current `QUEUE` (e.g. after adding groups); running gem5 runs continue. |
| `campaign_schema10.sh` | The metric-schema-10 campaign on one host (written for castXeon), under the five small-* configurations: roms (train) and x264 (test) first, then the other test runs, the ref SimPoint points (`simpoint.sh run` with `TOTAL_JOBS`, then combine), the other train runs; at most `TOTAL` gem5 runs at a time. `--dry-run` checks and shows the plan; `start` also runs the spill tests, stops the host's schema-9 runs, moves the schema-9 SimPoint results to `<run>_simpoint_schema9` and starts detached; `status`; `stop --yes`. Running `start` again resumes. Full ref runs are not part of it. |
| `status_cache.sh` | Every status view, chosen by option (output: column and state names in English, notes in Turkish without Turkish letters). No option or `--all`: overview of every queued input and configuration, with the input set named at the top of each section. `--test` / `--train` pick the input of a configuration view (default `--test`). `--2way`, `--8way`, ... (`--<N>way`, L1D N-way and L2 8-way; N a power of two up to 64, anything else is rejected with the reason): one N-way configuration. `--fa`: fully associative. `--dm`: direct-mapped. `--check`: coverage of every input (test, train, ref): per configuration how many runs are completed, running (and on which host), waiting in a queue, in no queue at all (they would never start), or failed, with the lists of the last two. `--info`: cache geometry (size, line size, lines, sets, lines per set, tag store, replacement) from gem5's own `config.ini`. A configuration view shows the geometry, table 1 (state, times, progress estimate, `total_insts/load/store`, `roi_total_insts`, `roi_load`, `roi_store`, `roi_spill_store`, `roi_spill_event`, `roi_spill_load`) table 2 (percentages, with their formulas) and table 3 (cache miss rates: all L1D accesses, spill vs. other loads, spill stores, spill-event stores, unread spill stores and other stores in L1D, local L2 miss rates of all L2 requests, spill loads, spill stores, spill-event stores and unread spill stores). Tables 1 and 2 are the same in every configuration (same program, same instructions); table 3 is where the configurations differ. |
| `smoke_test.sh` | Short trial (5 M instructions) of every workload under each configuration with the runner's exact command line. Shows in minutes whether everything starts; output in `logs/cache_runs/smoke/`, real runs untouched. `RUNS=a,b` and `PROFILE=train` narrow it. |
| `qemu_count.sh INPUT [RUN...]` | Runs each workload to the end under qemu-riscv64 (m5ops patched to NOPs) with the runner's command line and counts its instructions (equal to gem5's `total_insts` to ~0.002%), then estimates the gem5 time (`RATE`, default 0.9 M instructions/s). Minutes instead of days: proves a workload runs through and lets its output be compared with SPEC's. Output in `logs/qemu/INPUT/`. |
| `stop_all.sh --yes` | Stops castdata's queue and every run of its plan on this host. |
| `export_results.py --schema N --input test` | Freezes results into `general_reports/results/schema<N>_<input>_<date>/`: the overview and, per configuration, tables 1-3 as text, one CSV row per configuration and run (counts, ratios, miss rates, raw ROI counters, gem5 cache counts), and a README listing the missing runs. `--schema 8` exports the superseded schema-8 results (also shown by `status_cache.sh --schema 8`). |
| `run_on_host.sh` | The same experiment on another host that mounts `/cta/users` (cast1-3, epic, xeon): `check` (is the host ready: glibc, gem5 libraries, inputs, recommended `--jobs` from free cores and memory), `test` (the 29 spill tests with gem5 there), `smoke INPUT`, `start INPUTS [--configs ...] [--jobs N] [--runs a,b] [--dry-run]` (detached queue, longest runs first by their qemu count; `--runs` limits it to those run IDs), `all INPUTS` (check, test, smoke, start in one go), `status`, `stop --yes`. Queue files in `logs/cache_runs/hosts/<host>/`. |
| `simpoint.sh STAGE INPUT ...` | SimPoint for `ref` (full detailed runs would take months). `profile` (qemu basic block vectors of the ROI, 100M-instruction intervals), `cluster` (SimPoint 3.2, up to 30 points), `summary`, `checkpoint` (gem5 checkpoints of the points made from qemu state dumps by `qemu/ckpt_dump.c` and `qemu/qemu2gem5.py`, laid out in memory as gem5 lays the program out; minutes instead of gem5's weeks of atomic simulation), `run INPUT CONFIGS` (each point restored with TimingSimpleCPU: 500M warmup, 100M measured, into `benchmarks/<bench>/<input>/m5out/<config>/<run>_simpoint/spNN`), `combine` (`simpoint_combine.py`: weighted estimate of the whole ROI written like a full run, linked as `simpoint_<input>_<config>_<run>` next to the `latest_*` links of full runs; `status_cache.sh --ref --simpoint --2way`, `benchmark_reports.py --input ref --simpoint` and `export_results.py --input ref --simpoint` read them), `status`. Full ref runs (no SimPoint) go through the normal queue, e.g. `run_on_host.sh start ref --runs mcf,xz_cld,...`. Output of the first stages in `logs/simpoint/<input>/<run>/`. |

Refresh a view every minute: `watch -n 60 cache_scripts/status_cache.sh --2way`.

The older stack-class and who-evicted-whom tables are switched off for now
(`show_cache_tables()` in `cache_status.py` still builds them).

`cache_status.py` holds the logic behind the status scripts. Queue log:
`logs/cache_runs/queue.log`. Results land where every SPEC run does,
`benchmarks/<bench>/m5out_<bench>/latest_test_<config>_<run>`, so the usual
reports work too:

```bash
./scripts/spill_report.sh --profile test --cache small-fa
```

States: `PENDING` (not started), `RUNNING/pre-ROI` (before m5_work_begin),
`RUNNING/in ROI`, `COMPLETED`, `FAILED`, `INTERRUPTED` (worker died, e.g. a
reboot: run `start_all.sh` again), `STOPPED`.

The status scripts work from any host sharing `/cta/users`. Processes can only
be checked on the host that started the queue (recorded in
`logs/cache_runs/queue.host`); elsewhere the run status files are shown as
written. `start_all.sh` and `stop_all.sh` refuse to run on another host.

## Several hosts

All lab hosts mount `/cta/users`, so one tree serves them all: a host takes
whatever its queue lists, a run started anywhere shows as `RUNNING` on every
host and every other queue skips it. The status script shows every host's
queue and works from any of them. Results do not depend on the host.

```bash
ssh epyc-tailscale                     # or: ssh bkaya@100.97.166.1
cd /cta/users/bkaya/riscv-spec-register-spilling/gem5
cache_scripts/run_on_host.sh check     # changes nothing
cache_scripts/run_on_host.sh all train # check, tests, smoke, then the queue
```
