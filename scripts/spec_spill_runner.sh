#!/usr/bin/env bash
# Run and monitor SPEC CPU2017 workloads with the schema-v7 spill detector.

set -uo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
# The repository root is one level above scripts/.
ROOT_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
GEM5_BIN="${GEM5_BIN:-$ROOT_DIR/build/RISCV/gem5.opt}"
GEM5_CONFIG="${GEM5_CONFIG:-$ROOT_DIR/configs/deprecated/example/se.py}"
ANALYZER="$ROOT_DIR/scripts/spill_report.py"

usage() {
    cat <<'EOF'
Usage:
  ./scripts/spec_spill_runner.sh list [test|train|ref]
  ./scripts/spec_spill_runner.sh check  PROFILE CACHE [TARGET ...]
  ./scripts/spec_spill_runner.sh start  PROFILE CACHE TARGET [TARGET ...]
  ./scripts/spec_spill_runner.sh status PROFILE CACHE [TARGET ...]
  ./scripts/spec_spill_runner.sh stop   PROFILE CACHE TARGET [TARGET ...]
  ./scripts/spec_spill_runner.sh log    PROFILE CACHE RUN_ID [LINES]
  ./scripts/spec_spill_runner.sh results PROFILE CACHE [TARGET ...]

PROFILE: test, train, ref
CACHE:   standard, small
TARGET:  run ID, benchmark name, or "all"

Examples:
  ./scripts/spec_spill_runner.sh list test
  ./scripts/spec_spill_runner.sh check test standard all
  ./scripts/spec_spill_runner.sh start test standard gcc perlbench
  ./scripts/spec_spill_runner.sh status test standard all
  ./scripts/spec_spill_runner.sh log test standard gcc 40
  ./scripts/spec_spill_runner.sh results test standard gcc
  ./scripts/spec_spill_runner.sh stop test standard gcc

Results are never overwritten. Every start creates a timestamped directory
under benchmarks/<benchmark>/m5out_<benchmark>/ and updates a "latest_*" link.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

valid_profile() {
    case "$1" in test|train|ref) return 0 ;; *) return 1 ;; esac
}

valid_cache() {
    case "$1" in standard|small) return 0 ;; *) return 1 ;; esac
}

# Fields: run_id | benchmark | input_set | input_description | binary |
#         program_options | required_paths | optional_omnet_ini
record() {
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@"
}

