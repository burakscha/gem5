/* spill_tests.S — pure ASM spill detector plumbing test
 *
 * Single file: no main.c needed.
 * m5_work_begin / m5_work_end come from libm5.a — called like any C function.
 *
 * Layout:
 *   test_spill_l1_hit   — leaf, exact 1 sd + 1 ld, no ra save
 *   test_no_spill       — leaf, size mismatch sw+ld, negative test
 *   main                — ROI markers + calls to the test functions above
 */

    .section .text

/* ======================================================================
 * test_spill_l1_hit  — minimum L1 HIT test
 *
 * Leaf function (no calls → no ra save → zero prologue stack traffic).
 *
 * Stack layout (8 bytes):
 *   sp+0 : spill_slot (8 bytes)
 *
 * Sequence:
 *   li   t0, 0xABCD    — load sentinel into t0  (register op, no mem)
 *   sd   t0, 0(sp)     — STORE  → store_map[sp+0] = {size=8, tick, ...}
 *   ld   t0, 0(sp)     — LOAD   → isLikelySpill=true → SPILL_LOAD tag
 *                                  Cache L1D: HIT (line just written by sd)
 *                                  → spillLoadHits++
 *
 * Expected:
 *   system.cpu.dcache.spillLoadHits   += 1
 *   system.cpu.dcache.spillLoadMisses += 0
 * ====================================================================== */
    .globl  test_spill_l1_hit
    .type   test_spill_l1_hit, @function
    .align  2
.option norvc
test_spill_l1_hit:
    addi  sp, sp, -8
    li    t0, 0xABCD        /* sentinel value — makes disasm readable */
    sd    t0, 0(sp)         /* STORE  → store_map[sp+0]               */
    ld    t0, 0(sp)         /* LOAD   → L1 HIT → spillLoadHits++      */
    addi  sp, sp, 8
    ret
.option rvc
    .size   test_spill_l1_hit, . - test_spill_l1_hit


/* ======================================================================
 * test_no_spill  — negative test (size mismatch)
 *
 * sw stores 4 bytes; ld loads 8 bytes from same address.
 * isLikelySpill() size check: 4 != 8 → false → no SPILL_LOAD tag.
 *
 * Expected: no change to any spillLoad* counter.
 * ====================================================================== */
    .globl  test_no_spill
    .type   test_no_spill, @function
    .align  2
.option norvc
test_no_spill:
    addi  sp, sp, -8
    li    t0, 0x1234
    sw    t0, 0(sp)         /* STORE 4 bytes → store_map[sp+0] size=4 */
    ld    t0, 0(sp)         /* LOAD  8 bytes → size mismatch → NOT spill */
    addi  sp, sp, 8
    ret
.option rvc
    .size   test_no_spill, . - test_no_spill


/* ======================================================================
 * main — ROI control + test dispatch
 *
 * main calls external functions (m5_work_begin, m5_work_end,
 * test_spill_l1_hit) so it must save ra.
 *
 * Stack layout (16 bytes):
 *   sp+8 : saved ra
 *   sp+0 : (padding / alignment)
 *
 * Timeline relative to ROI:
 *   sd ra, 8(sp)   — BEFORE m5_work_begin → outside ROI
 *                    enterROI() calls store_map.clear() → this entry wiped
 *   ... ROI ...
 *   ld ra, 8(sp)   — AFTER  m5_work_end   → inside_roi=false → not counted
 *
 * Uncomment test_no_spill call for Phase 2 negative verification.
 * ====================================================================== */
    .globl  main
    .type   main, @function
    .align  2
main:
    addi  sp, sp, -16
    sd    ra, 8(sp)         /* save ra — OUTSIDE ROI, cleared by enterROI */

    li    a1, 0             /* m5_work_begin(0, 0) */
    li    a0, 0
    call  m5_work_begin     /* ROI START → store_map.clear()             */

    call  test_spill_l1_hit /* Phase 1: 1 spill → L1 hit                */
  /*call  test_no_spill*/   /* Phase 2: uncomment for negative test      */

    li    a1, 0             /* m5_work_end(0, 0) */
    li    a0, 0
    call  m5_work_end       /* ROI END → inside_roi = false              */

    li    a0, 0             /* return 0 */
    ld    ra, 8(sp)         /* restore ra — inside_roi=false, not counted */
    addi  sp, sp, 16
    ret
    .size   main, . - main
