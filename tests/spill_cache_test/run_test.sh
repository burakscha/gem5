#!/bin/bash
# run_test.sh — gem5 SE mode simulation for spill cache hit/miss verification
#
# Modes:
#   ./run_test.sh             # Phase 2: HIT + MISS tests
#   ./run_test.sh --phase1    # Phase 1: HIT only (safest first step)
#   ./run_test.sh --check     # Parse stats.txt from last run, report pass/fail
#
# Cache geometry:
#   L1D = 32 KB, 8-way    (default gem5)
#   L2  = 1 MB, 8-way     (upped from 256KB so 256KB evict_buf fits in L2)
#   EVICT_BYTES = 256 KB   (> L1D for eviction, < L2 for warmup)

set -e

GEM5_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GEM5="$GEM5_ROOT/build/RISCV/gem5.opt"
SE_PY="$GEM5_ROOT/configs/deprecated/example/se.py"
BINARY="$(dirname "$0")/test_spill_cache"
OUTDIR="$(dirname "$0")/m5out"

L1D_SIZE=32kB
L1I_SIZE=32kB
L2_SIZE=1MB          # Must be > EVICT_BYTES (256KB) so warmup fits in L2
L1D_ASSOC=8
L1I_ASSOC=8
L2_ASSOC=8

# --------------------------------------------------------------------------
# --check mode
# --------------------------------------------------------------------------
if [[ "$1" == "--check" ]]; then
    STATS="$OUTDIR/stats.txt"
    if [[ ! -f "$STATS" ]]; then
        echo "ERROR: $STATS not found. Run simulation first."
        exit 1
    fi

    SPILL_LOG="$OUTDIR/riscv_spill_stats.txt"
    echo "=== Spill detector summary ==="
    if [[ -f "$SPILL_LOG" ]]; then
        grep -E "roi_spills|spill_rate" "$SPILL_LOG" || true
    fi
    echo ""

    echo "=== Cache spill stats ==="
    grep -E "spillLoad" "$STATS" || echo "(no spillLoad entries found — is this a new gem5 build?)"
    echo ""

    DCACHE_HITS=$(grep "system.cpu.dcache.spillLoadHits"   "$STATS" 2>/dev/null | awk '{print $2}')
    DCACHE_MISS=$(grep "system.cpu.dcache.spillLoadMisses" "$STATS" 2>/dev/null | awk '{print $2}')
    L2_HITS=$(grep     "system.l2cache.spillLoadHits"      "$STATS" 2>/dev/null | awk '{print $2}')
    L2_MISS=$(grep     "system.l2cache.spillLoadMisses"    "$STATS" 2>/dev/null | awk '{print $2}')

    # Detect which phase was run from the spill log
    ROI_SPILLS=$(grep "roi_spills" "$SPILL_LOG" 2>/dev/null | awk -F: '{print $2}' | tr -d ' ' || echo "")

    PASS=1
    check_eq() {
        local label="$1" got="$2" want="$3"
        if [[ "$got" == "$want" ]]; then
            echo "  PASS  $label = $got"
        else
            echo "  FAIL  $label = $got  (expected $want)"
            PASS=0
        fi
    }
    check_ge() {
        local label="$1" got="$2" want="$3"
        if [[ -n "$got" ]] && (( got >= want )); then
            echo "  PASS  $label = $got  (>= $want)"
        else
            echo "  FAIL  $label = $got  (expected >= $want)"
            PASS=0
        fi
    }

    # Phase 1: only test_l1_hit ran → roi_spills = 1 → only hits
    if [[ "$ROI_SPILLS" == "1" ]]; then
        echo "--- Phase 1 checks (HIT only) ---"
        check_eq "dcache.spillLoadHits"   "$DCACHE_HITS" "1"
        check_eq "dcache.spillLoadMisses" "$DCACHE_MISS" "0"
    else
        # Phase 2: both tests ran → roi_spills = 2
        echo "--- Phase 2 checks (HIT + MISS) ---"
        check_eq "dcache.spillLoadHits"   "$DCACHE_HITS" "1"
        check_eq "dcache.spillLoadMisses" "$DCACHE_MISS" "1"
        check_eq "l2cache.spillLoadHits"  "$L2_HITS"     "1"
        check_eq "l2cache.spillLoadMisses" "$L2_MISS"    "0"
    fi

    echo ""
    if [[ "$PASS" == "1" ]]; then
        echo "ALL CHECKS PASSED"
    else
        echo "SOME CHECKS FAILED"
        echo ""
        echo "Troubleshooting:"
        echo "  - Unexpected hits?  prologue ra may be counted → check objdump for 'c.sdsp ra' inside test_l1_miss"
        echo "  - No spillLoad entries?  gem5 was not rebuilt after adding the stats"
        echo "  - Eviction failed?  increase EVICT_BYTES: make EVICT_BYTES=\$((512*1024))"
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

PHASE=2
if [[ "$1" == "--phase1" ]]; then
    PHASE=1
fi

mkdir -p "$OUTDIR"

echo "Running gem5 simulation (phase $PHASE)..."
echo "  Binary  : $BINARY"
echo "  Options : $PHASE"
echo "  Output  : $OUTDIR"
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
    -c "$BINARY" \
    --options="$PHASE"

echo ""
echo "Done. Run '$0 --check' to verify stats."