manifest() {
    local profile="$1"
    case "$profile" in
      test)
        record cactuBSSN cactuBSSN test spec_test.par \
          benchmarks/cactuBSSN/cactuBSSN_r.riscv \
          'benchmarks/cactuBSSN/spec_test.par' \
          'benchmarks/cactuBSSN/spec_test.par' ''
        record parest parest test test.prm \
          benchmarks/parest/parest_r.riscv \
          'benchmarks/parest/test.prm' \
          'benchmarks/parest/test.prm' ''
        record deepsjeng deepsjeng test test.txt \
          benchmarks/deepsjeng/deepsjeng_r.riscv \
          'benchmarks/deepsjeng/test.txt' \
          'benchmarks/deepsjeng/test.txt' ''
        record leela leela test test.sgf \
          benchmarks/leela/leela_r.riscv \
          'benchmarks/leela/test.sgf' \
          'benchmarks/leela/test.sgf' ''
        record namd namd test 'apoa1.input, 1 iteration' \
          benchmarks/namd/namd_r.riscv \
          '--input benchmarks/namd/apoa1.input --iterations 1 --output {OUTDIR}/apoa1.output' \
          'benchmarks/namd/apoa1.input' ''
        record lbm lbm test '20 steps, 100_100_130_cf_a.of' \
          benchmarks/lbm/lbm_r.riscv \
          '20 {OUTDIR}/reference.dat 0 1 benchmarks/lbm/100_100_130_cf_a.of' \
          'benchmarks/lbm/100_100_130_cf_a.of' ''
        record nab nab test 'hkrdenq, 1000 iterations' \
          benchmarks/nab/nab_r.riscv \
          'hkrdenq 1930344093 1000' \
          'hkrdenq/hkrdenq.pdb;hkrdenq/hkrdenq.prm' ''
        record xz xz test 'cpu2006docs.tar.xz, level 0' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1548636 1555348 0' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record imagick imagick test 'test_input.tga, short filter chain' \
          benchmarks/imagick/imagick_r.riscv \
          '-limit disk 0 benchmarks/imagick/test_input.tga -shear 25 -resize 640x480 -negate -alpha Off {OUTDIR}/test_output.tga' \
          'benchmarks/imagick/test_input.tga' ''
        record blender blender test 'cube.blend, frame 1' \
          benchmarks/blender/blender_r.riscv \
          'benchmarks/blender/cube.blend --render-output {OUTDIR}/cube_ --threads 1 -b -F RAWTGA -s 1 -e 1 -a' \
          'benchmarks/blender/cube.blend' ''
        record povray povray test SPEC-benchmark-test.ini \
          benchmarks/povray/povray_r.riscv \
          'benchmarks/povray/SPEC-benchmark-test.ini' \
          'benchmarks/povray/SPEC-benchmark-test.ini' ''
        record omnetpp omnetpp test 'omnetpp_test.ini, sim-time-limit=0.003s' \
          benchmarks/omnetpp/omnetpp_r.riscv \
          '-c General -r 0 {OUTDIR}/omnetpp.ini' \
          'benchmarks/omnetpp/omnetpp_test.ini;benchmarks/omnetpp/ned' \
          benchmarks/omnetpp/omnetpp_test.ini
        record xalancbmk xalancbmk test 'test.xml + xalanc.xsl' \
          benchmarks/xalancbmk/xalancbmk_r.riscv \
          '-v benchmarks/xalancbmk/test.xml benchmarks/xalancbmk/xalanc.xsl' \
          'benchmarks/xalancbmk/test.xml;benchmarks/xalancbmk/xalanc.xsl' ''
        record x264 x264 train-fallback 'BuckBunny_train.264 decode' \
          benchmarks/x264/ldecod_r.riscv \
          '-i benchmarks/x264/BuckBunny_train.264 -o {OUTDIR}/BuckBunny.yuv' \
          'benchmarks/x264/BuckBunny_train.264' ''
        record gcc gcc test 't1.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/t1.c -O3 -finline-limit=50000 -o {OUTDIR}/t1.s' \
          'benchmarks/gcc/t1.c' ''
        record mcf mcf ref-fallback inp.in \
          benchmarks/mcf/mcf_r.riscv \
          'benchmarks/mcf/inp.in' \
          'benchmarks/mcf/inp.in' ''
        record perlbench_test perlbench test test.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/test.pl' \
          'benchmarks/perlbench/test.pl;benchmarks/perlbench/lib' ''
        ;;
      train)
        record cactuBSSN cactuBSSN train spec_train.par \
          benchmarks/cactuBSSN/cactuBSSN_r.riscv \
          'benchmarks/cactuBSSN/spec_train.par' \
          'benchmarks/cactuBSSN/spec_train.par' ''
        record parest parest train train.prm \
          benchmarks/parest/parest_r.riscv \
          'benchmarks/parest/train.prm' \
          'benchmarks/parest/train.prm' ''
        record deepsjeng deepsjeng train train.txt \
          benchmarks/deepsjeng/deepsjeng_r.riscv \
          'benchmarks/deepsjeng/train.txt' \
          'benchmarks/deepsjeng/train.txt' ''
        record leela leela train train.sgf \
          benchmarks/leela/leela_r.riscv \
          'benchmarks/leela/train.sgf' \
          'benchmarks/leela/train.sgf' ''
        record namd namd train 'apoa1.input, 7 iterations' \
          benchmarks/namd/namd_r.riscv \
          '--input benchmarks/namd/apoa1.input --iterations 7 --output {OUTDIR}/apoa1.output' \
          'benchmarks/namd/apoa1.input' ''
        record lbm lbm train '300 steps, 100_100_130_cf_b.of' \
          benchmarks/lbm/lbm_r.riscv \
          '300 {OUTDIR}/reference.dat 0 1 benchmarks/lbm/100_100_130_cf_b.of' \
          'benchmarks/lbm/100_100_130_cf_b.of' ''
        record nab nab train 'aminos, 1000 iterations' \
          benchmarks/nab/nab_r.riscv \
          'aminos 391519156 1000' \
          'aminos/aminos.pdb;aminos/aminos.prm' ''
        record xz xz train 'IMG_2560.cr2.xz, level 4' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/IMG_2560.cr2.xz 40 ec03e53b02deae89b6650f1de4bed76a012366fb3d4bdc791e8633d1a5964e03004523752ab008eff0d9e693689c53056533a05fc4b277f0086544c6c3cbbbf6 40822692 40824404 4' \
          'benchmarks/xz/IMG_2560.cr2.xz' ''
        record imagick imagick train 'train_input.tga, 8 filters' \
          benchmarks/imagick/imagick_r.riscv \
          '-limit disk 0 benchmarks/imagick/train_input.tga -resize 320x240 -shear 31 -edge 140 -negate -flop -resize 900x900 -edge 10 {OUTDIR}/train_output.tga' \
          'benchmarks/imagick/train_input.tga' ''
        record blender blender train 'sh5_reduced.blend, frame 234' \
          benchmarks/blender/blender_r.riscv \
          'benchmarks/blender/sh5_reduced.blend --render-output {OUTDIR}/sh5_ --threads 1 -b -F RAWTGA -s 234 -e 234 -a' \
          'benchmarks/blender/sh5_reduced.blend' ''
        record povray povray train SPEC-benchmark-train.ini \
          benchmarks/povray/povray_r.riscv \
          'benchmarks/povray/SPEC-benchmark-train.ini' \
          'benchmarks/povray/SPEC-benchmark-train.ini' ''
        record omnetpp omnetpp train 'omnetpp_train.ini, sim-time-limit=0.15s' \
          benchmarks/omnetpp/omnetpp_r.riscv \
          '-c General -r 0 {OUTDIR}/omnetpp.ini' \
          'benchmarks/omnetpp/omnetpp_train.ini;benchmarks/omnetpp/ned' \
          benchmarks/omnetpp/omnetpp_train.ini
        record xalancbmk xalancbmk train 'allbooks.xml + xalanc.xsl' \
          benchmarks/xalancbmk/xalancbmk_r.riscv \
          '-v benchmarks/xalancbmk/allbooks.xml benchmarks/xalancbmk/xalanc.xsl' \
          'benchmarks/xalancbmk/allbooks.xml;benchmarks/xalancbmk/xalanc.xsl' ''
        record x264 x264 ref-fallback 'BuckBunny.264 decode' \
          benchmarks/x264/ldecod_r.riscv \
          '-i benchmarks/x264/BuckBunny.264 -o {OUTDIR}/BuckBunny.yuv' \
          'benchmarks/x264/BuckBunny.264' ''
        record gcc gcc train 'train01.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/train01.c -O3 -finline-limit=50000 -o {OUTDIR}/train01.s' \
          'benchmarks/gcc/train01.c' ''
        record mcf mcf train inp_train.in \
          benchmarks/mcf/mcf_r.riscv \
          'benchmarks/mcf/inp_train.in' \
          'benchmarks/mcf/inp_train.in' ''
        record perlbench_scrabbl perlbench train scrabbl.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/scrabbl.pl' \
          'benchmarks/perlbench/scrabbl.pl;benchmarks/perlbench/lib' ''
        record perlbench_suns perlbench train suns.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/suns.pl' \
          'benchmarks/perlbench/suns.pl;benchmarks/perlbench/lib' ''
        ;;
      ref)
        record cactuBSSN cactuBSSN train-fallback spec_train.par \
          benchmarks/cactuBSSN/cactuBSSN_r.riscv \
          'benchmarks/cactuBSSN/spec_train.par' \
          'benchmarks/cactuBSSN/spec_train.par' ''
        record parest parest train-fallback train.prm \
          benchmarks/parest/parest_r.riscv \
          'benchmarks/parest/train.prm' \
          'benchmarks/parest/train.prm' ''
        record deepsjeng deepsjeng ref ref.txt \
          benchmarks/deepsjeng/deepsjeng_r.riscv \
          'benchmarks/deepsjeng/ref.txt' \
          'benchmarks/deepsjeng/ref.txt' ''
        record leela leela ref ref.sgf \
          benchmarks/leela/leela_r.riscv \
          'benchmarks/leela/ref.sgf' \
          'benchmarks/leela/ref.sgf' ''
        record namd namd ref 'apoa1.input, 65 iterations' \
          benchmarks/namd/namd_r.riscv \
          '--input benchmarks/namd/apoa1.input --iterations 65 --output {OUTDIR}/apoa1.output' \
          'benchmarks/namd/apoa1.input' ''
        record lbm lbm ref '3000 steps, 100_100_130_ldc.of' \
          benchmarks/lbm/lbm_r.riscv \
          '3000 {OUTDIR}/reference.dat 0 0 benchmarks/lbm/100_100_130_ldc.of' \
          'benchmarks/lbm/100_100_130_ldc.of' ''
        record nab nab ref '1am0, 122 iterations' \
          benchmarks/nab/nab_r.riscv \
          '1am0 1122214447 122' \
          '1am0/1am0.pdb;1am0/1am0.prm' ''
        record xz xz ref 'cld.tar.xz, level 6' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cld.tar.xz 160 19cf30ae51eddcbefda78dd06014b4b96281456e078ca7c13e1c0c9e6aaea8dff3efb4ad6b0456697718cede6bd5454852652806a657bb56e07d61128434b474 59796407 61004416 6' \
          'benchmarks/xz/cld.tar.xz' ''
        record imagick imagick ref 'refrate_input.tga, reference filters' \
          benchmarks/imagick/imagick_r.riscv \
          '-limit disk 0 benchmarks/imagick/refrate_input.tga -edge 41 -resample 181% -emboss 31 -colorspace YUV -mean-shift 19x19+15% -resize 30% {OUTDIR}/refrate_output.tga' \
          'benchmarks/imagick/refrate_input.tga' ''
        record blender blender ref 'sh3_no_char.blend, frame 849' \
          benchmarks/blender/blender_r.riscv \
          'benchmarks/blender/sh3_no_char.blend --render-output {OUTDIR}/sh3_ --threads 1 -b -F RAWTGA -s 849 -e 849 -a' \
          'benchmarks/blender/sh3_no_char.blend' ''
        record povray povray ref SPEC-benchmark-ref.ini \
          benchmarks/povray/povray_r.riscv \
          'benchmarks/povray/SPEC-benchmark-ref.ini' \
          'benchmarks/povray/SPEC-benchmark-ref.ini' ''
        record omnetpp omnetpp ref 'omnetpp.ini, sim-time-limit=2.25s' \
          benchmarks/omnetpp/omnetpp_r.riscv \
          '-c General -r 0 {OUTDIR}/omnetpp.ini' \
          'benchmarks/omnetpp/omnetpp.ini;benchmarks/omnetpp/ned' \
          benchmarks/omnetpp/omnetpp.ini
        record xalancbmk xalancbmk ref 't5.xml + xalanc.xsl' \
          benchmarks/xalancbmk/xalancbmk_r.riscv \
          '-v benchmarks/xalancbmk/t5.xml benchmarks/xalancbmk/xalanc.xsl' \
          'benchmarks/xalancbmk/t5.xml;benchmarks/xalancbmk/xalanc.xsl' ''
        record x264 x264 ref 'BuckBunny.264 decode' \
          benchmarks/x264/ldecod_r.riscv \
          '-i benchmarks/x264/BuckBunny.264 -o {OUTDIR}/BuckBunny.yuv' \
          'benchmarks/x264/BuckBunny.264' ''
        record gcc gcc ref 'gcc-pp.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/gcc-pp.c -O3 -finline-limit=0 -fif-conversion -fif-conversion2 -o {OUTDIR}/gcc-pp.s' \
          'benchmarks/gcc/gcc-pp.c' ''
        record mcf mcf ref inp.in \
          benchmarks/mcf/mcf_r.riscv \
          'benchmarks/mcf/inp.in' \
          'benchmarks/mcf/inp.in' ''
        record perlbench_checkspam perlbench ref checkspam.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/checkspam.pl 2500 5 25 11 150 1 1 1 1' \
          'benchmarks/perlbench/checkspam.pl;benchmarks/perlbench/lib' ''
        record perlbench_diffmail perlbench ref diffmail.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/diffmail.pl 4 800 10 17 19 300' \
          'benchmarks/perlbench/diffmail.pl;benchmarks/perlbench/lib' ''
        record perlbench_splitmail perlbench ref splitmail.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/splitmail.pl 6400 12 26 16 100 0' \
          'benchmarks/perlbench/splitmail.pl;benchmarks/perlbench/lib' ''
        ;;
    esac
}

