#!/bin/bash
# Guard: isStackAddress() → false for BSS addresses
# Expected: ALL spill counters = 0
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATS="$SCRIPT_DIR/m5out/stats.txt"
[ ! -f "$STATS" ] && echo "ERROR: $STATS not found" && exit 1

extract() { grep -m1 "^${1}\b" "$STATS" | awk '{print $2}'; }
extract() { local v; v=$(grep -m1 "^${1}\b" "$STATS" | awk '{print $2}'); echo "${v:-0}"; }

LH=$(extract "system.cpu.dcache.spillLoadHits")
LM=$(extract "system.cpu.dcache.spillLoadMisses")
SH=$(extract "system.cpu.dcache.spillStoreHits")
SM=$(extract "system.cpu.dcache.spillStoreMisses")
L2LH=$(extract "system.l2.spillLoadHits")
L2LM=$(extract "system.l2.spillLoadMisses")
L2SH=$(extract "system.l2.spillStoreHits")
L2SM=$(extract "system.l2.spillStoreMisses")

echo "system.cpu.dcache.spillLoadHits    = $LH  (expect 0)"
echo "system.cpu.dcache.spillLoadMisses  = $LM  (expect 0)"
echo "system.cpu.dcache.spillStoreHits   = $SH  (expect 0)"
echo "system.cpu.dcache.spillStoreMisses = $SM  (expect 0)"
echo "system.l2.spillLoadHits            = $L2LH (expect 0)"
echo "system.l2.spillLoadMisses          = $L2LM (expect 0)"
echo "system.l2.spillStoreHits           = $L2SH (expect 0)"
echo "system.l2.spillStoreMisses         = $L2SM (expect 0)"

fail=0
for v in $LH $LM $SH $SM $L2LH $L2LM $L2SH $L2SM; do
    [ "$v" -ne 0 ] && fail=1
done

if [ "$fail" -eq 0 ]; then echo "PASS: negative/non_stack"; exit 0
else echo "FAIL: one or more spill counters != 0"; exit 1; fi
