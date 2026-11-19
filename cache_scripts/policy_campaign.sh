#!/usr/bin/env bash
# Replacement-policy experiment (metric schema 10): every run of one input
# (default test) under the small cache sizes (L1D 4 KiB, L1I 32 KiB, L2
# 32 KiB) with L1D 2-, 4- and 8-way (L2 8-way, L1I 2-way) and six replacement
# policies, the same policy in L1I, L1D and L2:
#   lru__ LRU   plru_ tree PLRU   fifo_ FIFO   rand_ random
#   srrip SRRIP (gem5 RRIPRP)   brrip BRRIP
# 3 x 6 = 18 configurations (small-<N>way-<policy>), 35 test runs each. The
# policy names are padded to five letters so that every configuration's run
# paths have the same length: the path reaches the program's arguments and
# moves its stack, which would change the cache behaviour by itself.
#
# Results go to cache_results/ in the gem5 root, one directory per benchmark:
#   cache_results/<benchmark>/<input>/m5out/<config>/<run>_<HHMM_DDMMYYYY>/
#   cache_results/<benchmark>/<input>/report/        (reports, later)
#   cache_results/<benchmark>/m5out_<benchmark>/     (latest_* links)
#   cache_results/_campaign/                         (plan, logs, driver files)
#
#   cache_scripts/policy_campaign.sh --dry-run        check the host, show the plan; changes nothing
#   cache_scripts/policy_campaign.sh start            check, then start the queue (detached: you can log out)
#   cache_scripts/policy_campaign.sh status           progress, running and failed runs, time left
#   cache_scripts/policy_campaign.sh status --runs    one line per run: the state in every configuration
#   cache_scripts/policy_campaign.sh status --done    every completed run: where, when, how long
#   cache_scripts/policy_campaign.sh stop --yes       stop the queue and every policy run on this host
#
#   TOTAL=42 ... start        this user's gem5 runs on the host in all (default: run_on_host.sh's rule)
#   POLICY_JOBS=21 ... start  policy runs while another queue (launch_spill_batch.sh, e.g. train)
#                             runs on the host (default: half of TOTAL); alone it may use TOTAL
#   INPUT=train ... start     another input (default test)
#
# x264 starts first in every configuration (about a week per run), then the
# other runs, longest first. A run that cannot be started is retried 3 times,
# 10 minutes apart; then the queue stops and says why in campaign.log, rather
# than skipping the rest. start again resumes: running and completed runs are
# skipped. status works from any host that mounts /cta/users.
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT" || exit 1
RUNNER="$ROOT/scripts/spec_spill_runner.sh"
GEM5="$ROOT/build/RISCV_SCHEMA10/gem5.opt"
HELLO="$ROOT/tests/test-progs/hello/bin/riscv/linux/hello"
INPUT="${INPUT:-test}"
RESULTS="${POLICY_RESULTS:-$ROOT/cache_results}"   # POLICY_RESULTS: for tests only
CDIR="$RESULTS/_campaign"
LOG="$CDIR/campaign.log"
QLOG="$CDIR/queue.log"
PLAN="$CDIR/plan_$INPUT.txt"
HOST="$(hostname)"
ME="$(id -u)"
ASSOCS=(2 4 8)
POLICIES=(lru__ plru_ fifo_ rand_ srrip brrip)
FIRST=(x264)            # run IDs started first, in every configuration
POLL_SECONDS=30
RETRY_SECONDS=600
MAX_TRIES=3

die()   { printf 'error: %s\n' "$*" >&2; exit 1; }
note()  { printf '  %s\n' "$*"; }
stamp() { printf '[%(%Y-%m-%d %H:%M:%S)T]' -1; }
alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

configs() {
    local a p
    for a in "${ASSOCS[@]}"; do
        for p in "${POLICIES[@]}"; do printf 'small-%sway-%s\n' "$a" "$p"; done
    done
}