matches_targets() {
    local run_id="$1" benchmark="$2"
    shift 2
    local target
    (( $# == 0 )) && return 0
    for target in "$@"; do
        [[ "$target" == all || "$target" == "$run_id" || "$target" == "$benchmark" ]] && return 0
    done
    return 1
}

selected_manifest() {
    local profile="$1"
    shift
    local run_id benchmark input_set input_desc binary options required omnet_ini
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        matches_targets "$run_id" "$benchmark" "$@" || continue
        record "$run_id" "$benchmark" "$input_set" "$input_desc" "$binary" \
            "$options" "$required" "$omnet_ini"
    done < <(manifest "$profile")
}

# All runs of a benchmark live side by side in one directory; the profile and
# cache are recorded inside each run rather than encoded in the path.
run_base() {
    local benchmark="$1"
    printf '%s/benchmarks/%s/m5out_%s' "$ROOT_DIR" "$benchmark" "$benchmark"
}

# One symlink per (profile, cache, run_id) pointing at that combination's most
# recent run, so lookups stay O(1) without scanning every run directory.
latest_link() {
    local profile="$1" cache="$2" benchmark="$3" run_id="$4"
    printf '%s/latest_%s_%s_%s' "$(run_base "$benchmark")" "$profile" "$cache" "$run_id"
}

latest_dir() {
    local link
    link="$(latest_link "$1" "$2" "$3" "$4")"
    [[ -L "$link" || -d "$link" ]] || return 1
    readlink -f "$link"
}

format_duration() {
    local seconds="${1:-0}"
    (( seconds < 0 )) && seconds=0
    printf '%02d:%02d:%02d' "$((seconds / 3600))" \
        "$(((seconds % 3600) / 60))" "$((seconds % 60))"
}

file_value() {
    local file="$1" value=''
    if [[ -r "$file" ]]; then
        IFS= read -r value < "$file" || true
    fi
    printf '%s' "$value"
}

read_state() {
    local outdir="$1" state pid
    [[ -n "$outdir" && -d "$outdir" ]] || { printf PENDING; return; }
    state="$(file_value "$outdir/.runner/status")"
    pid="$(file_value "$outdir/.runner/worker.pid")"
    if [[ "$state" == RUNNING ]]; then
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            printf RUNNING
        else
            printf INTERRUPTED
        fi
        return
    fi
    if [[ -n "$state" ]]; then
        printf '%s' "$state"
    elif [[ -f "$outdir/riscv_spill_stats.txt" ]] &&
         grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*7$' "$outdir/riscv_spill_stats.txt"; then
        printf COMPLETED
    else
        printf UNKNOWN
    fi
}

validate_paths() {
    local binary="$1" required="$2" missing=0 path
    [[ -x "$ROOT_DIR/$binary" ]] || {
        printf '  MISSING executable: %s\n' "$binary" >&2
        missing=1
    }
    IFS=';' read -r -a required_paths <<< "$required"
    for path in "${required_paths[@]}"; do
        [[ -z "$path" || -e "$ROOT_DIR/$path" ]] && continue
        printf '  MISSING input:      %s\n' "$path" >&2
        missing=1
    done
    return "$missing"
}

verify_gem5_build() {
    local source
    [[ -x "$GEM5_BIN" ]] || die "gem5 binary is missing or not executable: $GEM5_BIN"
    [[ -f "$GEM5_CONFIG" ]] || die "gem5 config is missing: $GEM5_CONFIG"
    if ! grep -a -q -m1 'total_spill_insts  : ' "$GEM5_BIN"; then
        die "gem5 binary does not contain the schema-v7 spill metrics; rebuild it"
    fi
    for source in \
        src/cpu/simple/spill_detector.cc \
        src/cpu/simple/timing.cc \
        src/mem/request.hh; do
        if [[ "$ROOT_DIR/$source" -nt "$GEM5_BIN" ]]; then
            die "gem5 binary is older than $source; rebuild it before launching SPEC"
        fi
    done
}

cache_options() {
    case "$1" in
      standard)
        printf '%s\n' '--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB'
        ;;
      small)
        printf '%s\n' '--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB --l1d_size=4kB --l1i_size=32kB --l2_size=32kB'
        ;;
    esac
}

