#!/usr/bin/env bash
# The metric-schema-10 campaign on this host (written for castXeon), under the
# five small-* cache configurations, in this order:
#   1. the longest runs: roms (train) and x264 (test), every configuration;
#   2. every other test run, longest first;
#   3. the ref SimPoint points (cache_scripts/simpoint.sh run, then combine);
#   4. every other train run, longest first.
# A free slot always goes to the next pending run, so the machine never idles;
# at most TOTAL gem5 runs of this user run at a time. Full ref runs are not
# part of it.
#
#   cache_scripts/campaign_schema10.sh --dry-run   check the host, show the plan; changes nothing
#   cache_scripts/campaign_schema10.sh start       check, run the spill tests, stop this host's
#                                                  schema-9 runs, move the schema-9 SimPoint
#                                                  results aside, start (detached: you can log out)
#   cache_scripts/campaign_schema10.sh status      where the campaign is
#   cache_scripts/campaign_schema10.sh stop --yes  stop the campaign and all its runs on this host
#
#   TOTAL=45 ... start     gem5 runs at a time (default: run_on_host.sh's recommendation)
#   SKIP_TESTS=1 ... start do not run the spill test suite first
#
# Running start again resumes: runs and SimPoint points with a schema-10 result
# are skipped. The schema-9 SimPoint results move to <run>_simpoint_schema9
# (still read by status_cache.sh --schema 9 --simpoint); the schema-9 full runs
# stay where they are. Logs: logs/cache_runs/hosts/<host>/campaign.log,
# queue.log (test and train starts), simpoint.log (the points).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT" || exit 1
RUNNER="$ROOT/scripts/spec_spill_runner.sh"
GEM5="$ROOT/build/RISCV_SCHEMA10/gem5.opt"
GEM5_SCHEMA9="$ROOT/build/RISCV/gem5.opt"
ASSEMBLER=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
HOST="$(hostname)"
QDIR="$ROOT/logs/cache_runs/hosts/$HOST"
LOG="$QDIR/campaign.log"
CONFIGS=(small-2way small-fa small-dm small-4way small-8way)
# input:run of the runs that start first, every configuration.
LONG=(train:roms test:x264)

die()  { printf 'error: %s\n' "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }
stamp() { printf '[%(%Y-%m-%d %H:%M:%S)T]' -1; }

alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }
campaign_pid() { cat "$QDIR/campaign.pid" 2>/dev/null; }

# This host's gem5 runs at a time: physical cores minus the load minus 2,
# capped by 2 GB of free memory per run, plus the runs going already (the
# rule of run_on_host.sh's recommended --jobs).
recommended_total() {
    local cores load mem_gb own by_cpu by_mem
    cores=$(lscpu -p=CORE,SOCKET 2>/dev/null | grep -v '^#' | sort -u | wc -l)
    (( cores > 0 )) || cores=$(nproc)
    load=$(awk '{printf "%d", $1 + 0.999}' /proc/loadavg)
    mem_gb=$(awk '/^MemAvailable:/ {printf "%d", $2 / 1048576}' /proc/meminfo)
    own=$(pgrep -c -u "$(id -u)" -x gem5.opt 2>/dev/null || true)
    by_cpu=$(( cores - load - 2 ))
    by_mem=$(( mem_gb / 2 ))
    local n=$(( (by_cpu < by_mem ? by_cpu : by_mem) + ${own:-0} ))
    (( n < 1 )) && n=1
    printf '%d' "$n"
}

# Run IDs of an input, longest first by the qemu instruction count (a run
# without a count goes first), without the given ones.
longest_first() {   # INPUT [EXCLUDED_RUN...]
    local input="$1" run n; shift
    "$RUNNER" list "$input" | awk 'NR > 2 && NF {print $1}' | while read -r run; do
        [[ " $* " == *" $run "* ]] && continue
        n="$(awk '{print $3}' "$ROOT/logs/qemu/$input/$run/RESULT" 2>/dev/null)"
        printf '%s %s\n' "${n:-999999999999999}" "$run"
    done | sort -k1,1nr | awk '{print $2}'
}

# The launch_spill_batch.sh groups of a step: input:config:run, configurations
# side by side for each run.
groups_of() {   # INPUT RUN...
    local input="$1" run cfg; shift
    for run in "$@"; do
        for cfg in "${CONFIGS[@]}"; do printf '%s:%s:%s\n' "$input" "$cfg" "$run"; done
    done
}

build_plan() {
    local entry long_test=() long_train=()
    for entry in "${LONG[@]}"; do
        [[ "${entry%%:*}" == test ]] && long_test+=("${entry#*:}")
        [[ "${entry%%:*}" == train ]] && long_train+=("${entry#*:}")
    done
    mapfile -t STEP1 < <(for entry in "${LONG[@]}"; do groups_of "${entry%%:*}" "${entry#*:}"; done
                         groups_of test $(longest_first test "${long_test[@]}"))
    mapfile -t STEP3 < <(groups_of train $(longest_first train "${long_train[@]}"))
}

