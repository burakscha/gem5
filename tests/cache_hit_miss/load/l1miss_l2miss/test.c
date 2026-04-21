/*
 * l1miss_l2miss/test.c
 *
 * PURPOSE
 * -------
 * Verify that a spill reload which misses in both L1 and L2 increments
 * the miss counter at each level:
 *
 *   system.cpu.dcache.spillLoadMisses  (L1 missed)
 *   system.l2.spillLoadMisses          (L2 also missed → went to DRAM)
 *
 * SCENARIO
 * --------
 *   1. ROI starts.
 *   2. Spill store: write `x` to a stack location.  Dirty line in L1.
 *   3. Full L1+L2 flush: load FLUSH_LINES (160) unique 64-byte-aligned
 *      entries from flush_buf.
 *
 *      Why 160 lines evicts L2:
 *        L2 has 32 sets, 4-way LRU, 128 total lines.
 *        160 sequential lines → 160 / 32 = 5 lines per set.
 *        4-way set fills after 4 lines; the 5th triggers LRU eviction.
 *        `x`'s dirty line is written back to L2 when L1 evicts it
 *        (after the first ~16 flush accesses).  Then 4 more flush lines
 *        land in x's L2 set → x evicted from L2.
 *
 *   4. Spill reload: read `x`.  Neither L1 nor L2 has the line → DRAM.
 *   5. ROI ends.
 *
 * EXPECTED STATS
 * --------------
 *   system.cpu.dcache.spillLoadMisses  >= 1   (x missed in L1)
 *   system.l2.spillLoadMisses          >= 1   (x also missed in L2)
 *
 * Note: flush_l1_l2() also pushes `ra` inside the ROI; that spill reload
 * will likewise miss both L1 and L2 (it was flushed out too), adding to
 * the >= 1 counts without changing the test conclusion.
 *
 * TIMING SAFETY (MAX_SPILL_WINDOW = 10,000,000 ticks = 10 µs)
 *   160 cold DRAM accesses × ~35,000 ticks each ≈ 5,600,000 ticks < 10 µs.
 *
 * CACHE CONFIG (see run.sh)
 *   L1 dcache : 1 kB, 4-way, 64 B/block  (16 total lines)
 *   L2        : 8 kB, 4-way, 64 B/block  (128 total lines)
 *   Memory    : SimpleMemory (30 ns)
 */

#include <gem5/m5ops.h>
#include <stdint.h>

/*
 * 160 × 64 B = 10 kB.
 * 160 / 32 L2-sets = 5 lines per set → overflows every L2 set (4-way).
 * This guarantees eviction of ALL resident lines from both L1 and L2,
 * including the stack line written back from L1.
 */
#define FLUSH_LINES  160
#define LINE_BYTES   64

static volatile char flush_buf[FLUSH_LINES * LINE_BYTES];

static __attribute__((noinline)) int flush_l1_l2(void)
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

    /* Step 1: spill store */
    volatile int64_t x;
    x = 0xA5A5A5A5A5A5A5A5LL;

    /*
     * Step 2: flush both L1 and L2.
     * After this call, x's line is in neither L1 nor L2.
     */
    int dummy = flush_l1_l2();

    /*
     * Step 3: spill reload.
     * SPILL_LOAD flag set by SpillDetector.
     * L1 miss  → dcache.spillLoadMisses++
     * L2 miss  → l2.spillLoadMisses++
     * → fetches from DRAM.
     */
    int64_t val = x;

    m5_work_end(0, 0);

    return (int)(val & 1) | (dummy & 1);
}
