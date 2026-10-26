#!/bin/bash
# check.sh — verify store/l1_hit expected counters
#
# Expected outcome:
#   dcache.spillStoreHits   >= 1   (volatile store inside ROI hits L1)
#   dcache.spillStoreMisses  = 0   (no misses expected)
#   l2.spillStoreHits        = 0   (L2 never sees a store-hit packet)
#   l2.spillStoreMisses      = 0   (write-allocate RFO strips SPILL_STORE flag)
#
# NOTE: l2.spillStore* are architecturally always 0 for stores because
# a write-miss at L1 generates an RFO (Read-For-Ownership) packet that
# does NOT carry the SPILL_STORE flag.  Only dcache store counters are
# meaningful.

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

SH=$(extract "system.cpu.dcache.spillStoreHits")
SM=$(extract "system.cpu.dcache.spillStoreMisses")
L2SH=$(extract "system.l2.spillStoreHits")
L2SM=$(extract "system.l2.spillStoreMisses")

echo "system.cpu.dcache.spillStoreHits   = $SH   (expect >= 1)"
echo "system.cpu.dcache.spillStoreMisses = $SM   (expect  = 0)"
echo "system.l2.spillStoreHits           = $L2SH (expect  = 0)"
echo "system.l2.spillStoreMisses         = $L2SM (expect  = 0)"

if [ "$SH" -lt 1 ]; then
    echo "FAIL: dcache.spillStoreHits < 1 (got $SH)"
    fail=1
fi
if [ "$SM" -ne 0 ]; then
    echo "FAIL: dcache.spillStoreMisses != 0 (got $SM)"
    fail=1
fi
if [ "$L2SH" -ne 0 ]; then
    echo "FAIL: l2.spillStoreHits != 0 (got $L2SH)"
    fail=1
fi
if [ "$L2SM" -ne 0 ]; then
    echo "FAIL: l2.spillStoreMisses != 0 (got $L2SM)"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "PASS: store/l1_hit"
    exit 0
else
    exit 1
fi
