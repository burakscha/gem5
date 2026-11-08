#!/usr/bin/env python3
"""Status of the cache-organisation SPEC experiment.

Three L1D/L2 organisations, same small capacities (L1D 4 KiB, L1I 32 KiB,
L2 32 KiB, 64 B lines), every SPEC workload of the `test` input profile:

    small-2way  L1D 2-way, L2 8-way
    small-fa    L1D and L2 fully associative (FALRU)
    small-dm    L1D and L2 direct-mapped

usage (cache_scripts/status_cache.sh passes its options through):
    --all            overview of every queued input and configuration (default)
    --info           cache geometry of the queued configurations
    --2way, --8way   one N-way configuration: L1D N-way, L2 8-way
    --fa             fully associative L1D and L2 (FALRU)
    --dm             direct-mapped L1D and L2
    --test, --train, --ref  input set of a configuration view (default --test)
    --simpoint       with --ref: the SimPoint estimates (cache_scripts/simpoint.sh,
                     links simpoint_ref_<config>_<run>) instead of full ref runs
    --check          coverage of every input: per configuration how many runs
                     are completed, running (on which host), waiting in a
                     queue, in no queue at all (they will never start), or
                     failed; then the lists of the last two
    --schema N       results of an older metric schema (e.g. 8) instead of the
                     current one: each run's newest completed run of that
                     schema, found in its run directories (works with every
                     view above)

Cache geometry is read from the config.ini gem5 itself wrote, so it shows
what was actually simulated (sets, ways, tag store, replacement policy).
"""

from __future__ import annotations

import configparser
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "spec_spill_runner.sh"
GEM5 = ROOT / "build" / "RISCV" / "gem5.opt"
LOGDIR = ROOT / "logs" / "cache_runs"
PROFILE = "test"        # input set being shown; main() sets it
INPUT_DESC = {"test": "SPEC CPU2017 'test' inputs, the smallest set",
              "train": "SPEC CPU2017 'train' inputs, the medium set",
              "ref": "SPEC CPU2017 'ref' inputs, the largest set"}
# start_all.sh writes the queue's (input, cache) groups here, in queue order.
PLAN = LOGDIR / "queue.plan"
DEFAULT_PLAN = [("test", "small-2way"), ("test", "small-fa"),
                ("test", "small-dm")]
# Every configuration of the experiment (ref has no queue: SimPoint runs).
ALL_CONFIGS = ["small-2way", "small-fa", "small-dm", "small-4way", "small-8way"]
CACHES = [("L1I", "system.cpu.icache"), ("L1D", "system.cpu.dcache"), ##
          ("L2", "system.l2")]

INT_FIELD = re.compile(r"^#\s+([A-Za-z0-9_]+)\s*:\s*([0-9]+)")
STAT_LINE = re.compile(r"^(\S+)\s+([-+0-9.eE]+)(?:\s|$)")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def num(value) -> str:
    return "-" if value is None else f"{value:,}"


def pct(part, whole) -> str:
    """Percentage with its sign: 18.45% means 18.45 of every 100."""
    return "-" if part is None or not whole else f"{100.0 * part / whole:.2f}%"


def duration(seconds) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d{hours:02d}h{minutes:02d}m"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{seconds % 60:02d}s"


def stamp(epoch) -> str:
    return "-" if epoch is None else datetime.fromtimestamp(epoch).strftime(
        "%m-%d %H:%M")


def table(header: list[str], rows: list[list[str]], left: int = 1) -> str:
    widths = [max(len(str(c)) for c in col) for col in zip(header, *rows)]
    def line(cells):
        return "  ".join(str(c).ljust(w) if i < left else str(c).rjust(w)
                         for i, (c, w) in enumerate(zip(cells, widths)))
    rule = "  ".join("-" * w for w in widths)
    return "\n".join([line(header), rule, *(line(r) for r in rows)])


# --------------------------------------------------------------------------
# Runs and their files
# --------------------------------------------------------------------------
def queue_dirs() -> list[Path]:
    """Queue state of every host: start_all.sh writes logs/cache_runs/queue.*,
    cache_scripts/run_on_host.sh writes logs/cache_runs/hosts/<host>/queue.*."""
    hosts = LOGDIR / "hosts"
    extra = sorted(d for d in hosts.iterdir() if d.is_dir()) if hosts.is_dir() else []
    return [LOGDIR, *extra]


def plan() -> list[tuple[str, str, set[str] | None]]:
    """(input, cache, run IDs or None for all) per queued group, in order,
    merged over the queues of every host."""
    merged: dict[tuple[str, str], set[str] | None] = {}
    for qdir in queue_dirs():
        for line in read(qdir / "queue.plan").splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            key = (fields[0], fields[1])
            runs = set(fields[2].split(",")) if len(fields) > 2 else None
            if key not in merged:
                merged[key] = runs
            elif merged[key] is not None:
                merged[key] = None if runs is None else merged[key] | runs
    groups = [(p, c, r) for (p, c), r in merged.items()]
    return groups or [(p, c, None) for p, c in DEFAULT_PLAN]


def planned_caches(profile: str) -> list[str]:
    return [cache for p, cache, _ in plan() if p == profile]


def planned_runs(profile: str) -> set[str] | None:
    """Run IDs queued for an input set; None when a group takes them all."""
    selections = [runs for p, _, runs in plan() if p == profile]
    if not selections or any(runs is None for runs in selections):
        return None
    return set().union(*selections)


def input_line() -> str:
    line = f"Input: {PROFILE}  ({INPUT_DESC.get(PROFILE, PROFILE)})"
    if SIMPOINT:
        line += "   [SimPoint estimates, cache_scripts/simpoint.sh]"
    if SCHEMA != CURRENT_SCHEMA:
        line += (f"   [metric schema {SCHEMA} results: superseded, the current "
                 f"detector writes schema {CURRENT_SCHEMA}]")
    return line


def workloads() -> list[tuple[str, str]]:
    out = subprocess.run([str(RUNNER), "list", PROFILE], capture_output=True,
                         text=True, check=True).stdout.splitlines()
    runs = [tuple(line.split()[:2]) for line in out[2:] if line.strip()]
    # The queue plan selects full runs only; simpoint.sh covers every run.
    wanted = None if SIMPOINT else planned_runs(PROFILE)
    return [r for r in runs if wanted is None or r[0] in wanted]


_ARCHIVE: dict[tuple[str, bool], dict[tuple[str, str, str], Path]] = {}


def archived_runs(benchmark: str) -> dict[tuple[str, str, str], Path]:
    """(input, cache, run ID) -> newest completed run of schema SCHEMA, from
    every run directory of the benchmark (the latest_* links follow the
    newest run, which may be of the current schema). With SIMPOINT, the
    combined SimPoint estimates (<run>_simpoint, and <run>_simpoint_schema9
    where a campaign moved an older one aside) instead of the full runs."""
    if (benchmark, SIMPOINT) not in _ARCHIVE:
        best: dict[tuple[str, str, str], tuple[int, Path]] = {}
        bench = ROOT / "benchmarks" / benchmark
        # Runs before 2026-10-15: m5out_<bench>/m5out_*; since then
        # <input>/m5out/<cache>/<run_id>_<stamp> (SimPoint: <run_id>_simpoint).
        dirs = [*bench.glob(f"m5out_{benchmark}/m5out_*"), *bench.glob("*/m5out/*/*")]
        for d in dirs:
            if d.is_symlink() or not d.is_dir():
                continue
            r = d / ".runner"
            if (r / "simpoint").exists() != SIMPOINT:
                continue
            if read(r / "status") != "COMPLETED" or run_schema(d) != SCHEMA:
                continue
            # A combined SimPoint directory names its input and cache only
            # through its path: <input>/m5out/<cache>/<run>_simpoint*.
            key = (read(r / "profile") or d.parent.parent.parent.name,
                   read(r / "cache") or d.parent.name, read(r / "run_id"))
            end = read(r / "finished.epoch")
            end = int(end) if end.isdigit() else 0
            if key not in best or end > best[key][0]:
                best[key] = (end, d)
        _ARCHIVE[(benchmark, SIMPOINT)] = {k: v[1] for k, v in best.items()}
    return _ARCHIVE[(benchmark, SIMPOINT)]


