/*
 * store/l1miss_l2miss/test.c — Spill Store L1-Miss / L2-Miss Micro-Test
 *
 * What this tests:
 *   A stack store inside the ROI that misses in BOTH L1 and L2.
 *   The write-allocate RFO packet carries SPILL_STORE to L2, and L2
 *   also misses, forcing a DRAM access.
 *   → dcache.spillStoreMisses++  AND  l2.spillStoreMisses++
 *
 * How:
 *   1. volatile x = 0  (pre-ROI): warms x's cache line in L1.
 *   2. flush_l1_l2() reads 160 × 64 B from flush_buf (BSS).
 *        L1 = 1 kB, 4-way, 4 sets → 40 competing lines per set >> 4 ways
 *        → x's line evicted from L1.
 *        L2 = 8 kB, 4-way, 32 sets → 5 competing lines per set > 4 ways
 *        → x's line evicted from L2.
 *   3. m5_work_begin(0,0): leaf (magic insn + ret), no stack access.
 *   4. x = 0xA5A5…: stack store inside ROI; L1 miss → RFO to L2 (with
 *      SPILL_STORE) → L2 miss → DRAM.
 *      dcache.spillStoreMisses++  l2.spillStoreMisses++
 *
 * Timing note:
 *   160 cold DRAM accesses × ~162 K ticks ≈ 26 M ticks < MAX_SPILL_WINDOW
 *   (50 M ticks).  For store detection there is no store_map expiration
 *   risk (SPILL_STORE is set purely from inside_roi + isStackAddress()),
 *   but the 50 µs window still covers the flush duration safely.
 *
 * Expected:
 *   system.cpu.dcache.spillStoreMisses >= 1
 *   system.cpu.dcache.spillStoreHits    = 0
 *   system.l2.spillStoreMisses         >= 1
 *   system.l2.spillStoreHits            = 0
 */

#include <gem5/m5ops.h>
#include <stdint.h>

#define FLUSH_LINES  160
#define LINE_BYTES   64

/* BSS: isStackAddress() returns false → flush loads never tagged as spills. */
static volatile char flush_buf[FLUSH_LINES * LINE_BYTES];

/* noinline + -O2 → compiler uses only caller-saved registers; no ra/s0
 * push/pop → zero stack accesses inside this function. */
static __attribute__((noinline)) int flush_l1_l2(void)
{
    int acc = 0;
    int i;
    for (i = 0; i < FLUSH_LINES; i++)
        acc += flush_buf[i * LINE_BYTES];
    return acc;
}

int main(void)
{
    volatile int64_t x;

    /* Step 1: pre-warm x's cache line (before ROI, not counted as spill). */
    x = 0;

    /* Step 2: evict x's line from both L1 and L2. */
    int dummy = flush_l1_l2();

    /* Step 3: open ROI — x's line is absent from both caches. */
    m5_work_begin(0, 0);

    /* Step 4: stack store inside ROI → L1 miss → RFO (with SPILL_STORE)
     * reaches L2 → L2 miss → DRAM.
     * dcache.spillStoreMisses++   l2.spillStoreMisses++ 
     * A5 A5 A5 A5 A5 A5 A5 A5   (8 byte)'lık memory dump ama distinctive pattern → easy to identify in DRAM trace.
     */
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL; 

    m5_work_end(0, 0);

    return (int)(x & 1) | (dummy & 1);
}
