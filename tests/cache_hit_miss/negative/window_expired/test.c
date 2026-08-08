/*
 * negative/window_expired/test.c
 *
 * Guard tested: cleanupOldStores() removes entries older than MAX_SPILL_WINDOW
 *               (50,000,000 ticks = 50 µs)
 *
 * How:
 *   1. Stack store inside ROI at tick T → store_map[&x] = {tick=T}
 *   2. 512 cold BSS reads inside ROI, each one calls cleanupOldStores(tick).
 *      512 cold DRAM misses × ~185K ticks ≈ 95M ticks >> 50M ticks.
 *      Somewhere around access 270 (50M / 185K), cleanupOldStores removes
 *      x's entry from store_map.
 *   3. Load x inside ROI → store_map.find(&x) == end() → no entry → no SPILL_LOAD.
 *
 * Why BSS reads trigger the cleanup:
 *   onLoadInstruction() is called for ALL loads (not just stack loads).
 *   The very first line is: cleanupOldStores(tick).
 *   So each BSS read advances current_tick and may evict stale entries.
 *
 * Why BSS reads don't produce false positives:
 *   store_map has no entry for BSS addresses (we never stored to delay_buf).
 *   Even if there were an entry, isLikelySpill() would fail isStackAddress().
 *
 * Expected:
 *   dcache.spillLoadHits   = 0
 *   dcache.spillLoadMisses = 0
 */

#include <gem5/m5ops.h>
#include <stdint.h>

/* 1024 × 64 B = 64 kB.
 * In gem5 SE mode, BSS is zero-initialized by the ELF loader before simulation
 * starts, so delay_buf is completely cold (never touched in simulated code).
 * Average L2 miss latency (SimpleMemory default) ≈ 63,000 ticks.
 * 1024 cold DRAM misses × 63,000 ticks ≈ 64.5M ticks >> MAX_SPILL_WINDOW (50M).
 * Entry expires at iteration ~794 (50,000,000 / 63,000). */
#define DELAY_LINES  1024
#define LINE_BYTES   64

static volatile char delay_buf[DELAY_LINES * LINE_BYTES];

int main(void)
{
    m5_work_begin(0, 0);

    /* Step 1: stack store inside ROI → store_map entry at tick T */
    volatile int64_t x;
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL;

    /* Step 2: delay loop — 512 cold BSS reads.
     * Each read calls cleanupOldStores(current_tick).
     * After ~270 iterations, 50M ticks have elapsed and x's entry is removed. */
    int acc = 0;
    int i;
    for (i = 0; i < DELAY_LINES; i++)
        acc += delay_buf[i * LINE_BYTES];

    /* Step 3: load x — store_map entry is gone → no SPILL_LOAD */
    int64_t v = x;

    m5_work_end(0, 0);

    return (int)(v & 1) | (acc & 1);
}