def dir_schema(d: Path) -> int | None:
    """Metric schema of a run: its result, or for an unfinished run the gem5
    build it was started with (schema 10 has its own build directory)."""
    schema = run_schema(d)
    if schema is not None:
        return schema
    command = read(d / ".runner" / "command.sh")
    if not command:
        return None
    return 10 if "/build/RISCV_SCHEMA10/" in command else 9


def run_dir(cache: str, run_id: str, benchmark: str) -> Path | None:
    link = (ROOT / "benchmarks" / benchmark / f"m5out_{benchmark}" /
            f"{'simpoint' if SIMPOINT else 'latest'}_{PROFILE}_{cache}_{run_id}")
    target = link.resolve() if link.exists() else None
    if SCHEMA == CURRENT_SCHEMA:
        return target
    # An older schema: the linked run if it is of that schema (still the
    # newest, or running with that build), else the newest archived result.
    if target is not None and dir_schema(target) == SCHEMA:
        return target
    return archived_runs(benchmark).get((PROFILE, cache, run_id))


def pid_alive(pid: str) -> bool:
    if not pid.isdigit():
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


HERE = socket.gethostname()


def run_host(d: Path) -> str:
    """Host a run executes on. /cta/users is shared between machines, and a
    PID can only be checked on the machine that owns it."""
    return read(d / ".runner" / "host") or read(LOGDIR / "queue.host") or HERE


SIMPOINT = False     # --simpoint: SimPoint estimates instead of full runs
CURRENT_SCHEMA = 10  # metric schema of the current gem5 build
SCHEMA = CURRENT_SCHEMA   # schema shown; --schema N picks an older one
SCHEMA_LINE = re.compile(r"^# metric_schema\s*:\s*(\d+)", re.MULTILINE)


def run_schema(d: Path) -> int | None:
    try:
        with (d / "riscv_spill_stats.txt").open() as f:
            m = SCHEMA_LINE.search(f.read(4096))
    except OSError:
        return None
    return int(m.group(1)) if m else None


def run_state(d: Path | None) -> str:
    if d is None:
        return "PENDING" if SCHEMA == CURRENT_SCHEMA else "MISSING"
    state = read(d / ".runner" / "status") or "UNKNOWN"
    if state == "RUNNING" and run_host(d) == HERE and \
            not pid_alive(read(d / ".runner" / "worker.pid")):
        return "INTERRUPTED"
    # A result of an older detector schema is not comparable with current
    # ones; the queue runs it again.
    if state == "COMPLETED" and run_schema(d) != SCHEMA:
        return "OLD_SCHEMA"
    return state


def run_times(d: Path | None) -> tuple[int | None, int | None]:
    if d is None:
        return None, None
    start = read(d / ".runner" / "started.epoch")
    end = read(d / ".runner" / "finished.epoch")
    return (int(start) if start.isdigit() else None,
            int(end) if end.isdigit() else None)


def phase(d: Path) -> str:
    """Where a running simulation is: workbegin/workend each dump stats."""
    try:
        blocks = (d / "stats.txt").read_text().count("Begin Simulation Statistics")
    except OSError:
        blocks = 0
    return {0: "pre-ROI", 1: "in ROI"}.get(blocks, "after ROI")


# Canonical ROI counter names (general_reports/action_plan/COUNTER_NAMING.md)
# and the older summaries they are read from by canonical():
#   schema 10 of 2026-11-05..08, recognized by roi_stack_store: the spill
#     stores were called roi_stack_store, the spill events roi_spill_event
#     (11-08) or roi_spill_store (11-05..07);
#   schema 9 (and schema 10 before 11-05), through CANONICAL: spill_store,
#     spill_load, stack_store. Schema 9 keeps its own meaning: spill_store are
#     the compiler-labelled spill stores, read back or not, spill_event those
#     read back, stack_store the sp/s0-based stores (roi_stack_store).
_TALLY = ("l1_hits", "l1_misses", "l2_hits", "l2_misses", "split_insts")
CANONICAL = {"roi_stack_store": "stack_store", "roi_spill_store": "spill_store",
             "roi_spill_load": "spill_load"}
CANONICAL.update({f"roi_{p}_{f}": f"{p}_{f}"
                  for p in ("stack_store", "spill_store", "spill_load") for f in _TALLY})


def canonical(roi: dict[str, int]) -> None:
    """Adds the canonical names to one ROI summary of an older format."""
    if "roi_stack_store" in roi:         # schema 10 of 2026-11-05..08
        events = "roi_spill_event" if "roi_spill_event" in roi else "roi_spill_store"
        renamed = {"roi_spill_store": roi["roi_stack_store"], "roi_spill_event": roi[events]}
        for f in _TALLY:
            renamed[f"roi_spill_store_{f}"] = roi.get(f"roi_stack_store_{f}", 0)
            renamed[f"roi_spill_event_{f}"] = roi.get(f"{events}_{f}", 0)
        if "diag_store_first_reload_after_stack_release" in roi:
            renamed["diag_event_after_stack_release"] = roi[
                "diag_store_first_reload_after_stack_release"]
        for k in [k for k in roi if k.startswith("roi_stack_store")]:
            del roi[k]
        roi.update(renamed)
        return
    for new, old in CANONICAL.items():
        if new not in roi and old in roi:
            roi[new] = roi[old]


def spill_log(d: Path | None) -> tuple[dict[str, int], dict[str, int]]:
    """(ROI counters summed over ROIs, GLOBAL SUMMARY counters); the ROI
    counters also under their canonical names."""
    roi: dict[str, int] = {}
    glob: dict[str, int] = {}
    if d is None:
        return roi, glob
    current = None
    try:
        lines = (d / "riscv_spill_stats.txt").read_text().splitlines()
    except OSError:
        return roi, glob
    for line in lines:
        if line.startswith("# ROI SUMMARY"):
            current = roi
        elif line.startswith("# GLOBAL SUMMARY"):
            current = glob
        else:
            m = INT_FIELD.match(line)
            if m and current is not None:
                current[m.group(1)] = current.get(m.group(1), 0) + int(m.group(2))
    canonical(roi)
    return roi, glob


def roi_stats(d: Path | None) -> dict[str, float]:
    """gem5 statistics of the ROI block(s): odd blocks of a 2N+1 layout."""
    if d is None:
        return {}
    blocks: list[dict[str, float]] = []
    try:
        for line in (d / "stats.txt").read_text().splitlines():
            if "Begin Simulation Statistics" in line:
                blocks.append({})
            elif blocks:
                m = STAT_LINE.match(line)
                if m:
                    try:
                        blocks[-1][m.group(1)] = float(m.group(2))
                    except ValueError:
                        pass
    except OSError:
        return {}
    if len(blocks) == 2:
        # A SimPoint interval run: warmup block, then the interval (ROI).
        return dict(blocks[1])
    if len(blocks) < 3 or len(blocks) % 2 == 0:
        return {}
    merged: dict[str, float] = {}
    for block in blocks[1::2]:
        for key, value in block.items():
            merged[key] = merged.get(key, 0.0) + value
    return merged