# gem5 runs at a time on this host: physical cores minus the load minus 2,
# capped by 2 GB of free memory per run, plus this user's runs going already
# (the rule of run_on_host.sh and campaign_schema10.sh).
recommended_total() {
    local cores load mem_gb own by_cpu by_mem n
    cores=$(lscpu -p=CORE,SOCKET 2>/dev/null | grep -v '^#' | sort -u | wc -l)
    (( cores > 0 )) || cores=$(nproc)
    load=$(awk '{printf "%d", $1 + 0.999}' /proc/loadavg)
    mem_gb=$(awk '/^MemAvailable:/ {printf "%d", $2 / 1048576}' /proc/meminfo)
    own=$(all_runs)
    by_cpu=$(( cores - load - 2 ))
    by_mem=$(( mem_gb / 2 ))
    n=$(( (by_cpu < by_mem ? by_cpu : by_mem) + own ))
    (( n < 1 )) && n=1
    printf '%d' "$n"
}

# This user's gem5 runs on this host: all of them, and those of this experiment.
gem5_cmdlines() { pgrep -u "$ME" -af 'build/RISCV[A-Z0-9_]*/gem5.opt' 2>/dev/null; }
all_runs()    { gem5_cmdlines | wc -l; }
policy_runs() { gem5_cmdlines | grep -c -- "--outdir=$RESULTS/"; }
# Another queue of this user here (run_on_host.sh / campaign_schema10.sh).
other_queue() { pgrep -u "$ME" -f 'scripts/launch_spill_batch[.]sh' > /dev/null; }

driver_pid()  { cat "$CDIR/driver.pid" 2>/dev/null; }
driver_host() { cat "$CDIR/driver.host" 2>/dev/null; }

# The queue, one line per run: config run_id benchmark reference_seconds.
# FIRST runs, then the others longest first; every configuration of a run
# side by side. The reference time of a run is its LRU run with the same L1D
# associativity in benchmarks/ (0 = none: those go first).
build_plan() {
    mkdir -p "$CDIR"
    "$RUNNER" list "$INPUT" | awk 'NR > 2 && NF {print $1, $2}' > "$CDIR/runs_$INPUT.txt"
    [[ -s "$CDIR/runs_$INPUT.txt" ]] || die "the runner lists no runs for input $INPUT"
    python3 - "$ROOT" "$INPUT" "${FIRST[*]}" "$(configs | paste -sd' ')" "$CDIR/runs_$INPUT.txt" \
        > "$PLAN.tmp" <<'PY' || die "cannot build the plan"
import sys
from pathlib import Path
root, inp, first, configs = Path(sys.argv[1]), sys.argv[2], sys.argv[3].split(), sys.argv[4].split()
runs = [line.split() for line in Path(sys.argv[5]).read_text().splitlines() if line.strip()]

def ref(run, bench, assoc):
    d = root / "benchmarks" / bench / inp / "m5out" / f"small-{assoc}way" / f"latest_{run}" / ".runner"
    try:
        return int((d / "finished.epoch").read_text()) - int((d / "started.epoch").read_text())
    except (OSError, ValueError):
        return 0

longest = lambda r: max(ref(r[0], r[1], a) for a in (2, 4, 8))
order = ([r for r in runs if r[0] in first] +
         sorted((r for r in runs if r[0] not in first),
                key=lambda r: (longest(r) != 0, -longest(r))))
for run, bench in order:
    for cfg in configs:
        assoc = cfg.split("-")[1].rstrip("way")
        print(cfg, run, bench, ref(run, bench, assoc))
PY
    mv "$PLAN.tmp" "$PLAN"
}

# 0 if the run is going or has a schema-10 result already.
handled() {   # CONFIG BENCHMARK RUN_ID
    local d="$RESULTS/$2/m5out_$2/latest_${INPUT}_$1_$3" s
    [[ -e "$d" ]] || return 1
    s="$(cat "$d/.runner/status" 2>/dev/null)"
    case "$s" in
      RUNNING|STARTING) return 0 ;;
      COMPLETED) grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*10$' "$d/riscv_spill_stats.txt" 2>/dev/null ;;
      *) return 1 ;;
    esac
}