prepare_omnet_ini() {
    local source_ini="$1" outdir="$2"
    [[ -n "$source_ini" ]] || return 0
    sed -E \
        -e "s|^[[:space:]]*ned-path[[:space:]]*=.*|ned-path = $ROOT_DIR/benchmarks/omnetpp/ned|" \
        -e "s|^[[:space:]]*result-dir[[:space:]]*=.*|result-dir = $outdir|" \
        "$ROOT_DIR/$source_ini" > "$outdir/omnetpp.ini"
}

worker_stop_requested=0
worker_child_pid=''

worker_stop() {
    worker_stop_requested=1
    [[ -n "$worker_child_pid" ]] && kill -TERM "$worker_child_pid" 2>/dev/null || true
}

run_worker() {
    local profile="$1" cache="$2" wanted_id="$3" outdir="$4"
    local run_id benchmark input_set input_desc binary options required omnet_ini
    local found=0 rc=0 final_state cache_args

    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        [[ "$run_id" == "$wanted_id" ]] || continue
        found=1
        break
    done < <(manifest "$profile")
    (( found == 1 )) || die "worker manifest entry not found: $wanted_id"

    mkdir -p "$outdir/.runner"
    printf '%s\n' "$$" > "$outdir/.runner/worker.pid"
    printf '%s\n' RUNNING > "$outdir/.runner/status"
    printf '%s\n' "$(date +%s)" > "$outdir/.runner/started.epoch"
    printf '%s\n' "$(date --iso-8601=seconds)" > "$outdir/.runner/started_at"
    git -C "$ROOT_DIR" rev-parse HEAD > "$outdir/.runner/gem5_commit" 2>/dev/null || true

    prepare_omnet_ini "$omnet_ini" "$outdir"
    options="${options//\{OUTDIR\}/$outdir}"
    cache_args="$(cache_options "$cache")"
    printf '%q ' "$GEM5_BIN" "--outdir=$outdir" "$GEM5_CONFIG" \
        "--cmd=$ROOT_DIR/$binary" "--options=$options" $cache_args \
        > "$outdir/.runner/command.sh"
    printf '\n' >> "$outdir/.runner/command.sh"

    trap worker_stop TERM INT
    cd "$ROOT_DIR" || exit 1
    # options and cache_args must be split for se.py's argv interface.
    "$GEM5_BIN" "--outdir=$outdir" "$GEM5_CONFIG" \
        "--cmd=$ROOT_DIR/$binary" "--options=$options" \
        $cache_args > "$outdir/nohup.log" 2>&1 &
    worker_child_pid=$!
    printf '%s\n' "$worker_child_pid" > "$outdir/.runner/gem5.pid"
    wait "$worker_child_pid" || rc=$?

    if (( worker_stop_requested == 1 )); then
        final_state=STOPPED
    elif (( rc != 0 )); then
        final_state=FAILED
    elif grep -Eq '(^|[[:space:]])(fatal|panic):|^<!> Error:|Program aborted|Segmentation fault' \
            "$outdir/nohup.log"; then
        final_state=FAILED
    elif [[ ! -f "$outdir/riscv_spill_stats.txt" ]] ||
         ! grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*7$' \
            "$outdir/riscv_spill_stats.txt"; then
        final_state=INVALID_SCHEMA
    elif ! grep -q '^# ROI SUMMARY' "$outdir/riscv_spill_stats.txt"; then
        final_state=NO_ROI
    elif [[ ! -f "$outdir/stats.txt" ]] ||
         ! grep -q '^---------- End Simulation Statistics' "$outdir/stats.txt"; then
        final_state=INCOMPLETE
    else
        final_state=COMPLETED
    fi

    printf '%s\n' "$rc" > "$outdir/.runner/exit_code"
    printf '%s\n' "$(date +%s)" > "$outdir/.runner/finished.epoch"
    printf '%s\n' "$(date --iso-8601=seconds)" > "$outdir/.runner/finished_at"
    printf '%s\n' "$final_state" > "$outdir/.runner/status"
}

