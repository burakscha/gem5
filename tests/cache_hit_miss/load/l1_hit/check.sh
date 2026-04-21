#!/bin/bash
# check.sh — verify expected spill-load stats for the l1_hit test
#
# What this test proves:
#   A spill reload that finds its line in L1 increments spillLoadHits at the
#   dcache and ONLY there.  No miss counter should increment.
#
# Pass conditions:
#   system.cpu.dcache.spillLoadHits   >= 1   (tagged spill reload hit in L1)
#   system.cpu.dcache.spillLoadMisses  = 0   (nothing evicted between store/load)
#   system.l2.spillLoadHits            = 0   (L2 never consulted for a spill)
#   system.l2.spillLoadMisses          = 0
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

# Extract a single scalar stat.  Returns 0 if the line is absent (gem5
# does print zero-valued stats, but be defensive).
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
echo " TEST: l1_hit"
echo "========================================"
printf "  dcache.spillLoadHits   = %-8s  (expected >= 1)\n" "$L1H"
printf "  dcache.spillLoadMisses = %-8s  (expected  = 0)\n" "$L1M"
printf "  l2.spillLoadHits       = %-8s  (expected  = 0)\n" "$L2H"
printf "  l2.spillLoadMisses     = %-8s  (expected  = 0)\n" "$L2M"
echo "----------------------------------------"

PASS=1

if ! [ "$L1H" -gt 0 ] 2>/dev/null; then
    echo "FAIL: dcache.spillLoadHits should be >= 1 (got '$L1H')"
    echo "      → SpillDetector did not tag any load as SPILL_LOAD, or"
    echo "        the ROI was not entered (check m5_work_begin/end calls)."
    PASS=0
fi

if ! [ "$L1M" -eq 0 ] 2>/dev/null; then
    echo "FAIL: dcache.spillLoadMisses should be 0 (got '$L1M')"
    echo "      → Some tagged spill reload missed L1; the flush between"
    echo "        store and load is unexpected in this test."
    PASS=0
fi

if ! [ "$L2H" -eq 0 ] 2>/dev/null; then
    echo "FAIL: l2.spillLoadHits should be 0 (got '$L2H')"
    echo "      → A spill reload went to L2; it should not happen here."
    PASS=0
fi

if ! [ "$L2M" -eq 0 ] 2>/dev/null; then
    echo "FAIL: l2.spillLoadMisses should be 0 (got '$L2M')"
    PASS=0
fi

echo ""
if [ "$PASS" -eq 1 ]; then
    echo "RESULT: PASS"
else
    echo "RESULT: FAIL"
fi

exit $((1 - PASS))
