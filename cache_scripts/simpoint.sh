#!/usr/bin/env bash
# SimPoint pipeline for the SPEC workloads (meant for `ref`, where full
# detailed simulation takes months).
#
#   cache_scripts/simpoint.sh profile INPUT [RUN...]     basic block vectors of the ROI (qemu)
#   cache_scripts/simpoint.sh cluster INPUT [RUN...]     SimPoint 3.2: representative intervals + weights
#   cache_scripts/simpoint.sh summary INPUT              per run: ROI size, intervals, simpoints, cost
#   cache_scripts/simpoint.sh checkpoint INPUT [RUN...]  gem5 checkpoints of the simulation points (qemu)
#   cache_scripts/simpoint.sh run INPUT CONFIGS [RUN...] detailed gem5 runs of the points, per cache
#                                                        configuration (comma separated), then combine
#   cache_scripts/simpoint.sh combine INPUT [CONFIGS]    weighted result of every finished (run, config)
#   cache_scripts/simpoint.sh status INPUT [CONFIGS]     checkpoints and runs done per workload
#
#   JOBS=32 INTERVAL=100000000 cache_scripts/simpoint.sh profile ref
#   MAXK=30 cache_scripts/simpoint.sh cluster ref
#   JOBS=36 WARMUP=500000000 cache_scripts/simpoint.sh checkpoint ref
#   JOBS=60 cache_scripts/simpoint.sh run ref small-2way,small-fa,small-dm,small-4way,small-8way
#
# profile runs each workload to its end under qemu-riscv64 with the runner's
# command line (binary with m5ops patched to NOPs, cache_scripts/qemu) and the
# bbv_roi plugin: one SimPoint frequency vector per INTERVAL instructions,
# counted from the program's start, for the intervals that lie entirely inside
# the ROI (m5_work_begin .. m5_work_end). cluster runs SimPoint on them and
# writes simpoints.abs: the chosen intervals as indices from the program's
# start, the form gem5's --take-simpoint-checkpoints expects.
#
# checkpoint does what --take-simpoint-checkpoints would, without running
# gem5's atomic CPU (~1.5M instructions/s) up to every point: qemu runs the
# workload again with the ckpt_dump plugin, which dumps the program state
# WARMUP instructions before each point, and qemu/qemu2gem5.py writes the dumps
# as gem5 checkpoint directories (cpt/, same names as gem5's). The run is made
# to lay out memory as gem5 would, since the small caches are sensitive to
# where data lands: the binary copy (.g5.q) skips glibc's /proc/self/exe
# lookup, the plugin hides qemu's vDSO (gem5 has neither, both put objects on
# the heap), and one environment variable of chosen length moves the initial
# stack pointer to gem5's offset within its page (measured with a 1-instruction
# gem5 run of the same command). Checked on x264 test: same heap layout, same
# statistics as a checkpoint gem5 took itself.
#
# run restores every point with TimingSimpleCPU and the configuration's caches
# (spec_spill_runner.sh's cache_options), WARMUP instructions of warmup (the
# SpillDetector tracks stores through it, counting nothing) and one INTERVAL
# measured, into benchmarks/<bench>/<input>/m5out/<config>/<run>_simpoint/spNN.
# When a (run, config) has all its points, simpoint_combine.py writes the
# weighted estimate of the whole ROI into that directory, in the files a full
# run has, and points simpoint_<input>_<config>_<run> at it (next to the
# latest_* links of full runs), so status_cache.sh --simpoint and the reports'
# --simpoint read it like a full run.
#
# Output: logs/simpoint/<input>/<run>/ (bbv.bb, bbv.info, simpoints, weights,
# labels (cluster and distance of every interval), simpoints.abs, cpt_plan.txt,
# cpt/, qemu stdout/stderr).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
RUNNER="$ROOT/scripts/spec_spill_runner.sh"
source <(sed -e '$d' -e "s|^SCRIPT_PATH=.*|SCRIPT_PATH='$RUNNER'|" "$RUNNER")
ROOT_DIR="$ROOT"
TOOLS=/cta/research/level0/RISCV
QEMU="$TOOLS/bin/qemu-riscv64"
NM="$TOOLS/bin/riscv64-unknown-linux-gnu-nm"
SIMPOINT=/cta/users/bkaya/riscv-spec-register-spilling/tools/simpoint/SimPoint.3.2/bin/simpoint
HOST_CC="${HOST_CC:-/cta/users/bkaya/miniconda3/envs/gem5_env/bin/x86_64-conda-linux-gnu-gcc}"
JOBS="${JOBS:-3}"
INTERVAL="${INTERVAL:-100000000}"
WARMUP="${WARMUP:-500000000}"
MAXK="${MAXK:-30}"
RATE_TIMING="${RATE_TIMING:-0.9e6}"   # gem5 TimingSimpleCPU instructions/s with caches
OUT="$ROOT/logs/simpoint"
PLUGIN="$ROOT/logs/qemu/libbbv_roi.so"
CKPT_PLUGIN="$ROOT/logs/qemu/libckpt_dump.so"
TEMPLATE_DIR="$OUT/template"
LINKS=(benchmarks aminos gcn4dna hkrdenq 1am0 dictionary WORDS ned)
cd "$ROOT" || exit 1

