#!/usr/bin/env bash
# Run the cache experiment on any host that mounts /cta/users at the same
# path (castdata, cast1-3, epic, xeon): one entry point to check the host,
# validate gem5 on it, and start a detached queue sized to its cores.
#
#   cache_scripts/run_on_host.sh check                  is this host ready? (changes nothing)
#   cache_scripts/run_on_host.sh test                   spill_test suite (27 cases) with gem5 here
#   cache_scripts/run_on_host.sh smoke INPUT            5M-instruction trial of every run x config
#   cache_scripts/run_on_host.sh start INPUTS [opts]    start this host's queue (detached)
#   cache_scripts/run_on_host.sh all INPUTS [opts]      check + test + smoke + start, in one go
#   cache_scripts/run_on_host.sh status [view]          = cache_scripts/status_cache.sh [view]
#   cache_scripts/run_on_host.sh ps                     this host's running runs: input, config, run
#   cache_scripts/run_on_host.sh stop --yes [--inputs ref]  stop this host's queue and every run on it
#                                                       (--inputs: only the runs of these inputs)
#
#   INPUTS   test, train, ref or a comma list (ref: full runs, no SimPoint)
#   opts     --configs small-2way,small-fa,...  (default: the five small-* configs)
#            --jobs N    this user's gem5 runs on the host in total (default: see check)
#            --restart   replace this host's running queue (its gem5 runs go on)
#            --runs a,b  (start) only these run IDs of the INPUTS
#            --dry-run   (start) show the queue it would start, start nothing
#            --order merged|input   (start) merged (default): the runs of all
#                        INPUTS longest first in one list; input: INPUTS in
#                        the given order, each longest first (test,train =
#                        every test run before the first waiting train run)
#
# Hosts share the result directories: a run started on one host shows as
# RUNNING everywhere and every other queue skips it, so two hosts never run
# the same workload. Results do not depend on the host (same gem5 binary,
# same inputs; the simulation is deterministic).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
RUNNER="$ROOT/scripts/spec_spill_runner.sh"
GEM5="${GEM5_BIN:-$ROOT/build/RISCV_SCHEMA10/gem5.opt}"
TOOLS=/cta/research/level0/RISCV
LOGDIR="$ROOT/logs/cache_runs"
HOST="$(hostname)"
QDIR="$LOGDIR/hosts/$HOST"
CONFIGS="small-2way,small-fa,small-dm,small-4way,small-8way"
MEM_PER_JOB_GB="${MEM_PER_JOB_GB:-2}"     # gem5 RSS seen so far: 0.4-1 GB
cd "$ROOT" || exit 1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
ok()  { printf '  [ok]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; FAILS=$((FAILS + 1)); }
note(){ printf '  [info] %s\n' "$*"; }

# The --jobs value for this host. MAX_JOBS caps this user's gem5 processes
# in total, so it is the runs already going plus what fits beside them:
# physical cores (gem5 is CPU-bound; two runs on one core's SMT siblings slow
# each other down, and the longest run decides the finish) minus the current
# load minus 2 spare, and MEM_PER_JOB_GB of free memory per extra run.
physical_cores() {
    lscpu -p=CORE,SOCKET 2>/dev/null | grep -v '^#' | sort -u | wc -l
}
own_runs() {
    # -x matches the process name, so shells that merely mention gem5 do not count
    pgrep -c -u "$(id -u)" -x gem5.opt 2>/dev/null || true
}
recommended_jobs() {
    local cores load mem_gb own by_cpu by_mem jobs
    cores=$(physical_cores); (( cores > 0 )) || cores=$(nproc)
    load=$(awk '{printf "%d", $1 + 0.999}' /proc/loadavg)
    mem_gb=$(awk '/^MemAvailable:/ {printf "%d", $2 / 1048576}' /proc/meminfo)
    own=$(own_runs); own=${own:-0}
    by_cpu=$(( cores - load - 2 ))
    by_mem=$(( mem_gb / MEM_PER_JOB_GB ))
    jobs=$(( by_cpu < by_mem ? by_cpu : by_mem ))
    (( jobs < 0 )) && jobs=0
    jobs=$(( own + jobs ))
    (( jobs < 1 )) && jobs=1
    printf '%d' "$jobs"
}

queue_alive() {
    local pid
    pid="$(cat "$QDIR/queue.pid" 2>/dev/null)"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

cmd_check() {
    FAILS=0
    echo "Host check: $HOST   ($(date '+%Y-%m-%d %H:%M'))"
    echo
    echo "Machine"
    note "CPU: $(lscpu | sed -n 's/^Model name: *//p' | head -1), $(physical_cores) physical cores, $(nproc) logical CPUs"
    note "memory: $(awk '/^MemTotal:/ {printf "%d", $2/1048576}' /proc/meminfo) GB total, $(awk '/^MemAvailable:/ {printf "%d", $2/1048576}' /proc/meminfo) GB available"
    note "load average: $(cut -d' ' -f1-3 /proc/loadavg)   OS: $(. /etc/os-release; echo "$PRETTY_NAME")"
    local glibc
    glibc="$(ldd --version 2>/dev/null | head -1 | grep -o '[0-9]\+\.[0-9]\+$')"
    if [[ -n "$glibc" ]] && awk -v v="$glibc" 'BEGIN { exit !(v + 0 >= 2.35) }'; then
        ok "glibc $glibc (gem5 was built against 2.35)"
    else
        bad "glibc ${glibc:-unknown}: gem5 was built on glibc 2.35 and needs at least that"
    fi
    echo
    echo "Shared files"
    [[ "$ROOT" == /cta/users/* ]] && ok "repository at $ROOT" || bad "repository not under /cta/users: $ROOT"
    if [[ -f "$LOGDIR/queue.host" ]]; then
        ok "castdata's queue files are visible (queue started on $(cat "$LOGDIR/queue.host"))"
    else
        note "no castdata queue files under $LOGDIR"
    fi
    local probe
    if probe="$(mktemp -p "$LOGDIR" .write_test.XXXXXX 2>/dev/null)"; then
        rm -f "$probe"; ok "result directories are writable"
    else
        bad "cannot write $LOGDIR"
    fi
    [[ -d /cta/users/bkaya/miniconda3/envs/gem5_env/lib ]] &&
        ok "conda environment of gem5 (its libraries) is visible" ||
        bad "/cta/users/bkaya/miniconda3/envs/gem5_env/lib missing: gem5 cannot load its libraries"
    echo
    echo "gem5"
    if [[ -x "$GEM5" ]]; then
        local missing
        missing="$(ldd "$GEM5" 2>/dev/null | grep 'not found')"
        [[ -z "$missing" ]] && ok "all shared libraries of gem5.opt resolve" ||
            bad "unresolved libraries: $(echo "$missing" | awk '{print $1}' | tr '\n' ' ')"
        if "$GEM5" --help >/dev/null 2>&1; then ok "gem5.opt starts"; else bad "gem5.opt does not start"; fi
    else
        bad "no gem5 binary at $GEM5"
    fi
    for t in riscv64-unknown-linux-gnu-as riscv64-unknown-linux-gnu-ld qemu-riscv64; do
        [[ -x "$TOOLS/bin/$t" ]] && ok "$t (for the spill tests / qemu checks)" ||
            note "$TOOLS/bin/$t missing: 'test' cannot run here (simulation itself does not need it)"
    done
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null &&
        ok "python3 $(python3 -c 'import platform; print(platform.python_version())')" ||
        bad "python3 >= 3.8 needed for the status script and the tests"
    echo
    echo "Workloads (binaries, inputs, stack PC maps)"
    local input out
    for input in test train; do
        out="$("$RUNNER" check "$input" small-2way all 2>&1)"
        if echo "$out" | grep -q 'failures: 0'; then
            ok "$input: $(echo "$out" | grep -o 'Checked: [0-9]*') runs, all present"
        else
            bad "$input: $(echo "$out" | tail -1)"
        fi
    done
    echo
    echo "Parallel runs"
    note "recommended --jobs $(recommended_jobs)   (your $(own_runs) running gem5 runs + free physical cores minus 2,"
    note "                       capped by ${MEM_PER_JOB_GB} GB of free memory per run; --jobs is the total, not extra)"
    if queue_alive; then note "this host already runs a queue (pid $(cat "$QDIR/queue.pid"))"; fi
    echo
    if (( FAILS )); then echo "NOT READY: $FAILS check(s) failed."; return 1; fi
    echo "READY."
}

cmd_test() {
    [[ -x "$TOOLS/bin/riscv64-unknown-linux-gnu-as" ]] ||
        die "the RISC-V assembler is not visible on this host ($TOOLS); the tests need it"
    echo "spill_test suite with gem5 on $HOST (27 cases)"
    python3 tests/spill_test/run_tests.py "$@"
}

parse_opts() {
    JOBS=""; RESTART=0; DRY=0; ORDER=merged; RUNS=""
    while (( $# )); do
        case "$1" in
          --order)   ORDER="${2:?--order needs merged or input}"; shift 2
                     [[ "$ORDER" == merged || "$ORDER" == input ]] || die "--order: merged or input" ;;
          --dry-run) DRY=1; shift ;;
          --configs) CONFIGS="${2:?--configs needs a list}"; shift 2 ;;
          --jobs)    JOBS="${2:?--jobs needs a number}"; shift 2 ;;
          --restart) RESTART=1; shift ;;
          --runs)    RUNS="${2:?--runs needs a list of run IDs}"; shift 2 ;;
          *) die "unknown option: $1" ;;
        esac
    done
    [[ -z "$JOBS" ]] && JOBS="$(recommended_jobs)"
    [[ "$JOBS" =~ ^[0-9]+$ ]] || die "--jobs must be a number"
}

cmd_smoke() {
    local input="${1:?usage: $0 smoke INPUT [--configs ...] [--jobs N]}"; shift
    parse_opts "$@"
    mkdir -p "$QDIR"
    IFS=, read -r -a cfgs <<< "$CONFIGS"
    OUT="$QDIR/smoke" PROFILE="$input" JOBS="$JOBS" MAXINSTS="${MAXINSTS:-5000000}" \
        cache_scripts/smoke_test.sh "${cfgs[@]}"
    ! grep -qs FAIL "$QDIR"/smoke/*/*/RESULT
}

# "input run" for every run of the given input sets, longest first by the
# qemu instruction count (logs/qemu/<input>/<run>/RESULT; a run without a
# count goes first). The sets are merged, so the longest runs of all of them
# start first and none of them starts last.
runs_longest_first() {
    local input run n
    for input in "$@"; do
        "$RUNNER" list "$input" | awk 'NR > 2 && NF {print $1}' | while read -r run; do
            n="$(awk '{print $3}' "$ROOT/logs/qemu/$input/$run/RESULT" 2>/dev/null)"
            printf '%s %s %s\n' "${n:-999999999999999}" "$input" "$run"
        done
    done | sort -k1,1nr | awk '{print $2, $3}'
}

cmd_start() {
    local inputs="${1:?usage: $0 start INPUTS [--configs ...] [--jobs N] [--restart]}"; shift
    parse_opts "$@"
    local input cache run
    if (( ! DRY )) && [[ -f "$LOGDIR/queue.host" && "$(cat "$LOGDIR/queue.host")" == "$HOST" ]] &&
       kill -0 "$(cat "$LOGDIR/queue.pid" 2>/dev/null)" 2>/dev/null; then
        die "start_all.sh's queue already runs on this host; use start_all.sh here"
    fi
    (( DRY )) || mkdir -p "$QDIR"
    if queue_alive && (( ! DRY )); then
        (( RESTART )) || die "this host's queue already runs (pid $(cat "$QDIR/queue.pid")); add --restart to replace it"
        kill "$(cat "$QDIR/queue.pid")" && echo "Stopped the old queue of $HOST (its gem5 runs go on)."
    fi
    IFS=, read -r -a cfgs <<< "$CONFIGS"
    IFS=, read -r -a ins <<< "$inputs"
    local -a groups=() plan=()
    # Runs whose binary or inputs are missing are left out (with a notice);
    # start again once they exist (--restart keeps everything running).
    local -A blocked=()
    local bad
    for input in "${ins[@]}"; do
        for cache in "${cfgs[@]}"; do plan+=("$input $cache${RUNS:+ $RUNS}"); done
        for bad in $("$RUNNER" check "$input" "${cfgs[0]}" all 2>&1 |
                     awk '/^\[/ {id = $1; gsub(/[][]/, "", id)} /FAILED$/ {print id}'); do
            blocked["$input:$bad"]=1
            echo "notice: $input/$bad left out: its binary or inputs are missing ($RUNNER check $input ${cfgs[0]} $bad)"
        done
    done
    # One group per run and configuration, longest runs first: of all inputs
    # together (--order merged) or input by input (--order input).
    local -a sets=()
    if [[ "$ORDER" == input ]]; then sets=("${ins[@]}"); else sets=("${ins[*]}"); fi
    local set
    for set in "${sets[@]}"; do
        while read -r input run; do
            [[ -n "${blocked[$input:$run]:-}" ]] && continue
            [[ -n "$RUNS" && ",$RUNS," != *",$run,"* ]] && continue
            for cache in "${cfgs[@]}"; do groups+=("$input:$cache:$run"); done
        done < <(runs_longest_first $set)
    done
    if (( DRY )); then
        echo "Dry run on $HOST: ${#groups[@]} runs, at most $JOBS at a time, in this order:"
        printf '  %s\n' "${groups[@]}" | head -20
        (( ${#groups[@]} > 20 )) && echo "  ... ($(( ${#groups[@]} - 20 )) more)"
        return 0
    fi
    printf '%s\n' "${plan[@]}" > "$QDIR/queue.plan"
    MAX_JOBS="$JOBS" setsid nohup ./scripts/launch_spill_batch.sh "${groups[@]}" \
        > "$QDIR/queue.log" 2>&1 < /dev/null &
    echo $! > "$QDIR/queue.pid"
    date +%s > "$QDIR/queue.started"
    echo "$HOST" > "$QDIR/queue.host"
    echo "$JOBS" > "$QDIR/queue.maxjobs"
    echo "Queue started on $HOST (pid $!): inputs $inputs, configs $CONFIGS,"
    echo "${#groups[@]} runs, at most $JOBS at a time, longest first. Detached: you can log out."
    echo "Queue log : $QDIR/queue.log"
    echo "Overview  : cache_scripts/status_cache.sh   (from any host)"
}

cmd_ps() {
    # This host's gem5 processes, each mapped to its run through --outdir.
    local pid outdir r now
    now=$(date +%s)
    printf '%-6s %-11s %-22s %-11s %-9s %s\n' INPUT CONFIG RUN BENCHMARK ELAPSED OUTDIR
    for pid in $(pgrep -u "$(id -u)" -x gem5.opt); do
        outdir="$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | sed -n 's/^--outdir=//p')"
        r="$outdir/.runner"
        [[ -d "$r" ]] || continue
        local start el
        start="$(cat "$r/started.epoch" 2>/dev/null || echo "$now")"
        el=$(( now - start ))
        printf '%-6s %-11s %-22s %-11s %3dd%02dh%02dm %s\n' \
            "$(cat "$r/profile")" "$(cat "$r/cache")" "$(cat "$r/run_id")" \
            "$(cat "$r/benchmark")" $(( el / 86400 )) $(( el % 86400 / 3600 )) $(( el % 3600 / 60 )) \
            "${outdir#"$ROOT"/}"
    done | sort
    echo
    echo "per input on $HOST:"
    for pid in $(pgrep -u "$(id -u)" -x gem5.opt); do
        outdir="$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | sed -n 's/^--outdir=//p')"
        cat "$outdir/.runner/profile" 2>/dev/null
    done | sort | uniq -c | awk '{printf "  %-6s %d running\n", $2, $1}'
}

cmd_stop() {
    [[ "${1:-}" == --yes ]] || die "usage: $0 stop --yes [--inputs test,train,ref]   (stops $HOST's queue and its runs)"
    local inputs=test,train,ref
    [[ "${2:-}" == --inputs ]] && inputs="${3:?--inputs needs a list}"
    if queue_alive; then kill "$(cat "$QDIR/queue.pid")" && echo "queue of $HOST stopped"; fi
    # Every run of INPUTS on this host, whichever queue started it (runs on
    # other hosts are skipped by the runner).
    local input cache
    IFS=, read -r -a cfgs <<< "$CONFIGS"
    for input in ${inputs//,/ }; do
        for cache in "${cfgs[@]}"; do
            "$RUNNER" stop "$input" "$cache" all 2>&1 | grep -v 'not running\|runs on '
        done
    done
    return 0
}

case "${1:-}" in
  check)  shift; cmd_check "$@" ;;
  test)   shift; cmd_test "$@" ;;
  smoke)  shift; cmd_smoke "$@" ;;
  start)  shift; cmd_start "$@" ;;
  status) shift; exec cache_scripts/status_cache.sh "$@" ;;
  stop)   shift; cmd_stop "$@" ;;
  ps)     shift; cmd_ps ;;
  all)
    shift
    inputs="${1:?usage: $0 all INPUTS [--configs ...] [--jobs N]}"
    cmd_check || exit 1
    echo; cmd_test || die "spill tests failed on $HOST; not starting"
    for input in ${inputs//,/ }; do
        echo; cmd_smoke "$input" "${@:2}" || die "smoke test failed for $input; not starting"
    done
    echo; cmd_start "$@"
    ;;
  *) sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
