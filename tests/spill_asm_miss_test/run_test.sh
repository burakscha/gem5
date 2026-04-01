#!/bin/bash
set -e

GEM5_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GEM5="$GEM5_ROOT/build/RISCV/gem5.opt"
SE_PY="$GEM5_ROOT/configs/deprecated/example/se.py"
BINARY="$(dirname "$0")/spill_miss_test"
OUTDIR="$(dirname "$0")/m5out"

if [[ "$1" == "--check" ]]; then
    STATS="$OUTDIR/stats.txt"
    SPILL_LOG="$OUTDIR/riscv_spill_stats.txt"
    [[ -f "$STATS" ]] || { echo "ERROR: run simulation first"; exit 1; }

    echo "=== SpillDetector summary ==="
    grep -E "roi_spills|roi_stores|roi_loads|roi_instructions|spill_rate" "$SPILL_LOG" || true
    echo ""
    echo "=== Cache spill counters ==="
    grep "spillLoad" "$STATS" || { echo "WARNING: no spillLoad entries — rebuild gem5?"; exit 1; }
    echo ""

    DCACHE_HITS=$(awk '/system\.cpu\.dcache\.spillLoadHits/{print $2}'   "$STATS")
    DCACHE_MISS=$(awk '/system\.cpu\.dcache\.spillLoadMisses/{print $2}' "$STATS")
    L2_HITS=$(awk     '/system\.l2\.spillLoadHits/{print $2}'            "$STATS")
    L2_MISS=$(awk     '/system\.l2\.spillLoadMisses/{print $2}'          "$STATS")

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

    echo "--- Miss test checks ---"
    check "system.cpu.dcache.spillLoadHits"   "$DCACHE_HITS" "0"
    check "system.cpu.dcache.spillLoadMisses" "$DCACHE_MISS" "1"
    check "system.l2.spillLoadHits"           "$L2_HITS"     "1"
    check "system.l2.spillLoadMisses"         "$L2_MISS"     "0"
    echo ""

    ROI_SPILLS=$(grep "roi_spills" "$SPILL_LOG" 2>/dev/null | awk -F: '{gsub(/ /,"",$2); print $2}' || echo "?")
    echo "SpillDetector roi_spills: $ROI_SPILLS  (expected: 1)"
    echo ""

    if [[ "$PASS" == "1" ]]; then
        echo "ALL CHECKS PASSED"
        echo "  SpillDetector → SPILL_LOAD → dcache MISS → L2 HIT chain verified"
    else
        echo "SOME CHECKS FAILED"
        echo ""
        echo "Troubleshooting:"
        echo "  - dcache.spillLoadMisses=0: eviction may have failed → increase EVICT_BYTES"
        echo "    Rebuild: edit .equ EVICT_BYTES in spill_miss_test.S (try 1MB)"
        echo "  - l2.spillLoadHits=0: stack line not in L2 after eviction (check cache policy)"
        echo "  - dcache.spillLoadHits=1: eviction failed, ld still hit L1D"
        exit 1
    fi
    exit 0
fi

[[ -f "$BINARY" ]] || { echo "ERROR: run 'make' first"; exit 1; }
mkdir -p "$OUTDIR"

echo "Running gem5 simulation (miss test)..."
echo "  Binary : $BINARY"
echo "  Output : $OUTDIR"
echo ""

"$GEM5" -d "$OUTDIR" "$SE_PY" \
    --cpu-type=TimingSimpleCPU \
    --caches --l2cache \
    --l1d_size=32kB --l1i_size=32kB \
    --l2_size=1MB \
    --l1d_assoc=8 --l1i_assoc=8 --l2_assoc=8 \
    -c "$BINARY"

echo ""
echo "Done. Run '$0 --check' to verify."
