#!/bin/bash
# check.sh — verify store/l1_miss expected counters
#
# Expected outcome:
#   dcache.spillStoreMisses >= 1   (volatile store inside ROI misses L1)
#   dcache.spillStoreHits    = 0   (stack line was evicted before ROI)
#   l2.spillStoreHits       >= 1   (L1's write-miss RFO hits L2 with SPILL_STORE)
#   l2.spillStoreMisses      = 0   (L2 has the line — flush only evicted from L1)
#
# KEY INSIGHT: When an L1 write-miss occurs, gem5 sends a write-allocate
# RFO (ReadExReq) packet to L2.  That packet DOES inherit the SPILL_STORE
# flag from the original store request.  Therefore l2.spillStoreHits and
# l2.spillStoreMisses ARE meaningful for stores, contrary to expectations.
#
# Design note: 32 flush lines (2 kB) evict the stack line from L1 but NOT
# from L2 (L2 = 8 kB = 128 lines; 32 flush lines keep the stack line warm
# in L2).  So the L1 write-miss RFO hits L2 → l2.spillStoreHits = 1.

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
L2SH=$(extract "system.l2.spillStoreHits")
L2SM=$(extract "system.l2.spillStoreMisses")

echo "system.cpu.dcache.spillStoreMisses = $SM   (expect >= 1)"
echo "system.cpu.dcache.spillStoreHits   = $SH   (expect  = 0)"
echo "system.l2.spillStoreHits           = $L2SH (expect >= 1, RFO hits L2)"
echo "system.l2.spillStoreMisses         = $L2SM (expect  = 0)"

if [ "$SM" -lt 1 ]; then
    echo "FAIL: dcache.spillStoreMisses < 1 (got $SM)"
    fail=1
fi
if [ "$SH" -ne 0 ]; then
    echo "FAIL: dcache.spillStoreHits != 0 (got $SH)"
    fail=1
fi
if [ "$L2SH" -lt 1 ]; then
    echo "FAIL: l2.spillStoreHits < 1 (got $L2SH) — RFO should hit L2"
    fail=1
fi
if [ "$L2SM" -ne 0 ]; then
    echo "FAIL: l2.spillStoreMisses != 0 (got $L2SM)"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "PASS: store/l1_miss"
    exit 0
else
    exit 1
fi