# Every configuration instantiated once (gem5 --initialize-only, no
# simulation): the replacement policy of L1I, L1D and L2 and the
# associativities must be the intended ones.
check_configs() {
    local cfg dir bad=0
    mkdir -p "$CDIR/config_check"
    for cfg in $(configs); do
        dir="$CDIR/config_check/$cfg"
        rm -rf "$dir"
        # shellcheck disable=SC2046
        if ! "$GEM5" --outdir="$dir" configs/deprecated/example/se.py --cmd="$HELLO" \
                $(bash -c "source <(sed -n '/^cache_options() {/,/^}/p' '$RUNNER'); cache_options '$cfg'") \
                --initialize-only > "$dir.log" 2>&1; then
            note "FAILED $cfg: gem5 did not instantiate it (see $dir.log)"; bad=1; continue
        fi
        python3 - "$dir/config.ini" "$cfg" <<'PY' || bad=1
import configparser, sys
ini, cfg = sys.argv[1], sys.argv[2]
assoc = int(cfg.split("-")[1].rstrip("way"))
want = {"lru": ("LRURP", None), "plru": ("TreePLRURP", None), "fifo": ("FIFORP", None),
        "rand": ("RandomRP", None), "srrip": ("BRRIPRP", "100"), "brrip": ("BRRIPRP", "3")}
rp, btp = want[cfg.split("-")[2].rstrip("_")]
c = configparser.ConfigParser(strict=False, interpolation=None)
c.read(ini)
got, ok = [], True
for name, sec, a in (("L1I", "system.cpu.icache", 2), ("L1D", "system.cpu.dcache", assoc),
                     ("L2", "system.l2", 8)):
    p = c[sec + ".replacement_policy"]
    got.append(f"{name} {c[sec]['assoc']}-way {p['type']}" + (f" btp={p['btp']}" if "btp" in p else ""))
    ok &= (p["type"] == rp and (btp is None or p.get("btp") == btp)
           and int(c[sec]["assoc"]) == a)
print(f"  {'ok    ' if ok else 'WRONG '} {cfg:<18} " + ", ".join(got))
sys.exit(0 if ok else 1)
PY
    done
    return "$bad"
}

check_host() {
    echo "== Host check ($HOST)"
    [[ -x "$GEM5" ]] || die "no schema-10 gem5 at $GEM5"
    "$RUNNER" check "$INPUT" small-4way-srrip all > "$CDIR/runner_check.log" 2>&1 ||
        { tail -3 "$CDIR/runner_check.log" >&2; die "the runner refuses to start runs here (see $CDIR/runner_check.log)"; }
    grep -q 'FAILED$' "$CDIR/runner_check.log" &&
        note "notice: runs with missing binaries or inputs: $(grep 'FAILED$' "$CDIR/runner_check.log" | tr -d '[]' | awk '{print $1}' | paste -sd' ')"
    note "runner: gem5 build and inputs ok"
    echo "== The 18 configurations (gem5 --initialize-only)"
    check_configs || die "a configuration is not what it should be (see above); nothing started"
}

cmd_dry_run() {
    mkdir -p "$CDIR"
    check_host
    build_plan
    local total
    total="${TOTAL:-$(recommended_total)}"
    echo
    echo "== Plan on $HOST (nothing is started)"
    note "input $INPUT: $(wc -l < "$PLAN") runs = 18 configurations x $(awk '{print $2}' "$PLAN" | sort -u | wc -l) runs"
    note "gem5 runs on the host at most: $total; policy runs at most ${POLICY_JOBS:-$(( (total + 1) / 2 ))} while another queue runs here"
    note "running now: $(all_runs) gem5 runs of this user, $(policy_runs) of them policy runs; another queue here: $(other_queue && echo yes || echo no)"
    local done_n=0 cfg run bench ref
    while read -r cfg run bench ref; do handled "$cfg" "$bench" "$run" && done_n=$((done_n + 1)); done < "$PLAN"
    note "already running or completed (skipped): $done_n"
    note "order (first 20 of $(wc -l < "$PLAN")):"
    head -20 "$PLAN" | awk '{printf "    %-18s %-20s ref %.1f h\n", $1, $2, $4 / 3600}'
    note "reference work: $(awk '{s += $4} END {printf "%.0f", s / 3600}' "$PLAN") core-hours (from the LRU runs in benchmarks/)"
}

