#!/bin/bash
# check.sh — verify expected spill-load stats for the l1miss_l2miss test
#
# What this test proves:
#   A spill reload that misses in both L1 and L2 (must fetch from DRAM)
#   increments spillLoadMisses at BOTH cache levels.
#   This validates the deepest path of the tagging chain.
#
# Pass conditions:
#   system.cpu.dcache.spillLoadMisses  >= 1   (x's line evicted from L1)
#   system.l2.spillLoadMisses          >= 1   (x's line also evicted from L2)
#
# Note: dcache.spillLoadHits and l2.spillLoadHits may also be > 0 for
# other spill reloads (e.g., function-call ra push/pop pairs that happen
# to hit before the flush reaches them).  That does not affect the result.
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
echo " TEST: l1miss_l2miss"
echo "========================================"
printf "  dcache.spillLoadHits   = %-8s  (any value OK)\n"  "$L1H"
printf "  dcache.spillLoadMisses = %-8s  (expected >= 1)\n" "$L1M"
printf "  l2.spillLoadHits       = %-8s  (any value OK)\n"  "$L2H"
printf "  l2.spillLoadMisses     = %-8s  (expected >= 1)\n" "$L2M"
echo "----------------------------------------"

PASS=1

if ! [ "$L1M" -gt 0 ] 2>/dev/null; then
    echo "FAIL: dcache.spillLoadMisses should be >= 1 (got '$L1M')"
    echo "      → x's line was not evicted from L1."
    echo "        FLUSH_LINES=160 >> L1 capacity (16 lines); check run.sh."
    PASS=0
fi

if ! [ "$L2M" -gt 0 ] 2>/dev/null; then
    echo "FAIL: l2.spillLoadMisses should be >= 1 (got '$L2M')"
    echo "      → x's line survived in L2 despite the full flush."
    echo "        FLUSH_LINES=160 / 32 L2-sets = 5 per set (4-way → overflow)."
    echo "        Possible causes:"
    echo "          1. L2 is larger than expected; verify --l2_size=8kB."
    echo "          2. The SPILL_LOAD flag was not forwarded from dcache to L2."
    echo "             Check BaseCache::incMissCount propagation."
    PASS=0
fi

echo ""
if [ "$PASS" -eq 1 ]; then
    echo "RESULT: PASS"
else
    echo "RESULT: FAIL"
fi

exit $((1 - PASS))
