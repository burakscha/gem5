#!/bin/bash
# run.sh — simulate the l1_hit spill-load micro-test
#
# Cache config (kept small to fit within MAX_SPILL_WINDOW):
#   L1 dcache : 1 kB, 4-way, 64 B  → 16 total lines
#   L2        : 8 kB, 4-way, 64 B  → 128 total lines
#   Memory    : SimpleMemory (30 ns flat latency)
#
# Usage:
#   cd <this directory>
#   make           # cross-compile test.riscv
#   bash run.sh    # simulate; output goes to m5out/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GEM5_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"

GEM5="$GEM5_ROOT/build/RISCV/gem5.opt"
CFG="$GEM5_ROOT/configs/deprecated/example/se.py"
BIN="$SCRIPT_DIR/test.riscv"
OUTDIR="$SCRIPT_DIR/m5out"

if [ ! -f "$BIN" ]; then
    echo "ERROR: $BIN not found — run 'make' first."
    exit 1
fi

mkdir -p "$OUTDIR"

echo "=== l1_hit: running gem5 ==="
"$GEM5" \
    --outdir="$OUTDIR" \
    "$CFG" \
    --cmd="$BIN" \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --l2cache \
    --l1d_size=1kB  --l1d_assoc=4 \
    --l2_size=8kB   --l2_assoc=4  \
    --mem-type=SimpleMemory \
    --mem-size=512MB \
    > "$OUTDIR/sim.log" 2>&1

echo "Done.  Stats: $OUTDIR/stats.txt"
echo "Run 'bash check.sh' to verify expected counters."