cmd_start() {
    mkdir -p "$CDIR"
    if alive "$(driver_pid)" && [[ "$(driver_host)" == "$HOST" ]]; then
        die "the policy queue already runs here (pid $(driver_pid)); see: $0 status"
    fi
    [[ -n "$(driver_pid)" && "$(driver_host)" != "$HOST" ]] &&
        note "warning: a policy queue was started on $(driver_host); if it still runs there, stop it first"
    check_host
    build_plan
    write_readme
    TOTAL="${TOTAL:-$(recommended_total)}"
    POLICY_JOBS="${POLICY_JOBS:-$(( (TOTAL + 1) / 2 ))}"
    [[ "$TOTAL" =~ ^[0-9]+$ && "$TOTAL" -gt 0 ]] || die "TOTAL must be a positive number"
    [[ "$POLICY_JOBS" =~ ^[0-9]+$ && "$POLICY_JOBS" -gt 0 ]] || die "POLICY_JOBS must be a positive number"
    echo "$TOTAL" > "$CDIR/total"
    echo "$POLICY_JOBS" > "$CDIR/policy_jobs"
    echo "$INPUT" > "$CDIR/input"
    TOTAL="$TOTAL" POLICY_JOBS="$POLICY_JOBS" INPUT="$INPUT" \
        setsid nohup bash "$0" __drive >> "$LOG" 2>&1 < /dev/null &
    local driver=$!
    echo "$driver" > "$CDIR/driver.pid"
    echo "$HOST" > "$CDIR/driver.host"
    date +%s > "$CDIR/driver.started"
    echo
    echo "== Policy queue started on $HOST (pid $driver): $(wc -l < "$PLAN") runs of input $INPUT,"
    echo "   at most $POLICY_JOBS policy runs while another queue runs here ($TOTAL when alone),"
    echo "   $TOTAL gem5 runs of this user in all. Detached: you can log out."
    echo "   Progress: $0 status      Log: $LOG"
}

# The detached part: start every planned run, one per free slot.
cmd_drive() {
    echo "$(stamp) queue on $HOST: $(wc -l < "$PLAN") runs of input $INPUT; at most $POLICY_JOBS policy runs while another queue runs here, $TOTAL gem5 runs in all"
    local cfg run bench ref tries out cap started=0 skipped=0
    while read -r -u 3 cfg run bench ref; do
        if handled "$cfg" "$bench" "$run"; then skipped=$((skipped + 1)); continue; fi
        tries=0
        while :; do
            while :; do
                cap="$TOTAL"; other_queue && cap="$POLICY_JOBS"
                (( $(policy_runs) < cap && $(all_runs) < TOTAL )) && break
                sleep "$POLL_SECONDS"
            done
            out="$(SPILL_RESULTS_ROOT="$RESULTS" "$RUNNER" start "$INPUT" "$cfg" "$run" 2>&1 < /dev/null)"
            if grep -q 'STARTED pid=' <<< "$out"; then
                started=$((started + 1))
                printf '%s started %s %s (%s policy, %s gem5 runs here)\n' "$(stamp)" "$cfg" "$run" \
                    "$(policy_runs)" "$(all_runs)" >> "$QLOG"
                break
            fi
            tries=$((tries + 1))
            echo "$(stamp) could not start $cfg $run (try $tries of $MAX_TRIES):"
            sed 's/^/    /' <<< "$out" | tail -5
            if (( tries >= MAX_TRIES )); then
                echo "$(stamp) STOPPED: $cfg $run cannot be started; the queue stops here so that the"
                echo "    other runs are not skipped. Fix the cause above, then: $0 start (it resumes)"
                rm -f "$CDIR/driver.pid"
                exit 1
            fi
            sleep "$RETRY_SECONDS"
        done
        sleep 5
    done 3< "$PLAN"
    echo "$(stamp) every run started ($started now, $skipped already running or completed); the last ones finish on their own"
    rm -f "$CDIR/driver.pid"
}

