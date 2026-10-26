#!/bin/bash
# Guard: inside_roi == false at load time
# Expected: spillLoad counters = 0  (spillStore* may be non-zero — not checked)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATS="$SCRIPT_DIR/m5out/stats.txt"
[ ! -f "$STATS" ] && echo "ERROR: $STATS not found" && exit 1

extract() { local v; v=$(grep -m1 "^${1}\b" "$STATS" | awk '{print $2}'); echo "${v:-0}"; }

LH=$(extract "system.cpu.dcache.spillLoadHits")
LM=$(extract "system.cpu.dcache.spillLoadMisses")
L2LH=$(extract "system.l2.spillLoadHits")
L2LM=$(extract "system.l2.spillLoadMisses")

echo "system.cpu.dcache.spillLoadHits   = $LH  (expect 0)"
echo "system.cpu.dcache.spillLoadMisses = $LM  (expect 0)"
echo "system.l2.spillLoadHits           = $L2LH (expect 0)"
echo "system.l2.spillLoadMisses         = $L2LM (expect 0)"

fail=0
for v in $LH $LM $L2LH $L2LM; do
    [ "$v" -ne 0 ] && fail=1
done

if [ "$fail" -eq 0 ]; then echo "PASS: negative/roi_outside"; exit 0
else echo "FAIL: spillLoad counter != 0 outside ROI"; exit 1; fi
