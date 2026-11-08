#!/usr/bin/env bash
# Short trial of every SPEC `test` workload under each cache configuration:
# MAXINSTS instructions (default 5 million) with exactly the command line the
# runner uses (binary, inputs, cache options, stack PC map). A workload or a
# configuration that would fail shows up in minutes instead of hours into the
# real run. Output goes to logs/cache_runs/smoke/; the real runs are untouched.
#
#   cache_scripts/smoke_test.sh                  # 3 configs x 17 workloads
#   cache_scripts/smoke_test.sh small-fa         # one configuration
#   JOBS=1 MAXINSTS=2000000 cache_scripts/smoke_test.sh
#   RUNS=x264,mcf cache_scripts/smoke_test.sh    # only these run IDs
#   PROFILE=train cache_scripts/smoke_test.sh    # another input set
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
RUNNER="$ROOT/scripts/spec_spill_runner.sh"
# The runner's own functions (manifest, cache_options,
# prepare_omnet_ini, prepare_run_dir, stdin handling), without running its main.
source <(sed -e '$d' -e "s|^SCRIPT_PATH=.*|SCRIPT_PATH='$RUNNER'|" "$RUNNER")
ROOT_DIR="$ROOT"
GEM5_BIN="${GEM5_BIN:-$ROOT/build/RISCV_SCHEMA10/gem5.opt}"
GEM5_CONFIG="$ROOT/configs/deprecated/example/se.py"
MAXINSTS="${MAXINSTS:-5000000}"
JOBS="${JOBS:-2}"
RUNS="${RUNS:-}"
OUT="${OUT:-$ROOT/logs/cache_runs/smoke}"
if (( $# )); then CONFIGS=("$@"); else CONFIGS=(small-2way small-fa small-dm); fi
cd "$ROOT" || exit 1

smoke_one() {
    local cache="$1" run_id="$2" binary="$3" options="$4" omnet_ini="$5" run_src="$6"
    local outdir="$OUT/$cache/$run_id" start result workdir="$ROOT" cmd_path="$ROOT/$binary"
    rm -rf "$outdir"; mkdir -p "$outdir"
    prepare_omnet_ini "$omnet_ini" "$outdir"
    options="${options//\{OUTDIR\}/$outdir}"
    if [[ -n "$run_src" ]]; then
        workdir="$outdir/run"
        prepare_run_dir "$run_src" "$workdir"
        cmd_path="$(link_run_binary "$binary" "$workdir")"
    fi
    local -a stdin_args=()
    if [[ -n "$(stdin_file "$options")" ]]; then
        stdin_args=("--input=$workdir/$(stdin_file "$options")")
        options="$(strip_stdin "$options")"
    fi
    start=$(date +%s)
    # shellcheck disable=SC2046 -- cache options must split into words
    (cd "$workdir" && "$GEM5_BIN" "--outdir=$outdir" "$GEM5_CONFIG" "--cmd=$cmd_path" \
        "--options=$options" "${stdin_args[@]}" $(cache_options "$cache") \
        "--maxinsts=$MAXINSTS" > "$outdir/gem5.log" 2>&1)
    local rc=$?
    if grep -q "reached the max instruction count" "$outdir/gem5.log"; then
        result="OK"
    elif (( rc == 0 )) && grep -q "exiting with last active thread context" "$outdir/gem5.log"; then
        result="OK (ended before ${MAXINSTS})"
    else
        result="FAIL: $(grep -m1 -iE 'fatal|panic|error|abort|cannot|No such' "$outdir/gem5.log" | cut -c1-80)"
    fi
    printf '%-11s %-15s %4ss  %s\n' "$cache" "$run_id" "$(( $(date +%s) - start ))" "$result" \
        | tee "$outdir/RESULT"
}

printf 'Smoke test: %s instructions per run, %s at a time, configs: %s\n' \
    "$MAXINSTS" "$JOBS" "${CONFIGS[*]}"
for cache in "${CONFIGS[@]}"; do
    valid_cache "$cache" || { echo "unknown cache profile: $cache" >&2; exit 2; }
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        [[ -z "$RUNS" || ",$RUNS," == *",$run_id,"* ]] || continue
        while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
        smoke_one "$cache" "$run_id" "$binary" "$options" "$omnet_ini" "$run_src" &
    done < <(manifest "${PROFILE:-test}")
done
wait
total=$(cat "$OUT"/*/*/RESULT 2>/dev/null | grep -c .)
failed=$(cat "$OUT"/*/*/RESULT 2>/dev/null | grep -c 'FAIL')
printf '\n%s runs, %s failed. Logs: %s/<config>/<run>/gem5.log\n' "$total" "$failed" "$OUT"