cmd_status() {
    local view="${1:-}" pid host
    pid="$(driver_pid)"; host="$(driver_host)"
    if [[ -z "$pid" ]]; then
        echo "queue: no driver (finished, stopped or never started)"
    elif [[ "$host" == "$HOST" ]]; then
        alive "$pid" && echo "queue: running on $HOST (pid $pid)" || echo "queue: driver pid $pid is gone (crashed or killed); start resumes"
    else
        echo "queue: started on $host (pid $pid); this host is $HOST, so its process cannot be checked from here"
    fi
    [[ -f "$PLAN" ]] || { echo "no plan yet ($PLAN): run start or --dry-run on the experiment host"; return 0; }
    python3 - "$RESULTS" "$INPUT" "$PLAN" "$view" "$HOST" "$(cat "$CDIR/policy_jobs" 2>/dev/null)" <<'PY'
import os, re, sys, time
from pathlib import Path
results, inp, plan, view, here, pjobs = (Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]),
                                         sys.argv[4], sys.argv[5], sys.argv[6])
pjobs = int(pjobs) if pjobs.isdigit() else None
now = time.time()

def read(p):
    try:
        return p.read_text().strip()
    except OSError:
        return ""

def hours(s):
    if s is None:
        return "-"
    return f"{s / 60:.0f} min" if s < 3600 else f"{s / 3600:.1f} h"

def when(epoch):
    return time.strftime("%m-%d %H:%M", time.localtime(epoch)) if epoch else "-"

entries = []
for line in plan.read_text().split("\n"):
    if not line.strip():
        continue
    cfg, run, bench, ref = line.split()
    d = results / bench / f"m5out_{bench}" / f"latest_{inp}_{cfg}_{run}"
    r = d / ".runner"
    state = read(r / "status") or ("PENDING" if not d.exists() else "UNKNOWN")
    host = read(r / "host")
    if state == "RUNNING" and host == here:
        pid = read(r / "worker.pid")
        if not (pid.isdigit() and os.path.exists(f"/proc/{pid}")):
            state = "INTERRUPTED"
    if state == "COMPLETED" and not re.search(r"^# metric_schema\s*:\s*10$",
                                              read(d / "riscv_spill_stats.txt"), re.M):
        state = "FAILED"
    start = read(r / "started.epoch")
    end = read(r / "finished.epoch")
    start = int(start) if start.isdigit() else None
    end = int(end) if end.isdigit() else None
    elapsed = ((end or now) - start) if start else None
    entries.append(dict(cfg=cfg, run=run, bench=bench, ref=int(ref), state=state, host=host,
                        start=start, end=end, elapsed=elapsed, dir=d.resolve() if d.exists() else d))

configs = list(dict.fromkeys(e["cfg"] for e in entries))
runs = list(dict.fromkeys(e["run"] for e in entries))
by = lambda s: [e for e in entries if e["state"] == s]
done, running = by("COMPLETED"), by("RUNNING") + by("STARTING")
bad = [e for e in entries if e["state"] in ("FAILED", "STOPPED", "INTERRUPTED", "UNKNOWN")]
pending = by("PENDING")
n = len(entries)
print(f"\n== Replacement-policy experiment, input {inp}   ({time.strftime('%Y-%m-%d %H:%M')})")
print(f"runs: {len(done)} of {n} completed ({100 * len(done) / n:.1f}%), {len(running)} running, "
      f"{len(bad)} failed/stopped, {len(pending)} not started")

