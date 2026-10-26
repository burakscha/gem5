#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GEM5_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
GEM5="$GEM5_ROOT/build/RISCV/gem5.opt"
CFG="$GEM5_ROOT/configs/deprecated/example/se.py"
BIN="$SCRIPT_DIR/test.riscv"
OUTDIR="$SCRIPT_DIR/m5out"
[ ! -f "$BIN" ] && echo "ERROR: $BIN not found — run 'make' first." && exit 1
mkdir -p "$OUTDIR"
echo "=== negative/non_stack: running gem5 ==="
"$GEM5" --outdir="$OUTDIR" "$CFG" --cmd="$BIN" \
    --cpu-type=TimingSimpleCPU --caches --l2cache \
    --l1d_size=1kB --l1d_assoc=4 \
    --l2_size=8kB  --l2_assoc=4  \
    --mem-type=SimpleMemory --mem-size=512MB \
    > "$OUTDIR/sim.log" 2>&1
echo "Done. Stats: $OUTDIR/stats.txt"