# --------------------------------------------------------------------------
# Cache geometry from gem5's own config.ini
# --------------------------------------------------------------------------
def cache_options(cache: str) -> list[str]:
    script = (f'source <(sed -n "/^cache_options() {{/,/^}}/p" "{RUNNER}"); '
              f'cache_options "{cache}"')
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True, check=True).stdout
    return out.split()


def config_ini(cache: str, runs: list[tuple[str, str]]) -> tuple[Path, str]:
    """config.ini of a real run of this cache if one exists, otherwise of an
    --initialize-only instantiation (no simulation, a fraction of a second)."""
    for run_id, benchmark in runs:
        d = run_dir(cache, run_id, benchmark)
        if d and (d / "config.ini").is_file():
            return d / "config.ini", f"config.ini of the {run_id} run"
    outdir = LOGDIR / "geometry" / cache
    ini = outdir / "config.ini"
    if not ini.is_file():
        outdir.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(GEM5), f"--outdir={outdir}",
                        str(ROOT / "configs/deprecated/example/se.py"),
                        f"--cmd={ROOT}/tests/test-progs/hello/bin/riscv/linux/hello",
                        *cache_options(cache), "--initialize-only"],
                       capture_output=True, check=False)
    return ini, "config.ini from gem5 --initialize-only"


def geometry(cache: str, runs) -> tuple[list[list[str]], str]:
    ini, source = config_ini(cache, runs)
    cfg = configparser.ConfigParser(strict=False, interpolation=None)
    cfg.read(ini)
    if "system" not in cfg:
        return [], f"cannot read {ini}"
    line = int(cfg["system"]["cache_line_size"])
    rows = []
    for label, sec in CACHES:
        size = int(cfg[sec]["size"])
        lines = size // line
        tags = cfg[f"{sec}.tags"]["type"]
        if tags == "FALRU":
            sets, ways, policy = 1, lines, "LRU (FALRU)"
        else:
            ways = int(cfg[sec]["assoc"])
            sets = lines // ways
            policy = cfg[f"{sec}.replacement_policy"]["type"].replace("RP", "")
        organisation = ("fully associative" if sets == 1 else
                        "direct-mapped" if ways == 1 else f"{ways}-way")
        unit = f"{size // 1048576} MiB" if size >= 1048576 else f"{size // 1024} KiB"
        rows.append([label, unit, f"{line} B", f"{lines:,}", organisation,
                     f"{sets:,}", f"{ways:,}", tags, policy])
    return rows, source


GEOMETRY_HEADER = ["cache", "size", "line", "lines", "organisation", "sets",
                   "lines/set", "tag store", "replacement"]


def state_text(r: dict) -> str:
    return f"{r['state']} ({r['phase']})" if r["phase"] else r["state"]


# --------------------------------------------------------------------------
# Progress estimate for running runs
# --------------------------------------------------------------------------
def finished_duration(d: Path | None) -> int | None:
    # An older-schema run of the same workload is as good a time reference.
    if d is None or run_state(d) not in ("COMPLETED", "OLD_SCHEMA"):
        return None
    start, end = run_times(d)
    return end - start if start and end else None


def run_binary(d: Path | None) -> str | None:
    """The guest binary (--cmd=) a run executed, from its saved command."""
    m = re.search(r"--cmd=(\S+)", read(d / ".runner" / "command.sh")) if d else None
    return os.path.basename(m.group(1)) if m else None


def reference(cache: str, run_id: str, benchmark: str):
    """How long this workload took before: in another configuration of this
    experiment if one finished, else in the earlier standard-cache test run.
    A run of a different binary does not count (the old x264 test run was
    ldecod_r, not x264_r)."""
    binary = run_binary(run_dir(cache, run_id, benchmark))
    for other in planned_caches(PROFILE) + ["standard"]:
        if other == cache:
            continue
        d = run_dir(other, run_id, benchmark)
        seconds = finished_duration(d)
        if seconds and run_binary(d) == binary:
            return seconds, other
    return None, None


def progress(r: dict) -> str:
    if r["state"] == "COMPLETED":
        return "100%"
    if r["state"] != "RUNNING" or r["elapsed"] is None or not r["ref"]:
        return "-"
    share = 100.0 * r["elapsed"] / r["ref"]
    return f"~{share:.0f}%" if share < 100 else f">100% (ref {duration(r['ref'])})"


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------
def run_record(cache: str, run_id: str, benchmark: str) -> dict:
    d = run_dir(cache, run_id, benchmark)
    state = run_state(d)
    start, end = run_times(d)
    now = int(time.time())
    elapsed = None if start is None else (end or now) - start
    roi, glob = spill_log(d) if state in ("COMPLETED", "FAILED", "STOPPED") else ({}, {})
    stats = roi_stats(d) if roi else {}
    l1d_h = stats.get("system.cpu.dcache.demandHits::total")
    l1d_m = stats.get("system.cpu.dcache.demandMisses::total")
    l2_h = stats.get("system.l2.demandHits::total")
    l2_m = stats.get("system.l2.demandMisses::total")
    sl_h, sl_m = roi.get("roi_spill_load_l1_hits"), roi.get("roi_spill_load_l1_misses")
    ref, ref_source = (reference(cache, run_id, benchmark) if state == "RUNNING"
                       else (None, None))
    return {
        "stats": stats,
        "run_id": run_id, "benchmark": benchmark, "dir": d, "state": state,
        "phase": phase(d) if state == "RUNNING" and d else "",
        "start": start, "end": end, "elapsed": elapsed, "roi": roi,
        "glob": glob, "ref": ref, "ref_source": ref_source,
        "l1d_miss": pct(l1d_m, (l1d_h or 0) + (l1d_m or 0)) if stats else "-",
        "l2_miss": pct(l2_m, (l2_h or 0) + (l2_m or 0)) if stats else "-",
        "spill_ld_miss": pct(sl_m, (sl_h or 0) + (sl_m or 0)) if roi else "-",
    }


def counts(r: dict) -> dict:
    """The instruction counts of one run, under the canonical names (see
    canonical()), and the differences the ratios use: spill stores never
    read back and stores that are not spill stores. Schema 9 results carry
    the compiler-map spill class under the same names: roi_spill_store
    (labelled stores, read back or not) and roi_spill_event (those read
    back)."""
    g, roi = r["glob"], r["roi"]
    c = {k: g.get(k) for k in ("total_insts", "total_load", "total_store")}
    c.update({k: roi.get(k) for k in ("roi_total_insts", "roi_load", "roi_store",
                                      "roi_spill_store", "roi_spill_load",
                                      "roi_stack_store")})
    c["roi_spill_event"] = roi.get("roi_spill_event", roi.get("spill_event"))

    def diff(a, b, sign=1):
        return None if c[a] is None or c[b] is None else c[a] + sign * c[b]

    c["roi_spill_insts"] = diff("roi_spill_load", "roi_spill_store")
    c["roi_total_mem"] = diff("roi_load", "roi_store")
    c["roi_unread_spill_store"] = diff("roi_spill_store", "roi_spill_event", -1)
    c["roi_non_spill_store"] = diff("roi_store", "roi_spill_store", -1)
    return c