schema_of() {   # result directory -> its metric schema (a SimPoint dir: its first point's)
    local f
    for f in "$1/riscv_spill_stats.txt" "$1/sp01/riscv_spill_stats.txt"; do
        [[ -f "$f" ]] || continue
        sed -n 's/^# metric_schema[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$f" | head -1
        return
    done
}

# Combined schema-9 SimPoint results, which simpoint.sh run would delete.
simpoint9_dirs() {
    local d
    for d in "$ROOT"/benchmarks/*/ref/m5out/*/*_simpoint; do
        [[ -d "$d" && ! -L "$d" ]] || continue
        [[ "$(schema_of "$d")" == 9 ]] && printf '%s\n' "$d"
    done
}

# "pid profile cache run" of this host's schema-9 gem5 runs.
schema9_runs() {
    local pid exe outdir r
    for pid in $(pgrep -u "$(id -u)" -x gem5.opt); do
        exe="$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | head -1)"
        [[ "$exe" == "$GEM5_SCHEMA9" ]] || continue
        outdir="$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | sed -n 's/^--outdir=//p')"
        r="$outdir/.runner"
        printf '%s %s %s %s\n' "$pid" "$(cat "$r/profile" 2>/dev/null)" \
            "$(cat "$r/cache" 2>/dev/null)" "$(cat "$r/run_id" 2>/dev/null)"
    done
}

check_host() {
    echo "== Host check"
    [[ -x "$GEM5" ]] || die "no schema-10 gem5 at $GEM5"
    grep -aq 'runtime effective address only' "$GEM5" ||
        die "$GEM5 is not a metric-schema-10 build"
    cache_scripts/run_on_host.sh check || die "this host is not ready (see above)"
}

cmd_dry_run() {
    check_host
    build_plan
    echo
    echo "== Plan on $HOST (nothing is changed)"
    note "gem5 runs at a time: ${TOTAL:-$(recommended_total) (recommended now)}"
    local runs
    runs="$(schema9_runs)"
    if [[ -n "$runs" ]]; then
        note "schema-9 runs that start would stop ($(wc -l <<< "$runs")):"
        sed 's/^/    pid /' <<< "$runs"
    else
        note "no schema-9 runs on this host"
    fi
    alive "$(cat "$QDIR/queue.pid" 2>/dev/null)" &&
        note "this host's old queue (pid $(cat "$QDIR/queue.pid")) would be stopped"
    note "schema-9 SimPoint results to move aside: $(simpoint9_dirs | wc -l)"
    note "step 1: ${#STEP1[@]} runs: roms (train) and x264 (test) first, then the test runs:"
    printf '    %s\n' "${STEP1[@]:0:12}"
    note "    ..."
    note "step 2: ref SimPoint points: $(cache_scripts/simpoint.sh status ref 2>/dev/null |
        awk '$2 == "ok" {k += $3} END {print k * 5}') point runs ($(echo "${CONFIGS[*]}" | tr ' ' ,))"
    note "step 3: ${#STEP3[@]} train runs, longest first: ${STEP3[0]:-}, ${STEP3[5]:-}, ..."
    note "runs and points that already have a schema-10 result are skipped"
}

cmd_start() {
    alive "$(campaign_pid)" && die "the campaign already runs here (pid $(campaign_pid)); see: $0 status"
    check_host
    if [[ "${SKIP_TESTS:-0}" != 1 ]]; then
        echo
        echo "== Spill test suite"
        if [[ -x "$ASSEMBLER" ]]; then
            python3 tests/spill_test/run_tests.py || die "spill tests failed on $HOST; not starting"
        else
            note "no RISC-V assembler on this host ($ASSEMBLER): tests skipped"
        fi
    fi
    mkdir -p "$QDIR"
    echo
    echo "== Stopping this host's schema-9 runs"
    local old pid profile cache run
    old="$(cat "$QDIR/queue.pid" 2>/dev/null)"
    if alive "$old"; then kill "$old" && note "old queue (pid $old) stopped"; fi
    while read -r pid profile cache run; do
        [[ -n "$pid" ]] || continue
        if [[ -n "$profile" && -n "$cache" && -n "$run" ]]; then
            "$RUNNER" stop "$profile" "$cache" "$run" > /dev/null 2>&1
            note "stopped $profile $cache $run (pid $pid)"
        else
            note "pid $pid runs the schema-9 gem5 outside the runner: left alone"
        fi
    done < <(schema9_runs)
    sleep 5
    [[ -z "$(schema9_runs)" ]] || note "warning: schema-9 runs still alive: $(schema9_runs | awk '{print $1}' | tr '\n' ' ')"
    echo
    echo "== Moving the schema-9 SimPoint results aside"
    local d n=0 cfgdir
    while read -r d; do
        [[ -n "$d" ]] || continue
        if [[ -e "${d}_schema9" ]]; then note "kept $d: ${d}_schema9 exists"; continue; fi
        mv "$d" "${d}_schema9" || die "could not move $d"
        cfgdir="$(dirname "$d")"
        [[ -s "${d}_schema9/.runner/profile" ]] || echo ref > "${d}_schema9/.runner/profile"
        [[ -s "${d}_schema9/.runner/cache" ]] || basename "$cfgdir" > "${d}_schema9/.runner/cache"
        n=$((n + 1))
    done < <(simpoint9_dirs)
    note "$n moved to <run>_simpoint_schema9"
    TOTAL="${TOTAL:-$(recommended_total)}"
    [[ "$TOTAL" =~ ^[0-9]+$ && "$TOTAL" -gt 0 ]] || die "TOTAL must be a positive number"
    echo
    TOTAL="$TOTAL" setsid nohup bash "$0" __drive >> "$LOG" 2>&1 < /dev/null &
    local driver=$!
    echo "$driver" > "$QDIR/campaign.pid"
    echo "== Campaign started on $HOST (pid $driver), at most $TOTAL gem5 runs at a time."
    echo "   Detached: you can log out. Progress: $0 status   (or status_cache.sh from any host)"
    echo "   Log: $LOG"
}

