/*
 * l1miss_l2hit/test.c
 *
 * PURPOSE
 * -------
 * Verify that a spill reload which misses in L1 but hits in L2 increments
 * the right counters in the right caches:
 *
 *   system.cpu.dcache.spillLoadMisses  (L1 missed → request forwarded to L2)
 *   system.l2.spillLoadHits            (L2 had the line → hit)
 *
 * SCENARIO
 * --------
 *   1. ROI starts.
 *   2. Spill store: write `x` to a stack location.
 *      The dirty cache line is now in L1.
 *   3. L1 flush: load FLUSH_LINES (32) unique 64-byte-aligned entries from
 *      flush_buf (global BSS, not stack → not detected as spill reloads).
 *      - 32 lines > 16 total L1 lines → L1 is fully replaced.
 *      - The dirty `x` line is written back to L2 (dirty eviction policy).
 *      - 32 flush lines < 128 total L2 lines → `x` line stays in L2.
 *   4. Spill reload: read `x`.
 *      L1 miss (evicted) → L2 hit (written-back line still there).
 *   5. ROI ends.
 *
 * EXPECTED STATS
 * --------------
 *   system.cpu.dcache.spillLoadMisses  >= 1   (x missed in L1)
 *   system.l2.spillLoadHits            >= 1   (x found in L2)
 *   system.l2.spillLoadMisses           = 0   (nothing missed both levels)
 *
 * Note: flush_l1() pushes `ra` onto its own stack frame inside the ROI.
 * That ra push/pop pair is also tagged as a spill reload.  Since ra is
 * evicted by the same flush loop, it too will be an L1-miss/L2-hit, adding
 * to the >= 1 counts but not violating the == 0 condition.
 *
 * TIMING SAFETY (MAX_SPILL_WINDOW = 10,000,000 ticks = 10 µs)
 *   32 cold DRAM accesses × ~35,000 ticks each ≈ 1,120,000 ticks << 10 µs.
 *
 * CACHE CONFIG (see run.sh)
 *   L1 dcache : 1 kB, 4-way, 64 B/block  (16 total lines)
 *   L2        : 8 kB, 4-way, 64 B/block  (128 total lines)
 *   Memory    : SimpleMemory (30 ns)
 */

#include <gem5/m5ops.h>
#include <stdint.h>

/*
 * 32 × 64 B = 2 kB.
 * > L1 capacity (16 × 64 = 1 kB) → guarantees full L1 replacement.
 * < L2 capacity (128 × 64 = 8 kB) → stack line survives in L2.
 */
#define FLUSH_LINES  32
#define LINE_BYTES   64

static volatile char flush_buf[FLUSH_LINES * LINE_BYTES];

/*
 * Load one byte from each of FLUSH_LINES cache-line-sized slots.
 * noinline keeps this a real function call so the loop compiles to
 * register-only arithmetic (i and acc never spill to the stack with -O2).
 * Returns the accumulator so the compiler cannot discard the loads.
 */
static __attribute__((noinline)) int flush_l1(void)
{
    int acc = 0;
    int i;
    for (i = 0; i < FLUSH_LINES; i++) {
        acc += flush_buf[i * LINE_BYTES];
    }
    return acc;
}

int main(void)
{
    m5_work_begin(0, 0);

    /* Step 1: spill store — x's cache line enters L1 */
    volatile int64_t x;
    x = 0xA5A5A5A5A5A5A5A5LL;

    /*
     * Step 2: evict x's line from L1.
     * After flush_l1() returns, x's dirty line has been written back to L2
     * and the 32 flush lines occupy L1.  x is still in L2.
     */
    int dummy = flush_l1();

    /*
     * Step 3: spill reload.
     * SpillDetector: store_map hit → SPILL_LOAD flag set.
     * L1 miss  → dcache.spillLoadMisses++
     * L2 hit   → l2.spillLoadHits++
     */
    int64_t val = x;

    m5_work_end(0, 0);

    return (int)(val & 1) | (dummy & 1);
}
