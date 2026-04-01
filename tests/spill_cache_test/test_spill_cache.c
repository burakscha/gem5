/*
 * test_spill_cache.c
 *
 * Micro-benchmark: verify gem5 SpillDetector + cache spillLoadHits /
 * spillLoadMisses counters are counted correctly.
 *
 * Usage (via gem5 --options):
 *   --options="1"   Phase 1 — HIT only (safest first test)
 *   --options="2"   Phase 2 — HIT + MISS (default)
 *
 * Tests inside the ROI:
 *
 *  Test 1 — L1 HIT   (always runs)
 *    leaf function: no ra save → ONLY one sd/ld pair on stack
 *    Expected: dcache.spillLoadHits += 1
 *
 *  Test 2 — L1 MISS  (phase 2 only)
 *    eviction loop INLINED → no call instruction → no ra save → leaf
 *    Only one sd/ld pair: the spill_slot store then (post-eviction) load
 *    Expected: dcache.spillLoadMisses += 1
 *             l2cache.spillLoadHits  += 1
 *
 *  Test 3 — NEGATIVE (always runs, contributes 0)
 *    store outside ROI → enterROI clears store_map → load not counted
 *
 * Phase 1 exact expected:
 *   dcache.spillLoadHits   == 1
 *   dcache.spillLoadMisses == 0
 *
 * Phase 2 exact expected:
 *   dcache.spillLoadHits   == 1
 *   dcache.spillLoadMisses == 1
 *   l2cache.spillLoadHits  == 1
 *   l2cache.spillLoadMisses == 0
 *
 * Why exact counts are achievable:
 *   Both test_l1_hit and test_l1_miss are LEAF functions (no ra save).
 *   The eviction loop uses register accumulation only (asm volatile prevents
 *   dead-store elimination without touching the stack).
 *   No other stack store/load pairs exist inside the ROI.
 *
 * EVICT_BYTES / L2_SIZE relationship:
 *   EVICT_BYTES must be > L1D size (for eviction) AND < L2 size (for warmup).
 *   Default: EVICT_BYTES=256KB, L2_SIZE=1MB → both constraints satisfied.
 *   For 8-way 32KB L1D:  min eviction = (8+1)*512*64 = 288KB > 256KB... see note.
 *
 * NOTE on 256KB evict_buf vs 8-way L1D:
 *   256KB / 64B = 4096 lines; 4096 / 512 sets = 8 accesses/set.
 *   LRU: the stack line is the oldest in its set (stored before the loop).
 *   After 8 new evict_buf lines land in the same set, the stack line is
 *   at LRU position 7 → the 8th new line evicts it.  So 256KB is sufficient.
 *   (If eviction is unreliable in practice, increase via -DEVICT_BYTES.)
 */

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <gem5/m5ops.h>

/* -----------------------------------------------------------------------
 * Eviction buffer.
 *
 * Constraints:
 *   EVICT_BYTES > L1D_SIZE  (to evict the spill_slot cache line)
 *   EVICT_BYTES < L2_SIZE   (so warmup fits in L2, avoiding DRAM in ROI)
 *
 * Default: 256 KB.  run_test.sh sets L2_SIZE=1MB so this fits easily.
 * Override: make EVICT_BYTES=$((512*1024))
 * ----------------------------------------------------------------------- */
#ifndef EVICT_BYTES
#define EVICT_BYTES (256UL * 1024UL)
#endif

#define EVICT_NELEMS (EVICT_BYTES / sizeof(uint64_t))

/* Global volatile: reads are real loads, but no stack stores generated. */
static volatile uint64_t evict_buf[EVICT_NELEMS];

/* -----------------------------------------------------------------------
 * warmup_evict_buf()  — called ONCE before m5_work_begin
 *
 * Brings entire evict_buf into L2 so the inlined eviction loop inside
 * test_l1_miss pays only L2 latency (~20 cycles each), not DRAM (~200+).
 *
 * Timing check for MAX_SPILL_WINDOW = 10_000_000 ticks:
 *   256KB / 8B = 32768 accesses × 20 cycles = 655K ticks  ← safe
 * ----------------------------------------------------------------------- */
static void __attribute__((noinline)) warmup_evict_buf(void)
{
    uint64_t sink = 0;
    for (size_t i = 0; i < EVICT_NELEMS; i++)
        sink += evict_buf[i];
    __asm__ volatile("" : : "r"(sink) : );
}

