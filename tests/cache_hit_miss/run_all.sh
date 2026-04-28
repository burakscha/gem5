#!/bin/bash
# run_all.sh — build and run all spill-load cache micro-tests
#
# Runs each test in sequence:
#   1. build (make)
#   2. simulate (run.sh)
#   3. check results (check.sh)
#
# Usage:
#   cd gem5/tests/cache_hit_miss
#   bash run_all.sh
#
# Exit code: 0 if all tests pass, 1 if any fail.

set -e

CACHE_HIT_MISS_DIR="$(cd "$(dirname "$0")" && pwd)"

TESTS=(
    "load/l1_hit"
    "load/l1miss_l2hit"
    "load/l1miss_l2miss"
    "store/l1_hit"
    "store/l1_miss"
    "store/l1miss_l2miss"
    "negative/non_stack"
    "negative/roi_outside"
    "negative/size_mismatch"
    "negative/window_expired"
)

PASS_COUNT=0
FAIL_COUNT=0
FAILED_TESTS=()

for TEST in "${TESTS[@]}"; do
    DIR="$CACHE_HIT_MISS_DIR/$TEST"
    echo ""
    echo "════════════════════════════════════════"
    echo " $TEST"
    echo "════════════════════════════════════════"

    if [ ! -d "$DIR" ]; then
        echo "SKIP: directory not found: $DIR"
        continue
    fi

    # Build
    echo "--- make ---"
    make -C "$DIR" --no-print-directory

    # Simulate
    echo "--- run.sh ---"
    bash "$DIR/run.sh"

    # Check
    echo "--- check.sh ---"
    if bash "$DIR/check.sh"; then
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAILED_TESTS+=("$TEST")
    fi
done

echo ""
echo "════════════════════════════════════════"
echo " SUMMARY"
echo "════════════════════════════════════════"
echo "  Passed : $PASS_COUNT"
echo "  Failed : $FAIL_COUNT"

if [ "${#FAILED_TESTS[@]}" -gt 0 ]; then
    echo ""
    echo "  Failed tests:"
    for T in "${FAILED_TESTS[@]}"; do
        echo "    - $T"
    done
    echo ""
    exit 1
fi

echo ""
echo "All tests PASSED."
exit 0