command_list() {
    local profile="${1:-}" run_id benchmark input_set input_desc binary options required omnet_ini
    if [[ -n "$profile" ]]; then
        valid_profile "$profile" || die "invalid profile: $profile"
    else
        profile=test
    fi
    printf '%-23s %-13s %-15s %s\n' RUN_ID BENCHMARK INPUT_SET INPUT
    printf '%-23s %-13s %-15s %s\n' '-----------------------' '-------------' '---------------' '-----'
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        printf '%-23s %-13s %-15s %s\n' "$run_id" "$benchmark" "$input_set" "$input_desc"
    done < <(manifest "$profile")
}

command_check() {
    local profile="$1" cache="$2"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini count=0 failures=0
    verify_gem5_build
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        ((count++))
        printf '[%-23s] ' "$run_id"
        if validate_paths "$binary" "$required"; then
            printf 'OK (%s)\n' "$input_desc"
        else
            printf 'FAILED\n'
            ((failures++))
        fi
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
    printf '\nChecked: %d, failures: %d, cache: %s\n' "$count" "$failures" "$cache"
    (( failures == 0 ))
}

command_start() {
    local profile="$1" cache="$2"
    shift 2
    (( $# > 0 )) || die 'start requires a run ID, benchmark name, or all'
    local run_id benchmark input_set input_desc binary options required omnet_ini
    local count=0 failures=0 base outdir stamp worker_pid current latest
    verify_gem5_build
    # HHMM_DDMMYYYY, e.g. m5out_mcf_1230_16092026
    stamp="$(date '+%H%M_%d%m%Y')"
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        ((count++))
        if ! validate_paths "$binary" "$required"; then
            printf '[%-23s] NOT STARTED: prerequisite failure\n' "$run_id" >&2
            ((failures++))
            continue
        fi
        latest="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        current="$(read_state "$latest")"
        if [[ "$current" == RUNNING ]]; then
            printf '[%-23s] ALREADY RUNNING: %s\n' "$run_id" "$latest"
            continue
        fi
        base="$(run_base "$benchmark")"
        outdir="$base/m5out_${run_id}_${stamp}"
        # Two runs of the same target within one minute would otherwise land in
        # the same directory.
        if [[ -e "$outdir" ]]; then
            local suffix=2
            while [[ -e "${outdir}_${suffix}" ]]; do suffix=$((suffix + 1)); done
            outdir="${outdir}_${suffix}"
        fi
        mkdir -p "$outdir/.runner"
        printf '%s\n' STARTING > "$outdir/.runner/status"
        printf '%s\n' "$profile" > "$outdir/.runner/profile"
        printf '%s\n' "$cache" > "$outdir/.runner/cache"
        printf '%s\n' "$run_id" > "$outdir/.runner/run_id"
        printf '%s\n' "$benchmark" > "$outdir/.runner/benchmark"
        ln -sfn "$outdir" "$(latest_link "$profile" "$cache" "$benchmark" "$run_id")"
        nohup "$SCRIPT_PATH" __worker "$profile" "$cache" "$run_id" "$outdir" \
            </dev/null > "$outdir/.runner/worker.log" 2>&1 &
        worker_pid=$!
        printf '%s\n' "$worker_pid" > "$outdir/.runner/worker.pid"
        printf '[%-23s] STARTED pid=%-7s input=%s\n' \
            "$run_id" "$worker_pid" "$input_desc"
        printf '  outdir=%s\n' "$outdir"
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
    printf '\nSelected: %d, prerequisite failures: %d\n' "$count" "$failures"
}

command_status() {
    local profile="$1" cache="$2"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini
    local count=0 state outdir pid started finished now elapsed
    printf '%-23s %-13s %-12s %-8s %-10s %s\n' RUN_ID INPUT_SET STATE PID ELAPSED INPUT
    printf '%-23s %-13s %-12s %-8s %-10s %s\n' \
        '-----------------------' '-------------' '------------' '--------' '----------' '-----'
    now="$(date +%s)"
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        ((count++))
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        state="$(read_state "$outdir")"
        pid='-'
        elapsed='-'
        if [[ -n "$outdir" ]]; then
            pid="$(file_value "$outdir/.runner/gem5.pid")"
            [[ -n "$pid" ]] || pid="$(file_value "$outdir/.runner/worker.pid")"
            [[ -n "$pid" ]] || pid='-'
            started="$(file_value "$outdir/.runner/started.epoch")"
            finished="$(file_value "$outdir/.runner/finished.epoch")"
            if [[ "$started" =~ ^[0-9]+$ ]]; then
                if [[ "$finished" =~ ^[0-9]+$ ]]; then
                    elapsed="$(format_duration "$((finished - started))")"
                else
                    elapsed="$(format_duration "$((now - started))")"
                fi
            fi
        fi
        printf '%-23s %-13s %-12s %-8s %-10s %s\n' \
            "$run_id" "$input_set" "$state" "$pid" "$elapsed" "$input_desc"
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
}

command_stop() {
    local profile="$1" cache="$2"
    shift 2
    (( $# > 0 )) || die 'stop requires a run ID, benchmark name, or all'
    local run_id benchmark input_set input_desc binary options required omnet_ini
    local count=0 outdir state pid
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        ((count++))
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        state="$(read_state "$outdir")"
        if [[ "$state" != RUNNING ]]; then
            printf '[%-23s] not running (state=%s)\n' "$run_id" "$state"
            continue
        fi
        pid="$(file_value "$outdir/.runner/worker.pid")"
        if [[ "$pid" =~ ^[0-9]+$ ]]; then
            kill -TERM "$pid"
            printf '[%-23s] stop requested (worker pid=%s)\n' "$run_id" "$pid"
        else
            printf '[%-23s] cannot stop: invalid worker PID\n' "$run_id" >&2
        fi
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
}

command_log() {
    local profile="$1" cache="$2" wanted_id="$3" lines="${4:-40}"
    local run_id benchmark input_set input_desc binary options required omnet_ini
    local found=0 outdir
    [[ "$lines" =~ ^[0-9]+$ ]] || die "LINES must be an integer"
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        [[ "$run_id" == "$wanted_id" ]] || continue
        found=1
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        [[ -n "$outdir" && -f "$outdir/nohup.log" ]] || die "no log for $wanted_id"
        printf '==> %s <==\n' "$outdir/nohup.log"
        tail -n "$lines" "$outdir/nohup.log"
    done < <(manifest "$profile")
    (( found == 1 )) || die "unknown run ID: $wanted_id"
}

command_results() {
    local profile="$1" cache="$2"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini
    local count=0 failures=0 outdir state
    [[ -x "$ANALYZER" || -f "$ANALYZER" ]] || die "analyzer not found: $ANALYZER"
    while IFS=$'\t' read -r run_id benchmark input_set input_desc binary options required omnet_ini; do
        ((count++))
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        state="$(read_state "$outdir")"
        if [[ "$state" != COMPLETED ]]; then
            printf '[%s] result unavailable: state=%s\n' "$run_id" "$state" >&2
            ((failures++))
            continue
        fi
        printf '\n===== %s | %s | %s =====\n' "$run_id" "$input_set" "$input_desc"
        python3 "$ANALYZER" --no-files "$outdir" || ((failures++))
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
    (( failures == 0 ))
}

main() {
    local command="${1:-help}"
    shift || true
    case "$command" in
      help|-h|--help)
        usage
        ;;
      list)
        command_list "${1:-test}"
        ;;
      check|start|status|stop|results)
        (( $# >= 2 )) || { usage >&2; exit 1; }
        valid_profile "$1" || die "invalid profile: $1"
        valid_cache "$2" || die "invalid cache: $2"
        "command_$command" "$@"
        ;;
      log)
        (( $# >= 3 )) || { usage >&2; exit 1; }
        valid_profile "$1" || die "invalid profile: $1"
        valid_cache "$2" || die "invalid cache: $2"
        command_log "$@"
        ;;
      __worker)
        (( $# == 4 )) || die 'invalid worker invocation'
        valid_profile "$1" || die "invalid profile: $1"
        valid_cache "$2" || die "invalid cache: $2"
        run_worker "$@"
        ;;
      *)
        usage >&2
        die "unknown command: $command"
        ;;
    esac
}

main "$@"