PROGRESS_NOTE = [
    "progress        = estimate: elapsed time / the same benchmark's earlier run time (another",
    "                  configuration of this experiment if one finished, else the earlier standard-cache",
    "                  run). Smaller caches can run longer; above 100% means slower than the reference.",
]
COUNT_COLUMNS_10 = ["total_insts", "total_load", "total_store", "roi_total_insts", "roi_load",
                    "roi_store", "roi_spill_store", "roi_spill_event", "roi_spill_load"]
COUNT_NOTES_10 = [
    "total_*         = the whole simulation: all instructions, loads, stores",
    "roi_*           = only between m5_work_begin/end (SimPoint: the interval)",
    "roi_spill_store = stores meeting the store conditions of a spill (inside the ROI, to the",
    "                  stack, not atomic), read back or not",
    "roi_spill_event = distinct spill stores read back at least once inside the ROI: one event per",
    "                  store, at its first reload",
    "roi_spill_load  = loads that read a spill store back (repeats included, so it can exceed",
    "                  roi_spill_event)",
    "Detection: runtime effective addresses only, store and reload inside the ROI (metric schema",
    "10); an operational definition, not necessarily compiler-generated spill code.",
    *PROGRESS_NOTE,
]
COUNT_COLUMNS_9 = ["total_insts", "total_load", "total_store", "roi_total_insts", "roi_load",
                   "roi_store", "roi_spill_event", "roi_spill_load", "roi_spill_store",
                   "roi_stack_store"]
COUNT_NOTES_9 = [
    "total_*         = the whole simulation: all instructions, loads, stores",
    "roi_*           = only between m5_work_begin/end",
    "roi_spill_event = spill events: one spill store + its first reload",
    "roi_spill_load  = spill loads (repeats included, so it can exceed roi_spill_event)",
    "roi_spill_store = compiler-labelled spill stores, read back or not",
    "roi_stack_store = sp/s0-based stores",
    "Schema 9: spill = the compiler-map (GCC -dP) spill class.",
    *PROGRESS_NOTE,
]
# header, numerator, denominator
RATIOS_10 = [
    ("roi/total", "roi_total_insts", "total_insts"),
    ("load/roi", "roi_load", "roi_total_insts"),
    ("store/roi", "roi_store", "roi_total_insts"),
    ("spill/roi", "roi_spill_insts", "roi_total_insts"),
    ("spill_load/load", "roi_spill_load", "roi_load"),
    ("spill_store/store", "roi_spill_store", "roi_store"),
    ("spill_event/store", "roi_spill_event", "roi_store"),
    ("spill_event/spill_store", "roi_spill_event", "roi_spill_store"),
    ("spill/mem", "roi_spill_insts", "roi_total_mem"),
]
RATIO_FORMULAS_10 = [
    ("roi/total", "(roi_total_insts / total_insts) * 100",
     "komutlarin yuzde kaci ROI icinde"),
    ("load/roi", "(roi_load / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci load"),
    ("store/roi", "(roi_store / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci store"),
    ("spill/roi", "((roi_spill_load + roi_spill_store) / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci spill load veya spill store"),
    ("spill_load/load", "(roi_spill_load / roi_load) * 100",
     "ROI load'larinin yuzde kaci spill load"),
    ("spill_store/store", "(roi_spill_store / roi_store) * 100",
     "ROI store'larinin yuzde kaci spill store (geri okunsun okunmasin)"),
    ("spill_event/store", "(roi_spill_event / roi_store) * 100",
     "ROI store'larinin yuzde kaci geri okunan spill store (spill event)"),
    ("spill_event/spill_store", "(roi_spill_event / roi_spill_store) * 100",
     "spill store'larin yuzde kaci ROI icinde geri okundu"),
    ("spill/mem", "((roi_spill_load + roi_spill_store) / (roi_load + roi_store)) * 100",
     "bellek komutlarinin (load + store) yuzde kaci spill load veya spill store"),
]
RATIOS_9 = [
    ("roi/total", "roi_total_insts", "total_insts"),
    ("load/roi", "roi_load", "roi_total_insts"),
    ("store/roi", "roi_store", "roi_total_insts"),
    ("spill/roi", "roi_spill_insts", "roi_total_insts"),
    ("spill_load/roi", "roi_spill_load", "roi_total_insts"),
    ("spill_store/roi", "roi_spill_store", "roi_total_insts"),
    ("spill_load/load", "roi_spill_load", "roi_load"),
    ("spill_store/store", "roi_spill_store", "roi_store"),
    ("spill/mem", "roi_spill_insts", "roi_total_mem"),
    ("stack_store/store", "roi_stack_store", "roi_store"),
    ("spill_store/stack_store", "roi_spill_store", "roi_stack_store"),
]
RATIO_FORMULAS_9 = [
    ("roi/total", "(roi_total_insts / total_insts) * 100",
     "komutlarin yuzde kaci ROI icinde"),
    ("load/roi", "(roi_load / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci load"),
    ("store/roi", "(roi_store / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci store"),
    ("spill/roi", "((roi_spill_load + roi_spill_store) / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci spill kaynakli (load + store)"),
    ("spill_load/roi", "(roi_spill_load / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci spill kaynakli load"),
    ("spill_store/roi", "(roi_spill_store / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci spill kaynakli store"),
    ("spill_load/load", "(roi_spill_load / roi_load) * 100",
     "ROI load'larinin yuzde kaci spill kaynakli"),
    ("spill_store/store", "(roi_spill_store / roi_store) * 100",
     "ROI store'larinin yuzde kaci spill kaynakli"),
    ("spill/mem", "((roi_spill_load + roi_spill_store) / (roi_load + roi_store)) * 100",
     "bellek komutlarinin (load + store) yuzde kaci spill"),
    ("stack_store/store", "(roi_stack_store / roi_store) * 100",
     "ROI store'larinin yuzde kaci stack'e yaziyor"),
    ("spill_store/stack_store", "(roi_spill_store / roi_stack_store) * 100",
     "stack store'larinin yuzde kaci ROI icinde geri okundu"),
]


def ratio_notes(formulas) -> list[str]:
    w1 = max(len(n) for n, _, _ in formulas)
    w2 = max(len(f) for _, f, _ in formulas)
    return (["All values are percentages: 18.45% = 18.45 of every 100 (a ratio of 0.1845)."] +
            [f"{n.ljust(w1)} = {f.ljust(w2)}   {m}" for n, f, m in formulas])


L1D, L2 = "system.cpu.dcache", "system.l2"
MISS_COLUMNS_10 = ["L1D_miss", "spill_ld_L1miss", "other_ld_L1miss", "spill_st_L1miss",
                   "spill_event_L1miss", "unread_st_L1miss", "other_st_L1miss", "L2_local_miss",
                   "spill_ld_L2local", "spill_st_L2local", "spill_event_L2local",
                   "unread_st_L2local"]
MISS_COLUMNS_9 = ["L1D_miss", "spill_ld_L1miss", "other_ld_L1miss",
                  "spill_st_L1miss", "other_st_L1miss", "stack_st_L1miss", "L2_miss",
                  "spill_ld_L2miss", "spill_st_L2miss", "stack_st_L2miss"]