# The detached part: the three steps one after the other.
cmd_drive() {
    build_plan
    local configs
    configs="$(IFS=,; echo "${CONFIGS[*]}")"
    # The queue files the status views read (this host's queue = the campaign).
    echo $$ > "$QDIR/queue.pid"
    date +%s > "$QDIR/queue.started"
    echo "$HOST" > "$QDIR/queue.host"
    echo "$TOTAL" > "$QDIR/queue.maxjobs"
    {
        for input in test train; do
            for cfg in "${CONFIGS[@]}"; do
                printf '%s %s %s\n' "$input" "$cfg" "$("$RUNNER" list "$input" |
                    awk 'NR > 2 && NF {print $1}' | paste -sd,)"
            done
        done
    } > "$QDIR/queue.plan"
    echo "$(stamp) campaign on $HOST, at most $TOTAL gem5 runs at a time"
    echo "$(stamp) step 1/3: roms (train) and x264 (test) first, then every test run: ${#STEP1[@]} runs"
    MAX_JOBS="$TOTAL" scripts/launch_spill_batch.sh "${STEP1[@]}" >> "$QDIR/queue.log" 2>&1
    echo "$(stamp) step 2/3: ref SimPoint points ($configs)"
    JOBS="$TOTAL" TOTAL_JOBS="$TOTAL" cache_scripts/simpoint.sh run ref "$configs" \
        >> "$QDIR/simpoint.log" 2>&1
    echo "$(stamp) step 2/3 done: $(cache_scripts/simpoint.sh status ref 2>/dev/null |
        grep -o combined | wc -l) of 180 SimPoint estimates combined"
    echo "$(stamp) step 3/3: the other train runs, longest first: ${#STEP3[@]} runs"
    MAX_JOBS="$TOTAL" scripts/launch_spill_batch.sh "${STEP3[@]}" >> "$QDIR/queue.log" 2>&1
    echo "$(stamp) every run started; the last ones finish on their own"
    rm -f "$QDIR/campaign.pid"
}

cmd_status() {
    local pid
    pid="$(campaign_pid)"
    if alive "$pid"; then echo "campaign: running on $HOST (pid $pid)"; else echo "campaign: no driver running on $HOST"; fi
    echo
    [[ -f "$LOG" ]] && { echo "== $LOG (last lines)"; tail -n 8 "$LOG"; echo; }
    [[ -f "$QDIR/queue.log" ]] && { echo "== queue.log (last starts)"; tail -n 3 "$QDIR/queue.log"; echo; }
    echo "== SimPoint (ref): estimates combined"
    cache_scripts/simpoint.sh status ref 2>/dev/null | awk 'NR > 1 {for (i = 4; i <= NF; i++) if ($i == "combined") c++; t += NF - 3}
        END {printf "  %d of %d (run, config) pairs\n", c, t}'
    echo
    echo "== gem5 runs on $HOST"
    cache_scripts/run_on_host.sh ps | sed -n '/^per input/,$p'
    echo
    echo "Coverage of every input: cache_scripts/status_cache.sh --check"
}

cmd_stop() {
    [[ "${1:-}" == --yes ]] || die "usage: $0 stop --yes   (stops the campaign and every test/train run and SimPoint point on $HOST)"
    local pid
    pid="$(campaign_pid)"
    # The driver runs in its own session: killing its process group stops it,
    # launch_spill_batch.sh, simpoint.sh and the point runs simpoint.sh started.
    if alive "$pid"; then kill -- "-$pid" 2>/dev/null || kill "$pid"; echo "campaign driver stopped"; fi
    rm -f "$QDIR/campaign.pid"
    pkill -u "$(id -u)" -f '[-]-restore-simpoint-checkpoint' && echo "SimPoint point runs stopped"
    cache_scripts/run_on_host.sh stop --yes --inputs test,train
}

case "${1:-}" in
  --dry-run) cmd_dry_run ;;
  start)     cmd_start ;;
  status)    cmd_status ;;
  stop)      shift; cmd_stop "$@" ;;
  __drive)   cmd_drive ;;
  *) sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