/* -----------------------------------------------------------------------
 * TEST 1 — L1 HIT
 *
 * LEAF function (no call → no ra save → no ra store/load in store_map).
 * Only stack traffic: one sd + one ld at sp+8.
 *
 * Disassembly should be:
 *   addi  sp, sp, -16
 *   sd    a5, 8(sp)     ← STORE  (SpillDetector → store_map)
 *   ld    a5, 8(sp)     ← LOAD   (SpillDetector → isLikelySpill=true)
 *                                 (Cache: L1 HIT — same cache line)
 *   addi  sp, sp, 16
 *   jr    ra
 *
 * Expected: dcache.spillLoadHits += 1
 * ----------------------------------------------------------------------- */
static void __attribute__((noinline)) test_l1_hit(void)
{
    volatile uint64_t spill_slot;
    spill_slot = 0xAAAAAAAAAAAAAAAAULL;   /* stack STORE */
    uint64_t val = spill_slot;            /* stack LOAD  — L1 HIT */
    (void)val;
}

/* -----------------------------------------------------------------------
 * TEST 2 — L1 MISS / L2 HIT
 *
 * LEAF function: eviction loop is inlined → no call → no ra save.
 * Stack traffic: only one sd + one ld at sp+8 (spill_slot).
 * Eviction loop uses register accumulation only (no stack stores).
 *
 * Disassembly should be:
 *   addi  sp, sp, -16
 *   sd    a5, 8(sp)     ← STORE spill_slot
 *   ... (eviction loop: only loads from evict_buf, no stack sd/ld)
 *   ld    a5, 8(sp)     ← LOAD spill_slot — L1 MISS, L2 HIT
 *   addi  sp, sp, 16
 *   jr    ra
 *
 * Expected: dcache.spillLoadMisses += 1
 *           l2cache.spillLoadHits  += 1
 * ----------------------------------------------------------------------- */
static void __attribute__((noinline)) test_l1_miss(void)
{
    volatile uint64_t spill_slot;
    spill_slot = 0xBBBBBBBBBBBBBBBBULL;  /* stack STORE */

    /* Inline eviction — no call instruction → this remains a leaf function.
     * Uses register accumulation only: no stack stores → no store_map pollution. */
    {
        uint64_t sink = 0;
        for (size_t i = 0; i < EVICT_NELEMS; i++)
            sink += evict_buf[i];
        __asm__ volatile("" : : "r"(sink) : );
    }

    uint64_t val = spill_slot;            /* stack LOAD  — L1 MISS, L2 HIT */
    (void)val;
}

/* -----------------------------------------------------------------------
 * TEST 3 — NEGATIVE
 *
 * neg_var is a global volatile.  Its store runs in main() BEFORE
 * m5_work_begin().  enterROI() calls store_map.clear() so no matching
 * entry exists when the load executes inside the ROI.
 *
 * Expected: no increment to any spillLoad* counter.
 * ----------------------------------------------------------------------- */
static volatile uint64_t neg_var;

/* -----------------------------------------------------------------------
 * main
 *
 * argv[1] = "1" → phase 1 (HIT only)
 * argv[1] = "2" or absent → phase 2 (HIT + MISS)
 * ----------------------------------------------------------------------- */
int main(int argc, char *argv[])
{
    int phase = (argc > 1) ? atoi(argv[1]) : 2;

    /* Negative-test store — OUTSIDE ROI */
    neg_var = 0xCCCCCCCCCCCCCCCCULL;

    /* Phase 2 only: warm evict_buf into L2 before ROI. */
    if (phase >= 2)
        warmup_evict_buf();

    /* ============================================================ */
    m5_work_begin(0, 0);   /* ROI START — store_map cleared here  */
    /* ============================================================ */

    /* Test 3: negative — load from pre-ROI store → not a spill */
    {
        uint64_t v = neg_var;
        (void)v;
    }

    /* Test 1: L1 hit (always) */
    test_l1_hit();

    /* Test 2: L1 miss (phase 2 only) */
    if (phase >= 2)
        test_l1_miss();

    /* ============================================================ */
    m5_work_end(0, 0);     /* ROI END — writeROISummary() called  */
    /* ============================================================ */

    return 0;
}