def miss_fractions(r: dict) -> dict[str, tuple[float, float]]:
    """Every miss rate of one run's ROI as (misses, accesses), so that runs
    can be pooled. Spill and stack-store counts come from the detector (spill
    loads and stack stores equal gem5's spillLoad*/stackStore*; the spill
    stores are known to the detector only), the rest from the ROI block of
    stats.txt. Counted per cache access; an L2 rate is local: its accesses
    are the L1D misses of that kind."""
    st, roi = r["stats"], r["roi"]
    g = lambda name: st.get(name, 0.0)
    v = lambda name: roi.get(name, 0)

    def l1(population):
        p = f"roi_{population}"
        return v(f"{p}_l1_misses"), v(f"{p}_l1_hits") + v(f"{p}_l1_misses")

    def l2(population):
        p = f"roi_{population}"
        return v(f"{p}_l2_misses"), v(f"{p}_l2_hits") + v(f"{p}_l2_misses")

    def gem5(req):
        return g(f"{L1D}.{req}.misses::total"), g(f"{L1D}.{req}.accesses::total")

    def minus(a, b):
        return a[0] - b[0], a[1] - b[1]

    out = {"L1D_miss": (g(f"{L1D}.demandMisses::total"), g(f"{L1D}.demandAccesses::total"))}
    out["L2_miss"] = out["L2_local_miss"] = (
        g(f"{L2}.demandMisses::total"),
        g(f"{L2}.demandHits::total") + g(f"{L2}.demandMisses::total"))
    out["spill_ld_L1miss"] = l1("spill_load")
    out["other_ld_L1miss"] = minus(gem5("ReadReq"), l1("spill_load"))
    out["spill_ld_L2miss"] = out["spill_ld_L2local"] = l2("spill_load")
    # Stores: spill stores (schema 9: the compiler-labelled ones), the stores
    # of spill events, the spill stores never read back, all other stores.
    out["spill_st_L1miss"] = l1("spill_store")
    out["spill_st_L2miss"] = out["spill_st_L2local"] = l2("spill_store")
    out["spill_event_L1miss"] = l1("spill_event")
    out["spill_event_L2local"] = l2("spill_event")
    out["unread_st_L1miss"] = minus(l1("spill_store"), l1("spill_event"))
    out["unread_st_L2local"] = minus(l2("spill_store"), l2("spill_event"))
    out["other_st_L1miss"] = minus(gem5("WriteReq"), l1("spill_store"))
    # Schema 9: the sp/s0-based stores.
    out["stack_st_L1miss"] = l1("stack_store")
    out["stack_st_L2miss"] = l2("stack_store")
    return out


def cache_misses(r: dict) -> dict[str, str]:
    """Table 3: the miss rates of one run's ROI, see miss_fractions()."""
    if not r["stats"] or not r["roi"]:
        return {k: "-" for k in MISS_COLUMNS}
    return {k: pct(*v) for k, v in miss_fractions(r).items()}


# Printed above table 3: what every term in the column names means.
MISS_TERMS_10 = [
    "Terimler (tablodan once):",
    "  access         = bir load ya da store komutunun cache'e yaptigi tek bir istek. Cache line",
    "                   sinirini asan bir komut iki access sayilir.",
    "  hit            = istenen veri cache'te bulundu; access o seviyede biter.",
    "  miss           = istenen veri cache'te yok; istek bir alt seviyeye gider (L1D -> L2 -> DRAM).",
    "  miss rate      = (misses / accesses) * 100: access'lerin yuzde kaci miss oldu.",
    "  L2 local       = L2 miss rate'in paydasi o turun L2'ye gelen access'leri, yani L1D miss'leri.",
    "  spill load     = adresi, o byte'i en son yazan spill store'un [adres, adres + boyut)",
    "                   araligina dusen load. Tespit sadece adrese dayanir.",
    "  other load     = spill load olmayan butun load'lar.",
    "  spill store    = ROI icinde stack'e yazan store (spill store sartlari), geri okunsun",
    "                   okunmasin.",
    "  spill event st = spill store'lardan en az bir kez geri okunanlar; cache sonucu store basina",
    "                   bir kez sayilir (store'un kendi sonucu, ilk reload'unda eklenir).",
    "  unread st      = hic geri okunmayan spill store'lar.",
    "  other store    = spill store olmayan store'lar (heap, global; store-conditional dahil).",
    "  L1D            = level-1 data cache; her load/store once buraya gelir.",
    "  L2             = L1D ve L1I'nin miss'lerini alan ortak level-2 cache. L2 access = L1 miss.",
    "Tum degerler yuzde ve ROI icinde olculur. Tablo 1 ve 2 her konfigurasyonda aynidir (ayni",
    "program, ayni komutlar); bu tablo ise konfigurasyona gore degisir, cunku sadece hit/miss",
    "davranisi degisir.",
]
MISS_TERMS_9 = [
    "Terimler (tablodan once):",
    "  access      = bir load ya da store komutunun cache'e yaptigi tek bir istek. Cache line",
    "                sinirini asan bir komut iki access sayilir.",
    "  hit         = istenen veri cache'te bulundu; access o seviyede biter.",
    "  miss        = istenen veri cache'te yok; istek bir alt seviyeye gider (L1D -> L2 -> DRAM).",
    "  miss rate   = (misses / accesses) * 100: access'lerin yuzde kaci miss oldu.",
    "  load        = bellekten veri okuyan komut. store = bellege veri yazan komut.",
    "  stack store = ROI icinde stack bolgesine yazan her store (geri okunsun okunmasin).",
    "  spill store = ROI icinde en az bir kez geri okunan stack store; cache sonucu store basina",
    "                bir kez sayilir.",
    "  spill load  = adresi, o byte'i en son yazan stack store'un [adres, adres + boyut)",
    "                araligina dusen load (spill reload). Tespit sadece adrese dayanir.",
    "  other load  = spill load olmayan butun load'lar.",
    "  other store = spill store olmayan butun store'lar (geri okunmayan stack store'lar dahil).",
    "  load miss   = bir load access'inin L1D'de miss olmasi. Load miss'ler iki gruba ayrilir:",
    "                spill load miss ve other load miss (store miss icin de ayni).",
    "  L1D         = level-1 data cache; her load/store once buraya gelir.",
    "  L2          = L1D ve L1I'nin miss'lerini alan ortak level-2 cache. L2 access = L1 miss.",
    "Tum degerler yuzde ve ROI icinde olculur. Tablo 1 ve 2 her konfigurasyonda aynidir (ayni",
    "program, ayni komutlar); bu tablo ise konfigurasyona gore degisir, cunku sadece hit/miss",
    "davranisi degisir.",
]
# name, formula, explanation lines
MISS_FORMULAS_9 = [
    ("L1D_miss", "(L1D misses / L1D accesses) * 100",
     ["Tum load ve store access'lerinin (spill + other) L1D miss rate'i: L1D'nin bu",
      "konfigurasyondaki genel performansi."]),
    ("spill_ld_L1miss", "(spill load L1D misses / spill load L1D accesses) * 100",
     ["Spill load'larin yuzde kaci L1D'de miss oldu. Genelde dusuktur: spill slot'u kisa",
      "sure once yazildigi icin cache line cogu zaman hala L1D'dedir."]),
    ("other_ld_L1miss", "((load misses - spill load misses) / (load accesses - spill load accesses)) * 100",
     ["Other load'larin (spill olmayan load'lar) L1D miss rate'i. spill_ld_L1miss ile yan",
      "yana bakilir: spill load'lar normal veriden daha mi az, daha mi cok miss oluyor?"]),
    ("spill_st_L1miss", "(spill store L1D misses / spill store L1D accesses) * 100",
     ["Spill store'larin yuzde kaci L1D'de miss oldu. Cache write-allocate: miss olan bir",
      "store once cache line'i L2'den getirir, sonra yazar."]),
    ("other_st_L1miss", "((store misses - spill store misses) / (store accesses - spill store accesses)) * 100",
     ["Other store'larin (spill olmayan store'lar) L1D miss rate'i; spill_st_L1miss ile",
      "karsilastirmak icin."]),
    ("stack_st_L1miss", "(stack store L1D misses / stack store L1D accesses) * 100",
     ["Butun stack store'larinin (geri okunsun okunmasin) L1D miss rate'i; spill_st_L1miss",
      "bunun geri okunan alt kumesidir."]),
    ("L2_miss", "(L2 misses / L2 accesses) * 100",
     ["L2'ye gelen tum isteklerin (L1D ve L1I miss'leri) yuzde kaci L2'de de miss oldu",
      "ve DRAM'e gitti."]),
    ("spill_ld_L2miss", "(spill load L2 misses / spill load L2 accesses) * 100",
     ["L1D'de miss olan spill load'larin yuzde kaci L2'de de miss oldu. Payda sadece",
      "L1D'yi miss eden spill load'lardir, butun spill load'lar degil."]),
    ("spill_st_L2miss", "(spill store L2 misses / spill store L2 accesses) * 100",
     ["L1D'de miss olan spill store'larin yuzde kaci L2'de de miss oldu (payda yine",
      "sadece L1D miss'leri)."]),
    ("stack_st_L2miss", "(stack store L2 misses / stack store L2 accesses) * 100",
     ["L1D'de miss olan stack store'larin yuzde kaci L2'de de miss oldu."]),
]
MISS_FORMULAS_10 = [
    MISS_FORMULAS_9[0], MISS_FORMULAS_9[1], MISS_FORMULAS_9[2],
    ("spill_st_L1miss", "(spill store L1D misses / spill store L1D accesses) * 100",
     ["Spill store'larin (geri okunsun okunmasin) yuzde kaci L1D'de miss oldu. Cache",
      "write-allocate: miss olan bir store once cache line'i L2'den getirir, sonra yazar."]),
    ("spill_event_L1miss", "(spill event store L1D misses / spill event store L1D accesses) * 100",
     ["Geri okunan spill store'larin yuzde kaci L1D'de miss oldu."]),
    ("unread_st_L1miss",
     "((spill store L1D misses - spill event store misses) / (spill store L1D accesses - spill event store accesses)) * 100",
     ["Hic geri okunmayan spill store'larin L1D miss rate'i."]),
    ("other_st_L1miss",
     "((store misses - spill store misses) / (store accesses - spill store accesses)) * 100",
     ["Spill store olmayan store'larin L1D miss rate'i; spill store'larla karsilastirmak icin."]),
    ("L2_local_miss", "(L2 misses / L2 accesses) * 100",
     ["L2'ye gelen tum isteklerin (L1D ve L1I miss'leri) yuzde kaci L2'de de miss oldu",
      "ve DRAM'e gitti."]),
    ("spill_ld_L2local", "(spill load L2 misses / spill load L2 accesses) * 100",
     ["L1D'de miss olan spill load'larin yuzde kaci L2'de de miss oldu. Payda sadece",
      "L1D'yi miss eden spill load'lardir, butun spill load'lar degil."]),
    ("spill_st_L2local", "(spill store L2 misses / spill store L2 accesses) * 100",
     ["L1D'de miss olan spill store'larin yuzde kaci L2'de de miss oldu."]),
    ("spill_event_L2local", "(spill event store L2 misses / spill event store L2 accesses) * 100",
     ["L1D'de miss olan geri okunan spill store'larin yuzde kaci L2'de de miss oldu."]),
    ("unread_st_L2local",
     "((spill store L2 misses - spill event store L2 misses) / (spill store L2 accesses - spill event store L2 accesses)) * 100",
     ["L1D'de miss olan, hic geri okunmayan spill store'larin yuzde kaci L2'de de miss oldu."]),
]


