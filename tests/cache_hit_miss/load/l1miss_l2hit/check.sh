#!/bin/bash
# check.sh — verify expected spill-load stats for the l1miss_l2hit test
#
# What this test proves:
#   A spill reload that misses in L1 but finds its line in L2 increments
#   spillLoadMisses at the dcache AND spillLoadHits at L2.
#   Nothing should reach DRAM as a spill.
#
# Pass conditions:
#   system.cpu.dcache.spillLoadMisses  >= 1   (x's line was evicted from L1)
#   system.l2.spillLoadHits            >= 1   (x's line was found in L2)
#   system.l2.spillLoadMisses           = 0   (no spill missed both levels)
#
# Note: dcache.spillLoadHits may also be > 0 (spills detected before the
# flush, e.g., inside m5_work_begin's wrapper frame), which is fine.
#
# Usage:
#   bash check.sh              (reads m5out/stats.txt by default)
#   bash check.sh /path/to/stats.txt

set -e

STATS="${1:-$(dirname "$0")/m5out/stats.txt}"

if [ ! -f "$STATS" ]; then
    echo "ERROR: stats file not found: $STATS"
    echo "Run 'bash run.sh' first."
    exit 1
fi

get_stat() {
    local name="$1"
    local val
    val=$(grep "^${name} " "$STATS" | awk '{print $2}')
    echo "${val:-0}"
}

L1H=$(get_stat "system.cpu.dcache.spillLoadHits")
L1M=$(get_stat "system.cpu.dcache.spillLoadMisses")
L2H=$(get_stat "system.l2.spillLoadHits")
L2M=$(get_stat "system.l2.spillLoadMisses")

echo "========================================"
echo " TEST: l1miss_l2hit"
echo "========================================"
printf "  dcache.spillLoadHits   = %-8s  (any value OK)\n"  "$L1H"
printf "  dcache.spillLoadMisses = %-8s  (expected >= 1)\n" "$L1M"
printf "  l2.spillLoadHits       = %-8s  (expected >= 1)\n" "$L2H"
printf "  l2.spillLoadMisses     = %-8s  (expected  = 0)\n" "$L2M"
echo "----------------------------------------"

PASS=1

if ! [ "$L1M" -gt 0 ] 2>/dev/null; then
    echo "FAIL: dcache.spillLoadMisses should be >= 1 (got '$L1M')"
    echo "      → x's cache line was not evicted from L1 by the flush."
    echo "        Check FLUSH_LINES (32) vs L1 capacity (16 lines)."
    PASS=0
fi

if ! [ "$L2H" -gt 0 ] 2>/dev/null; then
    echo "FAIL: l2.spillLoadHits should be >= 1 (got '$L2H')"
    echo "      → x's write-back did not survive in L2, or the SPILL_LOAD"
    echo "        flag was not propagated to the L2 request."
    echo "        Check that --l2cache is present in run.sh."
    PASS=0
fi

if ! [ "$L2M" -eq 0 ] 2>/dev/null; then
    echo "FAIL: l2.spillLoadMisses should be 0 (got '$L2M')"
    echo "      → A spill reload reached DRAM; x's line was evicted from L2."
    echo "        The flush array (32 lines) may have overflowed L2 (128 lines)."
    echo "        This should not happen — check cache config in run.sh."
    PASS=0
fi

echo ""
if [ "$PASS" -eq 1 ]; then
    echo "RESULT: PASS"
else
    echo "RESULT: FAIL"
fi

exit $((1 - PASS))
