#!/bin/bash
# run_deepsjeng.sh — run deepsjeng with test / train / ref inputs and analyze results.
#
# Usage:
#   bash run_deepsjeng.sh [test|train|ref|all]   (default: all)
#   bash run_deepsjeng.sh --status               (check running PIDs)
#   bash run_deepsjeng.sh --analyze              (parse stats, no run)
#
# Outputs go to:
#   benchmarks/deepsjeng/m5out_new_test/
#   benchmarks/deepsjeng/m5out_new_train/
#   benchmarks/deepsjeng/m5out_new_ref/

set -e

GEM5_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GEM5="$GEM5_ROOT/build/RISCV/gem5.opt"
SE_PY="$GEM5_ROOT/configs/deprecated/example/se.py"
BENCH_DIR="$GEM5_ROOT/benchmarks/deepsjeng"
BIN="$BENCH_DIR/deepsjeng_r.riscv"
OPTS="--cpu-type=TimingSimpleCPU --caches --mem-size=4GB"

# ── status / analyze shortcuts ────────────────────────────────────────────────
if [[ "$1" == "--status" ]]; then
    echo "=== Running gem5 processes ==="
    ps aux | grep gem5 | grep deepsjeng | grep -v grep || echo "  (none)"
    for sz in test train ref; do
        log="$BENCH_DIR/m5out_new_$sz/nohup.log"
        stats="$BENCH_DIR/m5out_new_$sz/stats.txt"
        if [ -f "$stats" ] && [ -s "$stats" ]; then
            echo "$sz: DONE  ($(wc -l < $stats) stat lines)"
        elif [ -f "$log" ]; then
            echo "$sz: RUNNING  ($(wc -l < $log) log lines)"
        else
            echo "$sz: not started"
        fi
    done
    exit 0
fi

if [[ "$1" == "--analyze" ]]; then
    python3 "$GEM5_ROOT/benchmarks/analyze_spills.py" deepsjeng
    exit 0
fi

# ── helpers ───────────────────────────────────────────────────────────────────
launch() {
    local sz="$1"
    local input="$BENCH_DIR/${sz}.txt"
    local outdir="$BENCH_DIR/m5out_new_${sz}"

    [ -f "$input" ] || { echo "ERROR: $input not found"; exit 1; }
    mkdir -p "$outdir"

    echo "Launching deepsjeng $sz → $outdir"
    nohup "$GEM5" \
        --outdir="$outdir" "$SE_PY" \
        --cmd="$BIN" \
        --options="$BENCH_DIR/${sz}.txt" \
        $OPTS \
        > "$outdir/nohup.log" 2>&1 &
    echo "  PID=$!  input=${sz}.txt"
}

# ── dispatch ──────────────────────────────────────────────────────────────────
SIZES="${1:-all}"
[[ "$SIZES" == "all" ]] && SIZES="test train ref"

for sz in $SIZES; do
    case "$sz" in
        test|train|ref) launch "$sz" ;;
        *) echo "Unknown size '$sz' — use test, train, ref, or all"; exit 1 ;;
    esac
done

echo ""
echo "Check progress:  bash run_deepsjeng.sh --status"
echo "Analyze results: bash run_deepsjeng.sh --analyze"