# Work left, in core-hours of the reference (LRU) runs: what pending runs
# need, plus what running runs still need beyond their elapsed time.
ref_total = sum(e["ref"] for e in entries)
left = sum(e["ref"] for e in pending) + sum(max(e["ref"] - (e["elapsed"] or 0), 0) for e in running)
eta = []
if running:
    eta.append(f"about {left / 3600 / len(running) / 24:.1f} days at the {len(running)} runs going now")
if pjobs and pjobs != len(running):
    eta.append(f"{left / 3600 / pjobs / 24:.1f} days at {pjobs} runs")
print(f"work: {100 * (1 - left / ref_total):.1f}% of {ref_total / 3600:,.0f} reference core-hours done; "
      f"{left / 3600:,.0f} left" + (" = " + ", ".join(eta) if eta else "")
      + " (the longest run, about a week, sets a lower bound)")

if view == "--runs":
    short = [c.replace("small-", "") for c in configs]
    mark = {"COMPLETED": "D", "RUNNING": "R", "STARTING": "R", "PENDING": ".", "FAILED": "F",
            "STOPPED": "S", "INTERRUPTED": "I", "UNKNOWN": "?"}
    print("\nD completed  R running  . not started  F failed  S stopped  I interrupted")
    assocs = list(dict.fromkeys(c.split("-")[1] for c in configs))
    letters = {a: "".join(c.split("-")[2][0] for c in configs if c.split("-")[1] == a) for a in assocs}
    print(f"{'':<20} " + "  ".join(f"{a:<{len(letters[a])}}" for a in assocs))
    print(f"{'run':<20} " + "  ".join(letters[a] for a in assocs))
    for run in runs:
        cells = ["".join(mark.get(e["state"], "?") for e in entries
                         if e["run"] == run and e["cfg"].split("-")[1] == a) for a in assocs]
        print(f"{run:<20} " + "  ".join(cells))
    print("columns per associativity: l lru, p plru, f fifo, r rand, s srrip, b brrip")
    sys.exit(0)

if view == "--done":
    print(f"\n{'config':<18} {'run':<20} {'host':<10} {'started':<11} {'finished':<11} {'took':>8} {'LRU ref':>8}")
    for e in sorted(done, key=lambda e: e["end"] or 0):
        print(f"{e['cfg']:<18} {e['run']:<20} {e['host']:<10} {when(e['start']):<11} {when(e['end']):<11} "
              f"{hours(e['elapsed']):>8} {hours(e['ref']):>8}")
    sys.exit(0)

print(f"\n{'config':<18} {'done':>5} {'run':>4} {'fail':>5} {'todo':>5} {'%done':>6} {'core-h used':>12}")
for c in configs:
    es = [e for e in entries if e["cfg"] == c]
    d = sum(e["state"] == "COMPLETED" for e in es)
    r = sum(e["state"] in ("RUNNING", "STARTING") for e in es)
    f = sum(e in bad for e in es)
    used = sum(e["elapsed"] or 0 for e in es if e["state"] in ("COMPLETED", "RUNNING", "STARTING"))
    print(f"{c:<18} {d:>5} {r:>4} {f:>5} {len(es) - d - r - f:>5} {100 * d / len(es):>5.0f}% {used / 3600:>12,.0f}")

if running:
    print(f"\nrunning ({len(running)}):")
    print(f"  {'config':<18} {'run':<20} {'host':<10} {'started':<11} {'elapsed':>8} {'~progress':>9}")
    for e in sorted(running, key=lambda e: e["start"] or 0):
        prog = f"{100 * e['elapsed'] / e['ref']:.0f}%" if e["ref"] and e["elapsed"] else "-"
        print(f"  {e['cfg']:<18} {e['run']:<20} {e['host']:<10} {when(e['start']):<11} "
              f"{hours(e['elapsed']):>8} {prog:>9}")
    print("  ~progress = elapsed / the same run's LRU time in benchmarks/ (an estimate)")