def miss_notes(formulas) -> list[str]:
    w = max(len(n) for n, _, _ in formulas)
    notes = ["Formuller ve aciklamalari:"]
    for name, formula, lines in formulas:
        notes.append(f"  {name.ljust(w)} = {formula}")
        notes.extend(f"  {' ' * w}   {line}" for line in lines)
    return notes


def use_schema(schema: int) -> None:
    """Show results of this metric schema: its columns, ratios and notes."""
    global SCHEMA, COUNT_COLUMNS, COUNT_NOTES, RATIOS, RATIO_FORMULAS, RATIO_NOTES
    global MISS_COLUMNS, MISS_TERMS, MISS_FORMULAS, MISS_NOTES
    SCHEMA = schema
    if schema >= 10:
        COUNT_COLUMNS, COUNT_NOTES = COUNT_COLUMNS_10, COUNT_NOTES_10
        RATIOS, RATIO_FORMULAS = RATIOS_10, RATIO_FORMULAS_10
        MISS_COLUMNS, MISS_TERMS, MISS_FORMULAS = MISS_COLUMNS_10, MISS_TERMS_10, MISS_FORMULAS_10
    else:
        COUNT_COLUMNS, COUNT_NOTES = COUNT_COLUMNS_9, COUNT_NOTES_9
        RATIOS, RATIO_FORMULAS = RATIOS_9, RATIO_FORMULAS_9
        MISS_COLUMNS, MISS_TERMS, MISS_FORMULAS = MISS_COLUMNS_9, MISS_TERMS_9, MISS_FORMULAS_9
    RATIO_NOTES = ratio_notes(RATIO_FORMULAS)
    MISS_NOTES = miss_notes(MISS_FORMULAS)


use_schema(CURRENT_SCHEMA)


def one_queue_line(qdir: Path) -> str | None:
    pid = read(qdir / "queue.pid")
    host = read(qdir / "queue.host") or HERE
    if not pid and qdir != LOGDIR:
        return None
    if pid and host != HERE:
        return (f"queue on {host}: started {stamp(int(read(qdir / 'queue.started') or 0))}; "
                f"this host is {HERE}, so its processes cannot be checked from here "
                f"(run states come from the run files)")
    gem5 = subprocess.run(["pgrep", "-c", "-u", str(os.getuid()), "-f",
                           "build/RISCV[A-Z0-9_]*/gem5.opt --outdir"],
                          capture_output=True, text=True).stdout.strip() or "0"
    if pid_alive(pid):
        started = read(qdir / "queue.started")
        since = (f", since {stamp(int(started))} "
                 f"({duration(time.time() - int(started))})"
                 if started.isdigit() else "")
        slots = read(qdir / "queue.maxjobs") or "?"
        return f"queue on {host}: RUNNING (pid {pid}){since}   gem5 processes: {gem5}/{slots}"
    if pid:
        return f"queue on {host}: FINISHED (every run has been started)   gem5 processes: {gem5}"
    return "queue: NOT STARTED (cache_scripts/start_all.sh)"


