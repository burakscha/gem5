/*
 * l1_hit/test.c
 *
 * PURPOSE
 * -------
 * Verify the complete tagging pipeline for a spill reload that hits in L1:
 *
 *   SpillDetector: store → store_map entry
 *   SpillDetector: load  → SPILL_LOAD flag set on the Request
 *   BaseCache::incHitCount: sees isSpillLoad() && isDemand() → spillLoadHits++
 *
 * SCENARIO
 * --------
 *   1. ROI starts (m5_work_begin).
 *   2. Spill store: write `x` to a stack location.
 *      The cache line is now in L1.
 *   3. Spill reload: read `x` immediately.
 *      No eviction happened → L1 hit.
 *   4. ROI ends (m5_work_end).
 *
 * EXPECTED STATS (m5out/stats.txt)
 * ---------------------------------
 *   system.cpu.dcache.spillLoadHits   >= 1   (spill reload found in L1)
 *   system.cpu.dcache.spillLoadMisses  = 0   (nothing was evicted)
 *   system.l2.spillLoadHits            = 0   (L2 never consulted)
 *   system.l2.spillLoadMisses          = 0
 *
 * Note: the count may be > 1 because the function call wrapper around
 * m5_work_begin pushes `ra` onto the stack inside the ROI; that push/pop
 * pair is also detected as a spill reload, and is an L1 hit.
 *
 * CACHE CONFIG (see run.sh)
 *   L1 dcache : 1 kB, 4-way, 64 B/block  (16 total lines)
 *   L2        : 8 kB, 4-way, 64 B/block  (128 total lines)
 *   Memory    : SimpleMemory (30 ns)
 */

#include <gem5/m5ops.h>
#include <stdint.h>

int main(void)
{
    m5_work_begin(0, 0);

    /*
     * Spill store: `volatile` forces the compiler to emit a real store
     * instruction to the stack.  SpillDetector adds (address → StoreInfo)
     * to store_map.
     */
    volatile int64_t x;
    x = 0xA5A5A5A5A5A5A5A5LL;

    /*
     * Spill reload: load from the same stack address.
     * SpillDetector finds the store_map entry, isLikelySpill() passes
     * (temporal order + size match + isStackAddress), inside_roi = true
     * → returns true → Request::SPILL_LOAD flag set.
     *
     * The cache line is still hot in L1 (no eviction between the store
     * and this load) → BaseCache::incHitCount → spillLoadHits++.
     */
    int64_t val = x;

    m5_work_end(0, 0);

    /* Prevent dead-code elimination */
    return (int)(val & 1);
}
