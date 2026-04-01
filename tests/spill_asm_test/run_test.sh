#!/bin/bash
# run_test.sh — gem5 simulation + stat verification for spill_asm_test
#
# Usage:
#   ./run_test.sh          # run simulation
#   ./run_test.sh --check  # parse m5out/stats.txt, report pass/fail

set -e

GEM5_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GEM5="$GEM5_ROOT/build/RISCV/gem5.opt"
SE_PY="$GEM5_ROOT/configs/deprecated/example/se.py"
BINARY="$(dirname "$0")/spill_asm_test"
OUTDIR="$(dirname "$0")/m5out"

# Default gem5 cache geometry
L1D_SIZE=32kB
L1I_SIZE=32kB
L2_SIZE=1MB
L1D_ASSOC=8
L1I_ASSOC=8
L2_ASSOC=8

# --------------------------------------------------------------------------
# --check mode: parse stats.txt
# --------------------------------------------------------------------------
if [[ "$1" == "--check" ]]; then
    STATS="$OUTDIR/stats.txt"
    SPILL_LOG="$OUTDIR/riscv_spill_stats.txt"

    if [[ ! -f "$STATS" ]]; then
        echo "ERROR: $STATS not found. Run simulation first."
        exit 1
    fi

    echo "=== SpillDetector summary ==="
    if [[ -f "$SPILL_LOG" ]]; then
        grep -E "roi_spills|spill_rate|roi_loads|roi_stores|roi_instructions" "$SPILL_LOG" || true
    fi
    echo ""

    echo "=== Cache spill counters ==="
    if grep -qE "spillLoad" "$STATS"; then
        grep -E "spillLoad" "$STATS"
    else
        echo "WARNING: No spillLoad entries found in stats.txt"
        echo "         Did you rebuild gem5 after adding the stats?"
        exit 1
    fi
    echo ""

    # Extract values
    DCACHE_HITS=$(awk '/system\.cpu\.dcache\.spillLoadHits/{print $2}' "$STATS")
    DCACHE_MISS=$(awk '/system\.cpu\.dcache\.spillLoadMisses/{print $2}' "$STATS")

    PASS=1
    check() {
        local label="$1" got="$2" want="$3"
        if [[ "$got" == "$want" ]]; then
            printf "  PASS  %-45s = %s\n" "$label" "$got"
        else
            printf "  FAIL  %-45s = %s  (expected %s)\n" "$label" "$got" "$want"
            PASS=0
        fi
    }

    echo "--- Phase 1 checks ---"
    check "system.cpu.dcache.spillLoadHits"   "$DCACHE_HITS" "1"
    check "system.cpu.dcache.spillLoadMisses" "$DCACHE_MISS" "0"
    echo ""

    # Sanity: SpillDetector should also report roi_spills = 1
    ROI_SPILLS=$(grep "roi_spills" "$SPILL_LOG" 2>/dev/null | awk -F: '{gsub(/ /,"",$2); print $2}' || echo "?")
    echo "SpillDetector roi_spills reported: $ROI_SPILLS  (expected: 1)"
    echo ""

    if [[ "$PASS" == "1" ]]; then
        echo "ALL CHECKS PASSED — plumbing chain verified:"
        echo "  SpillDetector → SPILL_LOAD tag → dcache.spillLoadHits"
    else
        echo "SOME CHECKS FAILED"
        echo ""
        echo "Troubleshooting:"
        echo "  - FAIL spillLoadHits=0 : SpillDetector not detecting or tag not set"
        echo "    → check --debug-flags=SpillDetector output"
        echo "  - FAIL spillLoadHits=2+: unexpected extra stack sd/ld in ROI"
        echo "    → run 'make disasm' and look for extra sd/ld in main or other functions"
        echo "  - No spillLoad in stats  : gem5 not rebuilt after adding stats"
        echo "  - roi_spills != 1        : SpillDetector logic issue"
        exit 1
    fi
    exit 0
fi

# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------
if [[ ! -f "$BINARY" ]]; then
    echo "ERROR: $BINARY not found. Run 'make' first."
    exit 1
fi

mkdir -p "$OUTDIR"

echo "Running gem5 simulation..."
echo "  Binary : $BINARY"
echo "  Output : $OUTDIR"
echo ""

"$GEM5" \
    -d "$OUTDIR" \
    "$SE_PY" \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --l2cache \
    --l1d_size=$L1D_SIZE \
    --l1i_size=$L1I_SIZE \
    --l2_size=$L2_SIZE \
    --l1d_assoc=$L1D_ASSOC \
    --l1i_assoc=$L1I_ASSOC \
    --l2_assoc=$L2_ASSOC \
    -c "$BINARY"

echo ""
echo "Simulation done. Run '$0 --check' to verify stats."