def queue_line() -> str:
    dirs = queue_dirs()
    # start_all.sh's queue (logs/cache_runs/queue.*) once it has ended is
    # noise next to the per-host queues of run_on_host.sh.
    if len(dirs) > 1 and not pid_alive(read(LOGDIR / "queue.pid")):
        dirs = dirs[1:]
    lines = [line for line in map(one_queue_line, dirs) if line]
    return "\n".join(lines)


def show_info(runs) -> None:
    print("Cache geometry of every configuration (from gem5's own config.ini)\n")
    print(input_line() + "\n")
    for cache in planned_caches(PROFILE):
        rows, source = geometry(cache, runs)
        print(f"{cache}: {label_for(cache)}   [source: {source}]")
        print(table(GEOMETRY_HEADER, rows, left=1) if rows else "  -")
        print()


def state_counts(records: list[dict]) -> dict[str, int]:
    # An older-schema result has to run again: it counts as pending.
    # An older-schema result and a stopped run are run again by the queue.
    states = ["PENDING" if r["state"] in ("OLD_SCHEMA", "MISSING", "STOPPED") else r["state"]
              for r in records]
    out = {s: states.count(s) for s in ("COMPLETED", "RUNNING", "PENDING")}
    out["FAILED"] = len(states) - sum(out.values())
    return out


def summary_line(records: list[dict]) -> str:
    c = state_counts(records)
    return (f"COMPLETED: {c['COMPLETED']}, RUNNING: {c['RUNNING']}, "
            f"PENDING: {c['PENDING']}, FAILED/STOPPED/INTERRUPTED: {c['FAILED']}"
            f"   (total {len(records)})")


def label_for(cache: str) -> str:
    org = cache.split("-", 1)[1] if "-" in cache else ""
    return {"": "L1D 2-way, L2 8-way (se.py defaults)",
            "fa": "fully associative L1D and L2 (FALRU)",
            "dm": "direct-mapped L1D and L2",
            "nway": "L1D 8-way, L2 16-way"}.get(
        org, f"{org[:-3]}-way (L1D {org[:-3]}-way, L2 8-way)")


def show_config(cache: str, runs) -> None:
    label = label_for(cache)
    print(f"=== {cache}: {label}   ({datetime.now():%Y-%m-%d %H:%M}) ===")
    print(input_line())
    print(queue_line(), "\n")
    rows, source = geometry(cache, runs)
    print(f"Cache geometry [source: {source}]")
    print(table(GEOMETRY_HEADER, rows) if rows else "  -")
    print()

    records = [run_record(cache, r, b) for r, b in runs]
    count_rows, ratio_rows, miss_rows = [], [], []
    for i, r in enumerate(records, 1):
        c = counts(r)
        count_rows.append([str(i), r["run_id"], state_text(r), stamp(r["start"]),
                           stamp(r["end"]) if r["end"] else "-",
                           duration(r["elapsed"]), progress(r),
                           *(num(c[k]) for k in COUNT_COLUMNS)])
        ratio_rows.append([str(i), r["run_id"],
                           *(pct(c[a], c[b]) for _, a, b in RATIOS)])
        m = cache_misses(r)
        miss_rows.append([str(i), r["run_id"], *(m[k] for k in MISS_COLUMNS)])

    print("1) State and instruction counts")
    print(table(["#", "run", "state", "started", "finished", "elapsed",
                 "progress", *COUNT_COLUMNS], count_rows, left=3))
    for note in COUNT_NOTES:
        print("   " + note)
    print()
    print("2) Ratios")
    print(table(["#", "run", *(h for h, _, _ in RATIOS)], ratio_rows, left=2))
    for note in RATIO_NOTES:
        print("   " + note)
    print()
    print("3) Cache miss rates (ROI)")
    for note in MISS_TERMS:
        print("   " + note)
    print()
    print(table(["#", "run", *MISS_COLUMNS], miss_rows, left=2))
    for note in MISS_NOTES:
        print("   " + note)
    print()
    if cache not in planned_caches(PROFILE):
        print(f"This configuration is not in the queue. To run it: "
              f"./scripts/launch_spill_batch.sh {PROFILE} {cache}")
    print(summary_line(records))


def queued_runs() -> tuple[set[tuple[str, str, str]], list[str]]:
    """(input, cache, run) of every queue that may still start runs, read from
    the "Queue: ..." line of its log; plus one note per queue."""
    queued: set[tuple[str, str, str]] = set()
    notes: list[str] = []
    expanded: dict[str, list[str]] = {}
    dirs = queue_dirs()
    if len(dirs) > 1 and not pid_alive(read(LOGDIR / "queue.pid")):
        dirs = dirs[1:]
    for qdir in dirs:
        log = read(qdir / "queue.log")
        host = read(qdir / "queue.host") or "?"
        if (qdir / "campaign.pid").exists():
            # A running campaign (campaign_schema10.sh) starts every run of
            # its plan, step by step; its log holds one queue per step after
            # older queues' lines, so the plan is what it still starts.
            if host == HERE and not pid_alive(read(qdir / "campaign.pid")):
                notes.append(f"campaign on {host} is not running")
                continue
            for line in read(qdir / "queue.plan").splitlines():
                fields = line.split()
                if len(fields) > 2:
                    queued.update((fields[0], fields[1], r) for r in fields[2].split(","))
            continue
        if not log.startswith("Queue: "):
            continue
        if host == HERE and not pid_alive(read(qdir / "queue.pid")):
            notes.append(f"queue on {host} is not running")
            continue
        if "all runs queued" in log:
            notes.append(f"queue on {host} has started every run it lists")
            continue
        for group in log.splitlines()[0][7:].split(";")[0].split():
            parts = group.split(":")
            if len(parts) < 2:
                continue
            inp, cache = parts[0], parts[1]
            if len(parts) > 2 and parts[2]:
                runs = parts[2].split(",")
            else:
                if inp not in expanded:
                    out = subprocess.run([str(RUNNER), "list", inp], capture_output=True,
                                         text=True).stdout.splitlines()[2:]
                    expanded[inp] = [l.split()[0] for l in out if l.strip()]
                runs = expanded[inp]
            queued.update((inp, cache, r) for r in runs)
    return queued, notes


