#!/usr/bin/env bash
# Start the cache organisation experiment as ONE queue of at most MAX_JOBS
# (default 8) gem5 runs at a time. A free slot always takes the next pending
# run in QUEUE order, so earlier groups finish first and the machine never
# idles. The host has 6 cores / 12 threads and ~8 GB of free memory; more
# than ~8 runs has run it out of memory before.
#
# Runs detached (setsid nohup): closing Claude Code, the terminal or the
# laptop does not stop it. Safe to run again: running or completed runs are
# skipped, so it also resumes after a reboot.
#
#   cache_scripts/start_all.sh             start (refuses if the queue runs)
#   cache_scripts/start_all.sh --restart   replace the running queue with the
#                                          QUEUE below; running gem5 runs go on
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
LOGDIR="$ROOT/logs/cache_runs"
mkdir -p "$LOGDIR"
cd "$ROOT"

# The queue, in order: INPUT:CACHE[:RUN,RUN,...]; a group without a run list
# takes every run of the input set (scripts/spec_spill_runner.sh list INPUT).
# The SPEC `test` set first, then `train`, each under the five L1D/L2
# organisations (small sizes: L1D 4 KiB, L2 32 KiB).
CONFIGS=(small-2way small-fa small-dm small-4way small-8way)
INPUTS=(test train)
# Within an input set these start first under every configuration: x264
# (~475e9 instructions on test, about 6 days per run under load) must not be
# the last run to begin. Later groups skip a run once it is running.
LONG_RUNS=x264
PLAN=()
QUEUE=()
for input in "${INPUTS[@]}"; do
    for cache in "${CONFIGS[@]}"; do QUEUE+=("$input:$cache:$LONG_RUNS"); done
    for cache in "${CONFIGS[@]}"; do PLAN+=("$input:$cache"); QUEUE+=("$input:$cache"); done
done

if [[ -f "$LOGDIR/queue.host" && "$(cat "$LOGDIR/queue.host")" != "$(hostname)" ]] &&
   [[ "$(cat "$LOGDIR/queue.pid" 2>/dev/null)" ]]; then
    echo "The queue was started on $(cat "$LOGDIR/queue.host"); run this there."
    echo "(Starting it here too would run every benchmark twice.)"
    exit 1
fi
if [[ -f "$LOGDIR/queue.pid" ]] && kill -0 "$(cat "$LOGDIR/queue.pid")" 2>/dev/null; then
    if [[ "${1:-}" != "--restart" ]]; then
        echo "The queue is already running (pid $(cat "$LOGDIR/queue.pid"))."
        echo "Follow it with: cache_scripts/status_cache.sh"
        echo "Replace it with the QUEUE of this script: $0 --restart"
        exit 0
    fi
    kill "$(cat "$LOGDIR/queue.pid")"
    echo "Stopped the old queue (its running gem5 runs continue)."
fi

# Pre-flight: binaries, inputs and stack PC maps of every queued input set.
for input in "${INPUTS[@]}"; do
    ./scripts/spec_spill_runner.sh check "$input" "${CONFIGS[0]}" all
done

# What the status script shows: one "input cache [runs]" line per group.
printf '%s\n' "${PLAN[@]}" | tr ':' ' ' > "$LOGDIR/queue.plan"

MAX_JOBS="${MAX_JOBS:-8}" setsid nohup ./scripts/launch_spill_batch.sh \
    "${QUEUE[@]}" > "$LOGDIR/queue.log" 2>&1 < /dev/null &
echo $! > "$LOGDIR/queue.pid"
date +%s > "$LOGDIR/queue.started"
hostname > "$LOGDIR/queue.host"
echo "${MAX_JOBS:-8}" > "$LOGDIR/queue.maxjobs"
echo "Queue started (pid $!, at most ${MAX_JOBS:-8} runs at a time):"
printf '  %s\n' "${QUEUE[@]}"
echo "Queue log : $LOGDIR/queue.log"
echo "Overview  : cache_scripts/status_cache.sh"
