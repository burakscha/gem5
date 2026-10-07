#!/usr/bin/env bash
# Launch every SPEC run for a profile/cache through spec_spill_runner.sh while
# keeping at most MAX_JOBS gem5 processes alive at a time.
#
# spec_spill_runner.sh start ... all fires every benchmark at once. On this
# host that is 17 gem5 processes against 12 cores and a ZFS ARC that already
# holds most of RAM, which is how earlier batches got OOM-killed. This script
# feeds the runner one benchmark at a time and waits for a slot.
#
#   ./scripts/launch_spill_batch.sh                      # test / standard, 6 at a time
#   MAX_JOBS=4 ./scripts/launch_spill_batch.sh train standard
#   ./scripts/launch_spill_batch.sh test small

set -uo pipefail

# The repository root is one level above scripts/.
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/spec_spill_runner.sh"
PROFILE="${1:-test}"
CACHE="${2:-standard}"
MAX_JOBS="${MAX_JOBS:-6}"
POLL_SECONDS="${POLL_SECONDS:-60}"

[[ -x "$RUNNER" ]] || { echo "runner not found: $RUNNER" >&2; exit 1; }

running_jobs() {
    # pgrep -c prints 0 AND exits non-zero when nothing matches, so a
    # "|| echo 0" fallback would emit two lines and break the arithmetic
    # comparison below. Count lines instead.
    pgrep -f 'build/RISCV/gem5.opt' 2>/dev/null | wc -l
}

# Skip benchmarks that already have a run in flight or a CURRENT-schema
# result, so the script can be re-run to top up a partially launched batch.
# A COMPLETED run from an older detector schema does not count: its numbers
# use the retired counter names and have to be produced again.
already_handled() {
    local run_id="$1" benchmark="$2" state log
    state="$("$RUNNER" status "$PROFILE" "$CACHE" "$run_id" 2>/dev/null | sed -n '3p')"
    case "$state" in
        *RUNNING*|*STARTING*) return 0 ;;
        *COMPLETED*)
            log="$ROOT_DIR/benchmarks/$benchmark/m5out_$benchmark/latest_${PROFILE}_${CACHE}_${run_id}/riscv_spill_stats.txt"
            grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*7$' "$log" 2>/dev/null
            return $?
            ;;
        *) return 1 ;;
    esac
}

mapfile -t RUN_SPECS < <("$RUNNER" list "$PROFILE" | awk 'NR>2 && NF {print $1, $2}')
(( ${#RUN_SPECS[@]} > 0 )) || { echo "no run IDs for profile $PROFILE" >&2; exit 1; }

printf 'Queueing %d runs (%s/%s), at most %s concurrent.\n' \
    "${#RUN_SPECS[@]}" "$PROFILE" "$CACHE" "$MAX_JOBS"

for spec in "${RUN_SPECS[@]}"; do
    read -r run_id benchmark <<< "$spec"
    if [[ "${FORCE:-0}" != 1 ]] && already_handled "$run_id" "$benchmark"; then
        printf '[%(%H:%M:%S)T] skipping %s (already running or completed)\n' -1 "$run_id"
        continue
    fi
    while (( $(running_jobs) >= MAX_JOBS )); do
        sleep "$POLL_SECONDS"
    done
    printf '[%(%H:%M:%S)T] starting %s (%s running)\n' -1 "$run_id" "$(running_jobs)"
    "$RUNNER" start "$PROFILE" "$CACHE" "$run_id" >/dev/null 2>&1 || \
        printf '  WARNING: could not start %s\n' "$run_id" >&2
    sleep 5
done

printf '[%(%H:%M:%S)T] all %d runs queued.\n' -1 "${#RUN_SPECS[@]}"
printf 'Track them with: ./scripts/spec_spill_runner.sh status %s %s all\n' "$PROFILE" "$CACHE"
printf 'Report them with: ./scripts/spill_report.sh --profile %s --cache %s\n' "$PROFILE" "$CACHE"