def show_check() -> None:
    global PROFILE
    print(f"=== Coverage check   ({datetime.now():%Y-%m-%d %H:%M}) ===")
    print(queue_line())
    queued, notes = queued_runs()
    for note in notes:
        print(f"note: {note}")
    for inp in ("test", "train", "ref"):
        PROFILE = inp
        runs = workloads_all()
        caches = planned_caches(inp) or sorted({c for i, c, _ in queued if i == inp})
        if not runs or not caches:
            continue
        print()
        print("=" * 100)
        print(f"{input_line()}   {len(runs)} runs x {len(caches)} configurations = "
              f"{len(runs) * len(caches)}")
        print("=" * 100)
        rows, unqueued, failed = [], [], []
        hosts_total: dict[str, int] = {}
        totals = [0, 0, 0, 0, 0]
        for cache in caches:
            n = [0, 0, 0, 0, 0]      # completed, running, queued, not queued, failed
            hosts: dict[str, int] = {}
            for run_id, bench in runs:
                r = run_record(cache, run_id, bench)
                st = r["state"]
                if st == "COMPLETED":
                    n[0] += 1
                elif st == "RUNNING":
                    n[1] += 1
                    h = run_host(r["dir"]) if r["dir"] else "?"
                    hosts[h] = hosts.get(h, 0) + 1
                    hosts_total[h] = hosts_total.get(h, 0) + 1
                elif st in ("PENDING", "OLD_SCHEMA", "STOPPED", "MISSING"):
                    if (inp, cache, run_id) in queued:
                        n[2] += 1
                    else:
                        n[3] += 1
                        unqueued.append(f"{cache} {run_id} ({st})")
                else:
                    n[4] += 1
                    failed.append(f"{cache} {run_id} ({st}, {r['dir']})")
            totals = [a + b for a, b in zip(totals, n)]
            where = ", ".join(f"{h} {k}" for h, k in sorted(hosts.items()))
            rows.append([cache, str(n[0]), f"{n[1]}" + (f" ({where})" if where else ""),
                         str(n[2]), str(n[3]), str(n[4])])
        where = ", ".join(f"{h} {k}" for h, k in sorted(hosts_total.items()))
        rows.append(["total", str(totals[0]), f"{totals[1]}" + (f" ({where})" if where else ""),
                     str(totals[2]), str(totals[3]), str(totals[4])])
        print(table(["config", "completed", "running", "queued", "not queued", "failed"],
                    rows, left=1))
        print("   queued     = waiting in a host's queue; starts when a slot frees")
        print("   not queued = in no running queue: will not start until a queue lists it")
        if unqueued:
            print(f"\nNot queued ({len(unqueued)}):")
            for u in unqueued:
                print(f"  - {u}")
        if failed:
            print(f"\nFailed ({len(failed)}):")
            for f in failed:
                print(f"  - {f}")
        if not unqueued and not failed:
            print("\nEvery run is completed, running or queued.")


def workloads_all() -> list[tuple[str, str]]:
    """Every run of PROFILE's manifest (not narrowed to the queue plan)."""
    out = subprocess.run([str(RUNNER), "list", PROFILE], capture_output=True,
                         text=True).stdout.splitlines()
    return [tuple(line.split()[:2]) for line in out[2:] if line.strip()]


def show_all() -> None:
    global PROFILE
    print(f"=== Cache organisation experiment   ({datetime.now():%Y-%m-%d %H:%M}) ===")
    print(queue_line())
    print("queue order: " + " -> ".join(f"{p}:{c}" for p, c, _ in plan()))
    for profile in dict.fromkeys(p for p, _, _ in plan()):
        PROFILE = profile
        runs = workloads()
        print()
        print("=" * 100)
        print(input_line())
        print("=" * 100)
        summary, per_bench = [], {}
        spill_key = "roi_spill_store"   # schema 9: the compiler-labelled ones
        caches = planned_caches(profile)
        for cache in caches:
            rows, _ = geometry(cache, runs)
            geo = {row[0]: f"{row[5]} sets x {row[6]}" for row in rows}
            records = [run_record(cache, r, b) for r, b in runs]
            for r in records:
                text = state_text(r)
                if r["elapsed"] is not None:
                    text += f" {duration(r['elapsed'])}"
                if r["state"] == "RUNNING" and progress(r) != "-":
                    text += f" {progress(r)}"
                per_bench.setdefault(r["run_id"], []).append(text)
            sc = state_counts(records)
            starts = [r["start"] for r in records if r["start"]]
            ends = [r["end"] or time.time() for r in records if r["start"]]
            done = [counts(r) for r in records if r["state"] == "COMPLETED"]
            tot = {k: sum(c[k] or 0 for c in done)
                   for k in ("total_insts", "roi_total_insts", "roi_load", "roi_store",
                             spill_key, "roi_spill_load")}
            summary.append([
                cache, geo.get("L1D", "-"), geo.get("L2", "-"),
                str(sc["COMPLETED"]), str(sc["RUNNING"]), str(sc["PENDING"]),
                str(sc["FAILED"]),
                duration(max(ends) - min(starts)) if starts else "-",
                num(tot["total_insts"]), num(tot["roi_total_insts"]),
                num(tot["roi_load"]), num(tot["roi_store"]),
                num(tot[spill_key]), num(tot["roi_spill_load"]),
                pct(tot["roi_spill_load"], tot["roi_load"]),
                pct(tot[spill_key], tot["roi_store"]),
            ])
        print("Per configuration (sums over completed runs)")
        print(table(["config", "L1D", "L2", "completed", "running", "pending",
                     "failed", "wall", "total_insts", "roi_total_insts",
                     "roi_load", "roi_store", spill_key,
                     "roi_spill_load", "spill_load/load",
                     f"{spill_key[4:]}/store"], summary, left=3))
        print("\nPer benchmark: state, elapsed, progress")
        print(table(["run", *caches],
                    [[run_id, *cells] for run_id, cells in per_bench.items()],
                    left=len(caches) + 1))
    print()
    print("   wall = time from the configuration's first run start to its last run end (or now)")
    print("   spill_load/load, spill_store/store = share of ROI loads/stores that are spill accesses")
    print("   progress = estimate from the benchmark's earlier run time")
    print("\nDetails: cache_scripts/status_cache.sh --2way | --4way | --8way | --fa | --dm"
          "  [--test | --train]   cache geometry: --info")


SIZE = "small"
L1D_LINES = 64          # small: L1D 4 KiB / 64 B lines


class UsageError(Exception):
    pass


def target(args: list[str]) -> tuple[str, str | None]:
    """Command-line option -> (view, cache profile); sets PROFILE from
    --test / --train / --ref (default test)."""
    global PROFILE, SIMPOINT
    if "--simpoint" in args:
        SIMPOINT = True
        args = [a for a in args if a != "--simpoint"]
    if "--schema" in args:
        i = args.index("--schema")
        if i + 1 >= len(args) or not args[i + 1].isdigit():
            raise UsageError("--schema needs a number, e.g. --schema 8")
        use_schema(int(args[i + 1]))
        args = args[:i] + args[i + 2:]
    inputs = [a for a in args if a in ("--test", "--train", "--ref")]
    if len(inputs) > 1:
        raise UsageError("give one input: --test, --train or --ref")
    PROFILE = inputs[0][2:] if inputs else "test"
    args = [a for a in args if a not in inputs]
    if not args or args == ["--all"]:
        return "all", None
    if args == ["--check"]:
        return "check", None
    if args == ["--info"]:
        return "info", None
    if len(args) != 1:
        raise UsageError("give a single option")
    opt = args[0]
    if opt == "--fa":
        return "config", f"{SIZE}-fa"
    if opt == "--dm":
        return "config", f"{SIZE}-dm"
    m = re.fullmatch(r"--(\d+)way", opt)
    if m:
        n = int(m.group(1))
        valid = [1 << i for i in range(L1D_LINES.bit_length())]
        if n not in valid:
            raise UsageError(
                f"{opt} is not valid: L1D {L1D_LINES * 64 // 1024} KiB = {L1D_LINES} lines, "
                f"sets = {L1D_LINES} / N and gem5 needs a power of two "
                f"({L1D_LINES} / {n} = {L1D_LINES / n:.2f}). "
                f"Valid N: {', '.join(map(str, valid))} "
                f"(1 = direct-mapped, {L1D_LINES} = one set, same as fully associative).")
        return "config", f"{SIZE}-{n}way"
    raise UsageError(f"unknown option: {opt}")


def main() -> int:
    try:
        view, cache = target(sys.argv[1:])
    except UsageError as error:
        print(f"Error: {error}\n")
        print(__doc__)
        return 2
    if view == "all":
        show_all()
        return 0
    if view == "check":
        show_check()
        return 0
    runs = workloads()
    if view == "info":
        show_info(runs)
    else:
        show_config(cache, runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
