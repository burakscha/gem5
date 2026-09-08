/*
 * Long-reuse-distance spill regression (legacy directory name).
 *
 * Guard tested: elapsed simulation time must NOT discard a pending store.
 *
 * How:
 *   1. Stack store inside ROI at tick T → store_map[&x] = {tick=T}
 *   2. Cold BSS reads create a delay greater than the removed historical
 *      50M-tick window.
 *   3. Load x inside ROI. The store entry must still match and be tagged.
 *
 * Why BSS reads don't produce false positives:
 *   store_map has no entry for BSS addresses (we never stored to delay_buf).
 *   Even if there were an entry, isLikelySpill() would fail isStackAddress().
 *
 * Expected:
 *   dcache.spillLoadHits + dcache.spillLoadMisses = 1
 */

#include <gem5/m5ops.h>
#include <stdint.h>

/* 1024 × 64 B = 64 kB.
 * In gem5 SE mode, BSS is zero-initialized by the ELF loader before simulation
 * starts, so delay_buf is completely cold (never touched in simulated code).
 * Average L2 miss latency (SimpleMemory default) ≈ 63,000 ticks.
 * 1024 cold DRAM misses × 63,000 ticks ≈ 64.5M ticks >> MAX_SPILL_WINDOW (50M).
 * This deliberately exceeds the old, invalid 50M-tick cutoff. */
#define DELAY_LINES  1024
#define LINE_BYTES   64

static volatile char delay_buf[DELAY_LINES * LINE_BYTES];

int main(void)
{
    m5_work_begin(0, 0);

    /* Step 1: stack store inside ROI → store_map entry at tick T */
    volatile int64_t x;
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL;

    /* Step 2: delay loop — enough cold BSS reads to exceed the old cutoff. */
    int acc = 0;
    int i;
    for (i = 0; i < DELAY_LINES; i++)
        acc += delay_buf[i * LINE_BYTES];

    /* Step 3: load x — the entry survives and produces one SPILL_LOAD. */
    int64_t v = x;

    m5_work_end(0, 0);

    return (int)(v & 1) | (acc & 1);
}