build_one_plugin() {   # SOURCE OUTPUT
    if [[ ! -f "$2" || "$1" -nt "$2" ]]; then
        "$HOST_CC" -shared -fPIC -O2 -I"$ROOT/cache_scripts/qemu/include" -I"$TOOLS/include" \
            -o "$2" "$1" || exit 1
    fi
}
build_plugin() { build_one_plugin "$ROOT/cache_scripts/qemu/bbv_roi.c" "$PLUGIN"; }

selected() {   # manifest lines of INPUT, narrowed to the given run IDs
    local input="$1"; shift
    manifest "$input" | while IFS=$'\x1f' read -r run_id rest; do
        if (( $# == 0 )) || [[ " $* " == *" $run_id "* ]]; then
            printf '%s\x1f%s\n' "$run_id" "$rest"
        fi
    done
}

# Working directory and binary (as argv[0]) of a checkpoint run of a workload,
# set up the way the profile set it up (run_dir copy or the repository's links).
# A run directory of its own (cptrun/), so the profile's outputs in run/ stay
# for checking against SPEC's; the checkpoints' open input files point here.
qemu_workdir() {   # DIR BINARY RUN_SRC QBIN -> prints "workdir<TAB>binary"
    local dir="$1" binary="$2" run_src="$3" qbin="$4"
    if [[ -n "$run_src" ]]; then
        rm -rf "$dir/cptrun"; prepare_run_dir "$run_src" "$dir/cptrun"
        printf '%s\t%s\n' "$dir/cptrun" "$(link_run_binary "$binary" "$dir/cptrun" "$qbin")"
    else
        for l in "${LINKS[@]}"; do
            [[ -e "$ROOT/$l" && ! -e "$dir/$l" ]] && ln -s "$ROOT/$l" "$dir/$l"
        done
        printf '%s\t%s\n' "$dir" "$qbin"
    fi
}

profile_one() {
    local input="$1" run_id="$2" binary="$3" options="$4" omnet_ini="$5" run_src="$6"
    local dir="$OUT/$input/$run_id" qbin="$ROOT/logs/qemu/bin/$(basename "$binary" .riscv).q"
    local b e stdin_path workdir start
    b=$("$NM" "$ROOT/$binary" | awk '$3 == "m5_work_begin" {print $1}')
    e=$("$NM" "$ROOT/$binary" | awk '$3 == "m5_work_end" {print $1}')
    rm -rf "$dir"; mkdir -p "$dir"
    prepare_omnet_ini "$omnet_ini" "$dir"
    options="${options//\{OUTDIR\}/$dir}"
    if [[ -n "$run_src" ]]; then
        workdir="$dir/run"
        prepare_run_dir "$run_src" "$workdir"
        qbin="$(link_run_binary "$binary" "$workdir" "$qbin")"
    else
        workdir="$dir"
        for l in "${LINKS[@]}"; do [[ -e "$ROOT/$l" ]] && ln -s "$ROOT/$l" "$dir/$l"; done
    fi
    stdin_path="$(stdin_file "$options")"
    options="$(strip_stdin "$options")"
    start=$(date +%s)
    (
        cd "$workdir" || exit 1
        # shellcheck disable=SC2086 -- options split into argv like se.py does
        "$QEMU" -plugin "$PLUGIN,out=$dir/bbv,interval=$INTERVAL,begin=$b,end=$e" "$qbin" $options \
            < "${stdin_path:-/dev/null}" > "$dir/stdout.txt" 2> "$dir/stderr.txt"
    )
    printf '%s %s\n' "$?" "$(( $(date +%s) - start ))" > "$dir/RESULT"
    printf '[%(%H:%M:%S)T] profiled %s/%s: exit %s, %ss\n' -1 "$input" "$run_id" \
        "$(cut -d' ' -f1 "$dir/RESULT")" "$(cut -d' ' -f2 "$dir/RESULT")"
}

cmd_profile() {
    local input="${1:?usage: $0 profile INPUT [RUN...]}"; shift
    build_plugin
    mkdir -p "$ROOT/logs/qemu/bin"
    declare -A seen
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        if [[ -z "${seen[$binary]:-}" ]]; then
            python3 "$ROOT/cache_scripts/qemu/patch_m5ops.py" "$ROOT/$binary" \
                "$ROOT/logs/qemu/bin/$(basename "$binary" .riscv).q" > /dev/null || exit 1
            seen[$binary]=1
        fi
        while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
        profile_one "$input" "$run_id" "$binary" "$options" "$omnet_ini" "$run_src" &
    done < <(selected "$input" "$@")
    wait
}

cmd_cluster() {
    local input="${1:?usage: $0 cluster INPUT [RUN...]}"; shift
    local run_id rest dir first
    while IFS=$'\x1f' read -r run_id rest; do
        dir="$OUT/$input/$run_id"
        [[ -s "$dir/bbv.bb" ]] || { echo "$run_id: no bbv.bb (profile it first)"; continue; }
        "$SIMPOINT" -loadFVFile "$dir/bbv.bb" -maxK "$MAXK" \
            -saveSimpoints "$dir/simpoints" -saveSimpointWeights "$dir/weights" -saveLabels "$dir/labels" \
            > "$dir/simpoint.log" 2>&1 || { echo "$run_id: SimPoint failed ($dir/simpoint.log)"; continue; }
        first=$(awk '$1 == "first_interval" {print $2}' "$dir/bbv.info")
        awk -v f="$first" '{print $1 + f, $2}' "$dir/simpoints" > "$dir/simpoints.abs"
        echo "$run_id: $(wc -l < "$dir/simpoints") simpoints"
    done < <(selected "$input" "$@")
}

cmd_summary() {
    local input="${1:?usage: $0 summary INPUT}"
    python3 - "$OUT/$input" "$INTERVAL" "$WARMUP" "$RATE_TIMING" <<'PY'
import os, sys
base, interval, warmup, rate = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
rows = []
for run in sorted(os.listdir(base)) if os.path.isdir(base) else []:
    d = os.path.join(base, run)
    info = {}
    try:
        for line in open(os.path.join(d, "bbv.info")):
            k, v = line.split()
            info[k] = int(v)
    except OSError:
        continue
    k = last = 0
    try:
        sp = [int(l.split()[0]) for l in open(os.path.join(d, "simpoints.abs"))]
        k, last = len(sp), max(sp) * interval
    except OSError:
        pass
    rc = open(os.path.join(d, "RESULT")).read().split()[0] if os.path.exists(os.path.join(d, "RESULT")) else "?"
    roi = info.get("roi_end_inst", 0) - info.get("roi_begin_inst", 0)
    rows.append((run, rc, info.get("total_insts", 0), roi, info.get("intervals", 0), k, last))
print(f"{'run':22s} {'exit':>4s} {'total insts':>18s} {'ROI insts':>18s} {'intervals':>9s} {'k':>3s} "
      f"{'last simpoint at':>18s} {'gem5 h/config':>13s}")
tot = 0.0
for run, rc, t, roi, n, k, last in rows:
    h = k * (warmup + interval) / rate / 3600
    tot += h
    print(f"{run:22s} {rc:>4s} {t:>18,} {roi:>18,} {n:>9,} {k:>3} {last:>18,} {h:13.1f}")
print(f"\ngem5 h/config = simulation points * (warmup {warmup/1e6:.0f}M + interval {interval/1e6:.0f}M) "
      f"/ {rate:g} instructions/s (TimingSimpleCPU); all runs: {tot:.0f} core-hours per configuration")
PY
}

# ---- checkpoints -----------------------------------------------------------

ensure_template() {
    # Any checkpoint of the restore's system (se.py, AtomicSimpleCPU, 4 GiB):
    # qemu2gem5.py keeps its system sections and replaces the program state.
    [[ -f "$TEMPLATE_DIR/cpt/m5.cpt" ]] && return 0
    rm -rf "$TEMPLATE_DIR"; mkdir -p "$TEMPLATE_DIR"
    "$GEM5_BIN" --outdir="$TEMPLATE_DIR/m5out" "$GEM5_CONFIG" \
        --cmd="$ROOT/benchmarks/mcf/mcf_r.riscv" --options="$ROOT/benchmarks/mcf/inp.in" \
        --cpu-type=AtomicSimpleCPU --mem-size=4GB --maxinsts=100000 --checkpoint-at-end \
        --checkpoint-dir="$TEMPLATE_DIR" > "$TEMPLATE_DIR/gem5.log" 2>&1
    local c found=''
    for c in "$TEMPLATE_DIR"/cpt.*; do   # se.py also leaves an empty "cpt.%d"
        [[ -f "$c/m5.cpt" ]] && found="$c"
    done
    [[ -n "$found" ]] || { echo "template checkpoint failed ($TEMPLATE_DIR/gem5.log)"; exit 1; }
    mv "$found" "$TEMPLATE_DIR/cpt"
}

# Offset within its page (hex) of the initial stack pointer gem5 gives the
# workload: a 1-instruction gem5 run of the runner's command line, checkpointed.
gem5_sp_offset() {   # DIR BINARY OPTIONS RUN_SRC
    local dir="$1" binary="$2" options="$3" run_src="$4" probe="$1/sp0probe" cmd="$ROOT/$2" cwd="$ROOT"
    rm -rf "$probe"; mkdir -p "$probe"
    if [[ -n "$run_src" ]]; then          # the runner starts these as ./<name> in a run dir
        cwd="$probe"; cmd="$(link_run_binary "$binary" "$probe")"
    fi
    ( cd "$cwd" && "$GEM5_BIN" --outdir="$probe/m5out" "$GEM5_CONFIG" --cmd="$cmd" --options="$options" \
        --cpu-type=AtomicSimpleCPU --mem-size=1GB --maxinsts=1 --checkpoint-at-end \
        --checkpoint-dir="$probe" ) > "$dir/sp0probe.log" 2>&1
    python3 - "$probe" <<'PY'
import glob, sys
for c in glob.glob(sys.argv[1] + "/cpt.*/m5.cpt"):
    for line in open(c):
        if line.startswith("regs.integer="):
            b = list(map(int, line.split("=", 1)[1].split()))
            print("%x" % (int.from_bytes(bytes(b[16:24]), "little") & 0xfff))
            sys.exit(0)
sys.exit(1)
PY
    local rc=$?
    rm -rf "$probe"
    return $rc
}

# Length of the environment variable that puts qemu's initial stack pointer at
# offset TARGET within its page (gem5_sp_offset); probes qemu, a few ms each.
stack_padding() {   # TARGET WORKDIR QBIN OPTIONS BINARY
    local target=$((16#$1)) workdir="$2" qbin="$3" options="$4" binary="$5" s0 d l s
    qsp() {
        # shellcheck disable=SC2086
        ( cd "$workdir" && env -i "P=$(head -c "$1" /dev/zero | tr '\0' x)" "$QEMU" \
            -plugin "$CKPT_PLUGIN,probe=1,bin=$ROOT/$binary" "$qbin" $options < /dev/null 2>/dev/null ) |
            awk '$1 == "sp0" {print $2}'
    }
    s0=$(qsp 0); [[ -n "$s0" ]] || return 1
    d=$(( (16#$s0 - target) & 0xfff ))
    for l in $(seq $(( d > 24 ? d - 24 : 0 )) $(( d + 24 ))) $(seq $(( d + 4072 )) $(( d + 4120 ))); do
        s=$(qsp "$l")
        if [[ -n "$s" ]] && (( (16#$s & 0xfff) == target )); then printf '%s\n' "$l"; return 0; fi
    done
    return 1
}

checkpoint_one() {
    local input="$1" run_id="$2" binary="$3" options="$4" omnet_ini="$5" run_src="$6"
    local dir="$OUT/$input/$run_id" wq workdir qbin stdin_path stdin_name start n want
    if [[ ! -s "$dir/simpoints.abs" ]]; then
        echo "$run_id: no simpoints.abs (cluster it first)"; return
    fi
    if [[ -z "${FORCE:-}" ]] && grep -qx "warmup $WARMUP" "$dir/cpt/DONE" 2>/dev/null; then
        echo "$run_id: checkpoints already there (FORCE=1 makes them again)"; return
    fi
    python3 "$ROOT/cache_scripts/qemu/qemu2gem5.py" plan --simpoints "$dir/simpoints.abs" \
        --weights "$dir/weights" --interval "$INTERVAL" --warmup "$WARMUP" --out "$dir/cpt_plan.txt" || return
    cut -d' ' -f2 "$dir/cpt_plan.txt" > "$dir/cpt_at.txt"
    want=$(wc -l < "$dir/cpt_plan.txt")
    prepare_omnet_ini "$omnet_ini" "$dir"
    options="${options//\{OUTDIR\}/$dir}"
    wq="$(qemu_workdir "$dir" "$binary" "$run_src" "$ROOT/logs/qemu/bin/$(basename "$binary" .riscv).g5.q")"
    workdir="${wq%%$'\t'*}"; qbin="${wq#*$'\t'}"
    stdin_path="$(stdin_file "$options")"
    options="$(strip_stdin "$options")"
    stdin_name=cin
    [[ -n "$stdin_path" ]] && stdin_name="$workdir/$stdin_path"
    rm -rf "$dir/dumps" "$dir/cpt"
    start=$(date +%s)
    local sp_off pad
    sp_off="$(gem5_sp_offset "$dir" "$binary" "$options" "$run_src")" ||
        { echo "$run_id: gem5 stack probe failed ($dir/sp0probe.log)"; return; }
    pad="$(stack_padding "$sp_off" "$workdir" "$qbin" "$options" "$binary")" ||
        { echo "$run_id: no stack padding found for offset $sp_off"; return; }
    (
        cd "$workdir" || exit 1
        # shellcheck disable=SC2086 -- options split into argv like se.py does
        env -i "P=$(head -c "$pad" /dev/zero | tr '\0' x)" \
            "$QEMU" -plugin "$CKPT_PLUGIN,out=$dir/dumps,at=$dir/cpt_at.txt,bin=$ROOT/$binary" \
            "$qbin" $options < "${stdin_path:-/dev/null}" > "$dir/cpt_stdout.txt" 2> "$dir/cpt_stderr.txt"
    )
    python3 "$ROOT/cache_scripts/qemu/qemu2gem5.py" convert --template "$TEMPLATE_DIR/cpt" \
        --plan "$dir/cpt_plan.txt" --dumps "$dir/dumps" --out "$dir/cpt" --interval "$INTERVAL" \
        --stdin "$stdin_name" > "$dir/cpt_convert.log" 2>&1
    n=$(ls -d "$dir"/cpt/cpt.simpoint_* 2>/dev/null | wc -l)
    if (( n == want )); then
        rm -rf "$dir/dumps"
        printf 'warmup %s\ninterval %s\npoints %s\nstdin %s\ngem5_sp_page_offset %s\npadding %s\n' \
            "$WARMUP" "$INTERVAL" "$n" "$stdin_name" "$sp_off" "$pad" > "$dir/cpt/DONE"
    fi
    printf '[%(%H:%M:%S)T] checkpoints %s/%s: %s of %s, %ss\n' -1 "$input" "$run_id" "$n" "$want" \
        "$(( $(date +%s) - start ))"
}

cmd_checkpoint() {
    local input="${1:?usage: $0 checkpoint INPUT [RUN...]}"; shift
    build_one_plugin "$ROOT/cache_scripts/qemu/ckpt_dump.c" "$CKPT_PLUGIN"
    ensure_template
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        local g5q="$ROOT/logs/qemu/bin/$(basename "$binary" .riscv).g5.q"
        [[ -f "$g5q" && "$g5q" -nt "$ROOT/$binary" ]] ||
            python3 "$ROOT/cache_scripts/qemu/patch_m5ops.py" "$ROOT/$binary" "$g5q" --gem5-compat > /dev/null
        while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
        checkpoint_one "$input" "$run_id" "$binary" "$options" "$omnet_ini" "$run_src" &
    done < <(selected "$input" "$@")
    wait
}

# ---- detailed runs of the points --------------------------------------------

sp_done() {   # gem5 outdir of one point
    # not anchored: the program's last stdout line may lack its newline
    grep -q 'Done running SimPoint!' "$1/nohup.log" 2>/dev/null &&
        grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*10$' "$1/riscv_spill_stats.txt" 2>/dev/null
}

spbase() {   # INPUT CONFIG BENCHMARK RUN
    printf '%s/benchmarks/%s/%s/m5out/%s/%s_simpoint' "$ROOT" "$3" "$1" "$2" "$4"
}

combine_one() {   # INPUT CONFIG BENCHMARK RUN
    local input="$1" cfg="$2" benchmark="$3" run_id="$4" base n k
    base="$(spbase "$input" "$cfg" "$benchmark" "$run_id")"
    n=$(wc -l < "$OUT/$input/$run_id/cpt_plan.txt")
    for (( k = 1; k <= n; k++ )); do sp_done "$base/$(printf 'sp%02d' "$k")" || return 1; done
    mkdir "$base/.combine.lock" 2>/dev/null || return 0
    mkdir -p "$(run_base "$benchmark")"
    python3 "$ROOT/cache_scripts/simpoint_combine.py" --spdir "$base" \
        --plan "$OUT/$input/$run_id/cpt_plan.txt" --bbv-info "$OUT/$input/$run_id/bbv.info" \
        --out "$base" --run-id "$run_id" \
        --link "$(run_base "$benchmark")/simpoint_${input}_${cfg}_${run_id}" > "$base/combine.log" 2>&1
    rmdir "$base/.combine.lock"
}

run_point() {   # INPUT CONFIG BENCHMARK RUN K BINARY OPTIONS RUN_SRC
    local input="$1" cfg="$2" benchmark="$3" run_id="$4" k="$5" binary="$6" options="$7" run_src="$8"
    local base out cpt stdin_name workdir rc=0
    local -a stdin_args=()
    base="$(spbase "$input" "$cfg" "$benchmark" "$run_id")"
    out="$base/$(printf 'sp%02d' "$k")"
    cpt="$OUT/$input/$run_id/cpt"
    rm -rf "$out"; mkdir -p "$out/.runner"
    printf '%s\n' "$(date +%s)" > "$out/.runner/started.epoch"
    hostname > "$out/.runner/host"
    options="${options//\{OUTDIR\}/$out}"
    workdir="$ROOT"
    if [[ -n "$run_src" ]]; then
        workdir="$out/run"
        prepare_run_dir "$run_src" "$workdir"
    fi
    stdin_name=$(awk '$1 == "stdin" {print $2}' "$cpt/DONE")
    [[ "$stdin_name" != cin ]] && stdin_args=("--input=$stdin_name")
    options="$(strip_stdin "$options")"
    (
        cd "$workdir" || exit 1
        # shellcheck disable=SC2046 -- cache options split like the runner does
        "$GEM5_BIN" "--outdir=$out" "$GEM5_CONFIG" "--cmd=$ROOT/$binary" "--options=$options" \
            "${stdin_args[@]}" $(cache_options "$cfg") --restore-with-cpu=TimingSimpleCPU \
            --restore-simpoint-checkpoint -r "$k" --checkpoint-dir="$cpt" \
            > "$out/nohup.log" 2>&1
    ) || rc=$?
    printf '%s\n' "$(date +%s)" > "$out/.runner/finished.epoch"
    printf '%s\n' "$rc" > "$out/.runner/exit_code"
    if sp_done "$out"; then
        printf 'COMPLETED\n' > "$out/.runner/status"
        [[ -n "$run_src" ]] && rm -rf "$out/run"
        combine_one "$input" "$cfg" "$benchmark" "$run_id"
    else
        printf 'FAILED\n' > "$out/.runner/status"
        printf '[%(%H:%M:%S)T] FAILED %s %s sp%02d (%s)\n' -1 "$cfg" "$run_id" "$k" "$out/nohup.log"
    fi
}

cmd_run() {
    local input="${1:?usage: $0 run INPUT CONFIGS [RUN...]}" configs="${2:?usage: $0 run INPUT CONFIGS [RUN...]}"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src cfg k n
    local -a tasks=()
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        if [[ ! -f "$OUT/$input/$run_id/cpt/DONE" ]]; then
            echo "$run_id: no checkpoints yet, skipped"; continue
        fi
        n=$(awk '$1 == "points" {print $2}' "$OUT/$input/$run_id/cpt/DONE")
        for (( k = 1; k <= n; k++ )); do
            for cfg in ${configs//,/ }; do
                sp_done "$(spbase "$input" "$cfg" "$benchmark" "$run_id")/$(printf 'sp%02d' "$k")" && continue
                tasks+=("$cfg"$'\x1f'"$benchmark"$'\x1f'"$run_id"$'\x1f'"$k"$'\x1f'"$binary"$'\x1f'"$options"$'\x1f'"$run_src")
            done
        done
    done < <(selected "$input" "$@")
    printf '[%(%H:%M:%S)T] %s point runs to do, %s at a time\n' -1 "${#tasks[@]}" "$JOBS"
    local t
    for t in "${tasks[@]}"; do
        IFS=$'\x1f' read -r cfg benchmark run_id k binary options run_src <<< "$t"
        while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
        run_point "$input" "$cfg" "$benchmark" "$run_id" "$k" "$binary" "$options" "$run_src" &
    done
    wait
    cmd_combine "$input" "$configs" > /dev/null
    printf '[%(%H:%M:%S)T] done\n' -1
}

cmd_combine() {
    local input="${1:?usage: $0 combine INPUT [CONFIGS]}" configs="${2:-small-2way,small-fa,small-dm,small-4way,small-8way}"
    local run_id benchmark rest cfg
    while IFS=$'\x1f' read -r run_id benchmark rest; do
        [[ -f "$OUT/$input/$run_id/cpt/DONE" ]] || continue
        for cfg in ${configs//,/ }; do
            [[ -d "$(spbase "$input" "$cfg" "$benchmark" "$run_id")" ]] || continue
            combine_one "$input" "$cfg" "$benchmark" "$run_id" && echo "$cfg $run_id combined"
        done
    done < <(selected "$input")
}

cmd_status() {
    local input="${1:?usage: $0 status INPUT [CONFIGS]}" configs="${2:-small-2way,small-fa,small-dm,small-4way,small-8way}"
    local run_id benchmark rest cfg n k d line
    printf '%-22s %6s %7s' run profile points
    for cfg in ${configs//,/ }; do printf ' %11s' "$cfg"; done
    printf '\n'
    while IFS=$'\x1f' read -r run_id benchmark rest; do
        d="$OUT/$input/$run_id"
        line="$(printf '%-22s %6s' "$run_id" "$([[ -f "$d/RESULT" ]] && cut -d' ' -f1 "$d/RESULT" | sed 's/^0$/ok/' || echo -)")"
        if [[ -f "$d/cpt/DONE" ]]; then
            n=$(awk '$1 == "points" {print $2}' "$d/cpt/DONE")
            line+="$(printf ' %7s' "$n")"
            for cfg in ${configs//,/ }; do
                local done_n=0 base
                base="$(spbase "$input" "$cfg" "$benchmark" "$run_id")"
                for (( k = 1; k <= n; k++ )); do sp_done "$base/$(printf 'sp%02d' "$k")" && done_n=$((done_n + 1)); done
                if [[ -f "$base/simpoint.txt" ]]; then line+="$(printf ' %11s' combined)"
                else line+="$(printf ' %11s' "$done_n/$n")"; fi
            done
        else
            line+="$(printf ' %7s' "$([[ -d "$d/dumps" ]] && echo dumping || echo -)")"
        fi
        printf '%s\n' "$line"
    done < <(selected "$input")
}

case "${1:-}" in
  profile) shift; cmd_profile "$@" ;;
  cluster) shift; cmd_cluster "$@" ;;
  summary) shift; cmd_summary "$@" ;;
  checkpoint) shift; cmd_checkpoint "$@" ;;
  run) shift; cmd_run "$@" ;;
  combine) shift; cmd_combine "$@" ;;
  status) shift; cmd_status "$@" ;;
  *) sed -n '2,46p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
