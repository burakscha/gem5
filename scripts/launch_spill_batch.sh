#!/usr/bin/env bash
# Launch SPEC runs through spec_spill_runner.sh while keeping at most
# MAX_JOBS gem5 processes alive at a time.
#
# spec_spill_runner.sh start ... all fires every benchmark at once. On this
# host that is 17 gem5 processes against 6 cores / 12 threads and a ZFS ARC
# that already holds most of RAM, which is how earlier batches got
# OOM-killed. This script feeds the runner one benchmark at a time and waits
# for a slot.
#
#   ./scripts/launch_spill_batch.sh                      # test / standard, 6 at a time
#   MAX_JOBS=4 ./scripts/launch_spill_batch.sh train standard
#   ./scripts/launch_spill_batch.sh test small-2way small-fa small-dm
#   ./scripts/launch_spill_batch.sh test:small-2way train:small-fa:gcc,xz
#
# Arguments are either PROFILE CACHE [CACHE ...] or groups of the form
# PROFILE:CACHE[:RUN,RUN,...] (no run list = every run of the profile).
# All groups form one queue, in the order given: a free slot always goes to
# the next pending run, so the first group finishes first while the machine
# never idles. MAX_JOBS caps all gem5 processes on the host.

set -uo pipefail

# The repository root is one level above scripts/.
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/spec_spill_runner.sh"
MAX_JOBS="${MAX_JOBS:-6}"
POLL_SECONDS="${POLL_SECONDS:-60}"

[[ -x "$RUNNER" ]] || { echo "runner not found: $RUNNER" >&2; exit 1; }

GROUPS_LIST=()
if [[ "${1:-}" == *:* ]]; then
    GROUPS_LIST=("$@")
else
    profile="${1:-test}"
    shift || true
    for cache in "${@:-standard}"; do GROUPS_LIST+=("$profile:$cache"); done
fi

running_jobs() {
    # pgrep -c prints 0 AND exits non-zero when nothing matches, so a
    # "|| echo 0" fallback would emit two lines and break the arithmetic
    # comparison below. Count lines instead.
    # Only this user's runs: on a shared host other users' gem5 processes
    # must not take our slots. SimPoint restores (cache_scripts/simpoint.sh
    # run) are not queue runs and keep to their own JOBS limit.
    pgrep -u "$(id -u)" -af 'build/RISCV[A-Z0-9_]*/gem5.opt' 2>/dev/null |
        grep -v -- '--restore-simpoint-checkpoint' | wc -l
}

# Skip runs that are already in flight or have a CURRENT-schema result, so
# the script can be re-run to top up or resume a queue. A COMPLETED run from
# an older detector schema does not count: it has to be produced again.
already_handled() {
    local profile="$1" cache="$2" run_id="$3" benchmark="$4" state log
    state="$("$RUNNER" status "$profile" "$cache" "$run_id" 2>/dev/null | sed -n '3p')"
    case "$state" in
        *RUNNING*|*STARTING*) return 0 ;;
        *COMPLETED*)
            log="$ROOT_DIR/benchmarks/$benchmark/m5out_$benchmark/latest_${profile}_${cache}_${run_id}/riscv_spill_stats.txt"
            grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*10$' "$log" 2>/dev/null
            return $?
            ;;
        *) return 1 ;;
    esac
}

printf 'Queue: %s; at most %s concurrent.\n' "${GROUPS_LIST[*]}" "$MAX_JOBS"

for group in "${GROUPS_LIST[@]}"; do
    IFS=: read -r profile cache runs <<< "$group"
    mapfile -t specs < <("$RUNNER" list "$profile" | awk 'NR>2 && NF {print $1, $2}')
    (( ${#specs[@]} > 0 )) || { echo "no run IDs for profile $profile" >&2; continue; }
    for spec in "${specs[@]}"; do
        read -r run_id benchmark <<< "$spec"
        if [[ -n "$runs" && ",$runs," != *",$run_id,"* ]]; then
            continue
        fi
        if [[ "${FORCE:-0}" != 1 ]] && already_handled "$profile" "$cache" "$run_id" "$benchmark"; then
            printf '[%(%H:%M:%S)T] skipping %s:%s/%s (already running or completed)\n' -1 "$profile" "$cache" "$run_id"
            continue
        fi
        while (( $(running_jobs) >= MAX_JOBS )); do
            sleep "$POLL_SECONDS"
        done
        printf '[%(%H:%M:%S)T] starting %s:%s/%s (%s running)\n' -1 "$profile" "$cache" "$run_id" "$(running_jobs)"
        "$RUNNER" start "$profile" "$cache" "$run_id" >/dev/null 2>&1 || \
            printf '  WARNING: could not start %s:%s/%s\n' "$profile" "$cache" "$run_id" >&2
        sleep 5
    done
done

printf '[%(%H:%M:%S)T] all runs queued (%s).\n' -1 "${GROUPS_LIST[*]}"
