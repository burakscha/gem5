#!/usr/bin/env bash
# Stop castdata's cache experiment queue (start_all.sh): first the queue (no
# new runs start), then every run of its plan that runs on this host. Runs on
# other hosts are left alone (stop those with run_on_host.sh stop there).
# Finished results are kept; start_all.sh later resumes the rest.
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
LOGDIR="$ROOT/logs/cache_runs"
if [[ -f "$LOGDIR/queue.host" && "$(cat "$LOGDIR/queue.host")" != "$(hostname)" ]]; then
    echo "The queue runs on $(cat "$LOGDIR/queue.host"); log in there to stop it."
    exit 1
fi
if [[ "${1:-}" != "--yes" ]]; then
    echo "usage: $0 --yes   (stops the queue and the runs of its plan on this host)"
    exit 2
fi
if [[ -f "$LOGDIR/queue.pid" ]] && kill -0 "$(cat "$LOGDIR/queue.pid")" 2>/dev/null; then
    kill "$(cat "$LOGDIR/queue.pid")" && echo "queue stopped"
fi
while read -r input cache _; do
    "$ROOT/scripts/spec_spill_runner.sh" stop "$input" "$cache" all
done < "$LOGDIR/queue.plan"