if bad:
    print(f"\nfailed, stopped or interrupted ({len(bad)}); start again reruns them:")
    for e in bad:
        last = ""
        log = Path(e["dir"]) / "nohup.log"
        if log.exists():
            lines = [l for l in log.read_text(errors="replace").splitlines() if l.strip()]
            last = lines[-1][:70] if lines else ""
        print(f"  {e['state']:<11} {e['cfg']:<18} {e['run']:<20} {e['host']:<10} {last}")
if pending:
    nxt = ", ".join(f"{e['cfg'].replace('small-', '')} {e['run']}" for e in pending[:6])
    print(f"\nnext to start: {nxt}{', ...' if len(pending) > 6 else ''}")
PY
    if [[ -f "$LOG" ]]; then echo; echo "== $LOG (last lines)"; tail -n 5 "$LOG"; fi
    echo
    echo "Per run: $0 status --runs    Completed runs and their times: $0 status --done"
}

cmd_stop() {
    [[ "${1:-}" == --yes ]] || die "usage: $0 stop --yes   (stops the policy queue and every policy run on $HOST)"
    local pid outdir r n=0
    pid="$(driver_pid)"
    if alive "$pid" && [[ "$(driver_host)" == "$HOST" ]]; then
        kill -- "-$pid" 2>/dev/null || kill "$pid"
        echo "policy queue stopped (pid $pid)"
    fi
    rm -f "$CDIR/driver.pid"
    while read -r outdir; do
        r="$outdir/.runner"
        [[ -d "$r" ]] || continue
        SPILL_RESULTS_ROOT="$RESULTS" "$RUNNER" stop "$(cat "$r/profile")" "$(cat "$r/cache")" \
            "$(cat "$r/run_id")" > /dev/null 2>&1 && n=$((n + 1))
    done < <(gem5_cmdlines | grep -o -- "--outdir=$RESULTS/[^ ]*" | sed 's/^--outdir=//')
    echo "$n policy runs stopped on $HOST"
}

write_readme() {
    [[ -f "$RESULTS/README.md" ]] && return 0
    cat > "$RESULTS/README.md" <<'EOF'
# Replacement-policy experiment (metric schema 10)

Every run of the input under the small cache sizes (L1D 4 KiB, L1I 32 KiB,
L2 32 KiB, 64 B lines) with L1D 2-, 4- and 8-way (L2 8-way, L1I 2-way) and
six replacement policies, the same policy in L1I, L1D and L2. Started and
monitored with `cache_scripts/policy_campaign.sh`.

| Config suffix | gem5 policy |
|---|---|
| `lru__` | `LRURP` |
| `plru_` | `TreePLRURP` |
| `fifo_` | `FIFORP` |
| `rand_` | `RandomRP` |
| `srrip` | `RRIPRP` (SRRIP: `BRRIPRP` with `btp=100`) |
| `brrip` | `BRRIPRP` (`btp=3`) |

The suffixes are padded to five letters so that every configuration's run
paths have the same length: the path reaches the program's arguments and
moves its stack, which changes the cache behaviour by itself. For the same
reason LRU is run again here instead of reusing the runs in `benchmarks/`.

Layout, one directory per benchmark:

    <benchmark>/<input>/m5out/<config>/<run>_<HHMM_DDMMYYYY>/   gem5 output of one run
    <benchmark>/<input>/report/                                reports of the benchmark
    <benchmark>/m5out_<benchmark>/                             latest_* links of the runner
    _campaign/                                                 plan, campaign.log, queue.log

The program counters (`roi_spill_*`) do not depend on the cache; only the
hit and miss counts change with the policy.
EOF
}

case "${1:-}" in
  --dry-run) cmd_dry_run ;;
  start)     cmd_start ;;
  status)    shift; cmd_status "$@" ;;
  stop)      shift; cmd_stop "$@" ;;
  __drive)   cmd_drive ;;
  *) sed -n '2,37p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
