#!/bin/bash
# Regression: the removed time window must not censor long-distance reloads.
# The legacy directory name is retained to avoid breaking existing scripts.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATS="$SCRIPT_DIR/m5out/stats.txt"
[ ! -f "$STATS" ] && echo "ERROR: $STATS not found" && exit 1

extract() { local v; v=$(grep -m1 "^${1}\b" "$STATS" | awk '{print $2}'); echo "${v:-0}"; }

LH=$(extract "system.cpu.dcache.spillLoadHits")
LM=$(extract "system.cpu.dcache.spillLoadMisses")
L2LH=$(extract "system.l2.spillLoadHits")
L2LM=$(extract "system.l2.spillLoadMisses")

echo "system.cpu.dcache.spillLoadHits   = $LH"
echo "system.cpu.dcache.spillLoadMisses = $LM  (L1 total must be 1)"
echo "system.l2.spillLoadHits           = $L2LH"
echo "system.l2.spillLoadMisses         = $L2LM (L2 total must equal L1 misses)"

fail=0
[ "$((LH + LM))" -ne 1 ] && fail=1
[ "$((L2LH + L2LM))" -ne "$LM" ] && fail=1

if [ "$fail" -eq 0 ]; then echo "PASS: long-distance reload survives"; exit 0
else echo "FAIL: long-distance spill pair was lost or cache levels disagree"; exit 1; fi
