/* spill_miss_test.S — L1 MISS / L2 HIT spill plumbing test
 *
 * Verifies:
 *   system.cpu.dcache.spillLoadMisses = 1
 *   system.l2.spillLoadHits           = 1
 *
 * Strategy:
 *   1. warmup_evict_buf (OUTSIDE ROI): stream through 512KB evict_buf
 *      → brings entire buffer into L2 so eviction inside ROI pays
 *        only L2 latency (~20 cycles each), not DRAM (~200+).
 *        Without this: 65536 × 200 cycles ≈ 13M ticks > MAX_SPILL_WINDOW.
 *        With this:    65536 × 20  cycles ≈  1.3M ticks — safe.
 *
 *   2. test_spill_l1_miss (INSIDE ROI):
 *      a. sd t0, 0(sp)     → STORE  → store_map[sp+0]  → line brought to L1D
 *      b. eviction loop    → stream 512KB evict_buf (L2 hits) → L1D filled
 *                            16× over → sp+0 line evicted from L1D
 *                            (dirty writeback → sp+0 line now in L2)
 *      c. ld t0, 0(sp)     → LOAD   → L1D MISS → L2 HIT
 *                            SpillDetector: isLikelySpill=true → SPILL_LOAD
 *                            Cache: incMissCount → spillLoadMisses++
 *                            L2:    incHitCount  → spillLoadHits++
 *
 * Eviction geometry (default gem5 se.py):
 *   L1D: 32KB, 8-way, 512 sets, 64B blocks
 *   L2:   1MB, 8-way
 *   EVICT_BYTES = 512KB = 16× L1D size
 *   After streaming: every L1D set has received 16 new lines → sp+0 evicted.
 *
 * Both warmup and eviction loops use the SAME code structure but DIFFERENT
 * local labels. Inline eviction in test_spill_l1_miss keeps it a LEAF
 * function (no call → no ra save → zero prologue stack traffic).
 *
 * Expected:
 *   system.cpu.dcache.spillLoadMisses = 1
 *   system.cpu.dcache.spillLoadHits   = 0
 *   system.l2.spillLoadHits           = 1
 *   system.l2.spillLoadMisses         = 0
 */

    .equ  EVICT_BYTES,  524288          /* 512 * 1024                      */
    .equ  EVICT_NELEMS, 65536           /* EVICT_BYTES / sizeof(uint64_t)  */

/* 512 KB BSS buffer — NOT on the stack, so SpillDetector's stack region
 * check will reject any accidental store/load pairs within this buffer.  */
    .section .bss
    .align  6                           /* cache-line aligned              */
evict_buf:
    .skip   EVICT_BYTES

    .section .text

/* ======================================================================
 * warmup_evict_buf — called ONCE from main, BEFORE m5_work_begin
 *
 * Streams through evict_buf to warm it into L2.
 * Leaf function (no calls). Uses a2/a3/a4/a5 (caller-saved, no save needed).
 * No stack traffic: loop variables stay in registers.
 * ====================================================================== */
    .globl  warmup_evict_buf
    .type   warmup_evict_buf, @function
    .align  2
warmup_evict_buf:
    la    a2, evict_buf             /* ptr = &evict_buf[0]                */
    li    a3, EVICT_BYTES
    add   a3, a2, a3                /* end = &evict_buf[0] + EVICT_BYTES  */
    li    a4, 0                     /* accumulator (keeps loop alive)     */
.Lwarmup_loop:
    ld    a5, 0(a2)                 /* load *ptr (DRAM first time, warm)  */
    add   a4, a4, a5                /* accumulate into register           */
    addi  a2, a2, 8                 /* ptr += 8                           */
    bltu  a2, a3, .Lwarmup_loop
    /* a4 holds the sum; compiler can't eliminate the loop.
     * We intentionally discard it — no stack store needed.               */
    ret
    .size warmup_evict_buf, . - warmup_evict_buf


