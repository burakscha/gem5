/*
 * store/l1_hit/test.c — Spill Store L1-Hit Micro-Test
 *
 * What this tests:
 *   A stack store inside the ROI that HITS the L1 dcache.
 *
 * How:
 *   The volatile store `x = 0` (before ROI, not counted as spill) touches
 *   x's cache line and brings it into L1 in Modified state.
 *   m5_work_begin is a leaf (magic insn + ret) — no stack access —
 *   so the line is still warm when the ROI opens.
 *   The second store `x = 0xA5A5…` inside the ROI hits L1.
 *   → dcache.spillStoreHits++
 *
 * Why the explicit pre-warm instead of relying on the prologue:
 *   With -O2 the compiler allocates x at sp+8 but only saves ra at sp+24.
 *   If sp%64 == 48, sp+8 and sp+24 fall on different 64 B cache lines,
 *   so the prologue's sd-ra write would NOT warm x's line.
 *   An explicit volatile write to x before ROI guarantees the line is hot
 *   regardless of stack alignment.
 *
 * Expected:
 *   system.cpu.dcache.spillStoreHits   >= 1
 *   system.cpu.dcache.spillStoreMisses  = 0
 *   system.l2.spillStoreHits            = 0   (L2 never sees the store)
 *   system.l2.spillStoreMisses          = 0
 */

#include <gem5/m5ops.h>
#include <stdint.h>

int main(void)
{
    volatile int64_t x;

    /* Pre-warm x's cache line BEFORE ROI (inside_roi = false → not counted
     * as spill).  After this store the line is in L1 Modified. */
    x = 0;

    /* ROI opens.  m5_work_begin is a leaf: magic insn + ret, no stack
     * access → x's line stays warm in L1. */
    m5_work_begin(0, 0);

    /* Stack store inside ROI → L1 hit → dcache.spillStoreHits++ */
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL;

    m5_work_end(0, 0);

    return (int)(x & 1);
}
