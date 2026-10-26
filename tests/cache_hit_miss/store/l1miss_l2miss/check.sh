#!/bin/bash
# check.sh — verify store/l1miss_l2miss expected counters
#
# Expected outcome:
#   dcache.spillStoreMisses >= 1   (L1 write-miss: stack line evicted)
#   dcache.spillStoreHits    = 0   (line was evicted before ROI)
#   l2.spillStoreMisses     >= 1   (RFO with SPILL_STORE also misses L2)
#   l2.spillStoreHits        = 0   (L2 evicted → miss, not hit)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATS="$SCRIPT_DIR/m5out/stats.txt"

if [ ! -f "$STATS" ]; then
    echo "ERROR: $STATS not found — run 'bash run.sh' first."
    exit 1
fi

fail=0

extract() {
    local key="$1"
    local val
    val=$(grep -m1 "^${key}\b" "$STATS" | awk '{print $2}')
    echo "${val:-0}"
}

SM=$(extract "system.cpu.dcache.spillStoreMisses")
SH=$(extract "system.cpu.dcache.spillStoreHits")
L2SM=$(extract "system.l2.spillStoreMisses")
L2SH=$(extract "system.l2.spillStoreHits")

echo "system.cpu.dcache.spillStoreMisses = $SM   (expect >= 1)"
echo "system.cpu.dcache.spillStoreHits   = $SH   (expect  = 0)"
echo "system.l2.spillStoreMisses         = $L2SM (expect >= 1)"
echo "system.l2.spillStoreHits           = $L2SH (expect  = 0)"

if [ "$SM" -lt 1 ]; then
    echo "FAIL: dcache.spillStoreMisses < 1 (got $SM)"
    fail=1
fi
if [ "$SH" -ne 0 ]; then
    echo "FAIL: dcache.spillStoreHits != 0 (got $SH)"
    fail=1
fi
if [ "$L2SM" -lt 1 ]; then
    echo "FAIL: l2.spillStoreMisses < 1 (got $L2SM)"
    fail=1
fi
if [ "$L2SH" -ne 0 ]; then
    echo "FAIL: l2.spillStoreHits != 0 (got $L2SH)"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "PASS: store/l1miss_l2miss"
    exit 0
else
    exit 1
fi
