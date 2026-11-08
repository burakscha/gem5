#!/usr/bin/env bash
# Run every workload of an input set natively fast under qemu-riscv64, with
# the runner's exact command line, and count its guest instructions. It shows
# in minutes that a workload runs to the end and how long gem5 will take
# (gem5's total_insts equals the qemu count to ~0.002%; checked on mcf test).
# m5ops are custom-3 instructions qemu does not know, so each binary runs as
# a copy with its m5ops patched to NOPs. Output: logs/qemu/<input>/<run>/.
#
#   cache_scripts/qemu_count.sh train              # every train workload
#   cache_scripts/qemu_count.sh test bwaves wrf    # selected run IDs
#   JOBS=2 RATE=1.2e6 cache_scripts/qemu_count.sh train
#
# RATE is the gem5 speed used for the estimate (instructions per second;
# default 0.9e6, what the small-* runs reach with 8 gem5 runs on the host).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
RUNNER="$ROOT/scripts/spec_spill_runner.sh"
source <(sed -e '$d' -e "s|^SCRIPT_PATH=.*|SCRIPT_PATH='$RUNNER'|" "$RUNNER")
ROOT_DIR="$ROOT"
TOOLS=/cta/research/level0/RISCV
QEMU="$TOOLS/bin/qemu-riscv64"
HOST_CC="${HOST_CC:-/cta/users/bkaya/miniconda3/envs/gem5_env/bin/x86_64-conda-linux-gnu-gcc}"
JOBS="${JOBS:-3}"
RATE="${RATE:-0.9e6}"
PROFILE="${1:?usage: $0 PROFILE [RUN_ID...]}"; shift
OUT="$ROOT/logs/qemu"
PLUGIN="$OUT/libinsncount.so"
# Inputs the runner's command lines reach relative to the gem5 root.
LINKS=(benchmarks aminos gcn4dna hkrdenq 1am0 dictionary WORDS ned)
cd "$ROOT" || exit 1
mkdir -p "$OUT/bin"

if [[ ! -f "$PLUGIN" || "$ROOT/cache_scripts/qemu/insncount.c" -nt "$PLUGIN" ]]; then
    # qemu-plugin.h includes <glib.h> for two types only; the host has no glib.
    mkdir -p "$OUT/fakeglib"
    printf 'typedef struct _GArray GArray;\ntypedef struct _GByteArray GByteArray;\n' \
        > "$OUT/fakeglib/glib.h"
    "$HOST_CC" -shared -fPIC -O2 -I"$OUT/fakeglib" -I"$TOOLS/include" \
        -o "$PLUGIN" "$ROOT/cache_scripts/qemu/insncount.c" || exit 1
fi

count_one() {
    local run_id="$1" binary="$2" options="$3" omnet_ini="$4" run_src="$5"
    local dir="$OUT/$PROFILE/$run_id" qbin="$OUT/bin/$(basename "$binary" .riscv).q"
    local stdin_path start rc workdir
    rm -rf "$dir"; mkdir -p "$dir"
    prepare_omnet_ini "$omnet_ini" "$dir"
    options="${options//\{OUTDIR\}/$dir}"
    if [[ -n "$run_src" ]]; then
        workdir="$dir/run"
        prepare_run_dir "$run_src" "$workdir"
        qbin="$(link_run_binary "$binary" "$workdir" "$qbin")"
    else
        # Stands in for the gem5 root: the inputs, but its own output files.
        workdir="$dir"
        for l in "${LINKS[@]}"; do [[ -e "$ROOT/$l" ]] && ln -s "$ROOT/$l" "$dir/$l"; done
    fi
    stdin_path="$(stdin_file "$options")"
    options="$(strip_stdin "$options")"
    start=$(date +%s)
    (
        cd "$workdir" || exit 1
        # shellcheck disable=SC2086 -- options split into argv like se.py does
        "$QEMU" -plugin "$PLUGIN,out=$dir/insn_count" "$qbin" $options \
            < "${stdin_path:-/dev/null}" > "$dir/stdout.txt" 2> "$dir/stderr.txt"
    )
    rc=$?
    printf '%s %s %s\n' "$rc" "$(( $(date +%s) - start ))" "$(cat "$dir/insn_count" 2>/dev/null || echo 0)" \
        > "$dir/RESULT"
}

declare -A seen
printf 'qemu instruction count: input %s, %s at a time\n' "$PROFILE" "$JOBS"
while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
    if (( $# )) && [[ " $* " != *" $run_id "* ]]; then continue; fi
    if [[ -z "${seen[$binary]:-}" ]]; then
        python3 "$ROOT/cache_scripts/qemu/patch_m5ops.py" "$ROOT/$binary" \
            "$OUT/bin/$(basename "$binary" .riscv).q" > /dev/null || exit 1
        seen[$binary]=1
    fi
    while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
    count_one "$run_id" "$binary" "$options" "$omnet_ini" "$run_src" &
done < <(manifest "$PROFILE")
wait

printf '\n%-22s %4s %8s %18s %12s\n' run exit qemu_s instructions gem5_est
total=0
while IFS=$'\x1f' read -r run_id _; do
    f="$OUT/$PROFILE/$run_id/RESULT"
    [[ -f "$f" ]] || continue
    read -r rc secs insts < "$f"
    total=$(( total + insts ))
    printf '%-22s %4s %8s %18s %12s\n' "$run_id" "$rc" "$secs" \
        "$(python3 -c "print(f'{$insts:,}')")" \
        "$(python3 -c "h=$insts/$RATE/3600; print(f'{h:.1f} h' if h < 48 else f'{h/24:.1f} d')")"
done < <(manifest "$PROFILE")
printf '%-22s %4s %8s %18s %12s\n' total '' '' "$(python3 -c "print(f'{$total:,}')")" \
    "$(python3 -c "print(f'{$total/$RATE/3600:.0f} h')")"
echo "Outputs: $OUT/$PROFILE/<run>/stdout.txt, stderr.txt"