/* ======================================================================
 * test_spill_l1_miss — minimum L1 MISS / L2 HIT spill test
 *
 * LEAF function: eviction loop is inlined → no call → no ra save.
 * Stack layout (8 bytes):
 *   sp+0 : spill_slot (8 bytes)
 *
 * Register usage (all caller-saved — no save/restore needed):
 *   t0   : spill value (0xABCD sentinel)
 *   a2   : evict_buf pointer
 *   a3   : evict_buf end pointer
 *   a4   : loop accumulator
 *   a5   : temp load value
 *
 * Sequence:
 *   addi sp, sp, -8
 *   li   t0, 0xABCD
 *   sd   t0, 0(sp)       STORE → store_map[sp+0], line in L1D
 *   <eviction loop>      512KB L2-warm reads → L1D filled 16× → sp+0 evicted
 *                        (dirty writeback: sp+0 line written to L2)
 *   ld   t0, 0(sp)       LOAD  → L1D MISS → L2 HIT
 *                        SpillDetector: isLikelySpill=true
 *                        → req->setFlags(SPILL_LOAD)
 *                        → dcache.spillLoadMisses++
 *                        → l2.spillLoadHits++
 *   addi sp, sp, 8
 *   ret
 * ====================================================================== */
    .globl  test_spill_l1_miss
    .type   test_spill_l1_miss, @function
    .align  2
.option norvc
test_spill_l1_miss:
    addi  sp, sp, -8

    li    t0, 0xABCD                /* sentinel — readable in disasm      */
    sd    t0, 0(sp)                 /* STORE → store_map[sp+0]            */

    /* ---- Inline eviction loop (no call → stays leaf) ------------------
     * Reads evict_buf sequentially (L2 hits after warmup).
     * Accumulates into a4 register only — no stack stores.
     * ------------------------------------------------------------------ */
    la    a2, evict_buf
    li    a3, EVICT_BYTES
    add   a3, a2, a3                /* a3 = end of evict_buf              */
    li    a4, 0                     /* accumulator                        */
.Levict_loop:
    ld    a5, 0(a2)                 /* load evict_buf[i] — L2 hit         */
    add   a4, a4, a5                /* accumulate                         */
    addi  a2, a2, 8                 /* advance pointer                    */
    bltu  a2, a3, .Levict_loop
    /* a4 discarded — loop cannot be eliminated */

    ld    t0, 0(sp)                 /* LOAD → L1D MISS → L2 HIT           */
    addi  sp, sp, 8
    ret
.option rvc
    .size test_spill_l1_miss, . - test_spill_l1_miss


/* ======================================================================
 * main — warmup outside ROI, then ROI with miss test
 *
 * Timeline:
 *   sd ra, 8(sp)          OUTSIDE ROI → enterROI clears store_map
 *   call warmup_evict_buf OUTSIDE ROI → warms L2
 *   m5_work_begin         ROI START
 *   call test_spill_l1_miss
 *   m5_work_end           ROI END
 *   ld ra, 8(sp)          inside_roi=false → not counted
 * ====================================================================== */
    .globl  main
    .type   main, @function
    .align  2
main:
    addi  sp, sp, -16
    sd    ra, 8(sp)                 /* save ra — OUTSIDE ROI              */

    call  warmup_evict_buf          /* warm L2 — OUTSIDE ROI              */

    li    a1, 0                     /* m5_work_begin(0, 0)                */
    li    a0, 0
    call  m5_work_begin             /* ROI START → store_map.clear()      */

    call  test_spill_l1_miss        /* 1 spill → L1D MISS → L2 HIT       */

    li    a1, 0                     /* m5_work_end(0, 0)                  */
    li    a0, 0
    call  m5_work_end               /* ROI END → inside_roi = false       */

    li    a0, 0                     /* return 0                           */
    ld    ra, 8(sp)                 /* restore ra — not counted           */
    addi  sp, sp, 16
    ret
    .size main, . - main
