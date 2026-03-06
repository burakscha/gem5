# ==============================================================================
# TC3 — Loop Body Spill (5 iterations × 3 spills = 15 ROI spills)
# ==============================================================================
#
# SCENARIO:
#   Simulates a loop whose body requires more live registers than are available,
#   so the compiler spills 3 values per iteration to the stack.
#
#   Each iteration independently spills:
#     Slot A (sp+16): loop counter offset          → 1 spill per iter
#     Slot B (sp+24): loop counter × multiplier    → 1 spill per iter
#     Slot C (sp+32): accumulated partial sum      → 1 spill per iter
#
#   The LOAD in each iteration erases the store_map entry for that slot, so the
#   next iteration's STORE re-enters cleanly → every iteration produces exactly
#   3 fresh spills.
#
# ROI LAYOUT:
#   [ROI BEGIN]
#     5 loop iterations, each:
#       sd t0, 16(sp)  →  ld t1, 16(sp)   SPILL A
#       sd t2, 24(sp)  →  ld t3, 24(sp)   SPILL B
#       sd t4, 32(sp)  →  ld t5, 32(sp)   SPILL C
#   [ROI END]
#
# SPILL BUDGET:
#   5 iterations × 3 spills/iter = 15 ROI spills
#
# EXPECTED RESULT:
#   roi_spills  : 15
#   roi_stores  : 15   (3 stores × 5 iterations)
#   roi_loads   : 15   (3 loads  × 5 iterations)
#
# NOTE — no pre-ROI or post-ROI spills in this test:
#   The store_map is cleared by enterROI(), so there are no stale entries
#   before the loop starts. After the ROI, we do only arithmetic / ecall.
#
# Build:
#   $AS -o tc3_loop_spill.o tc3_loop_spill.S
#   $LD -o tc3_loop_spill.riscv tc3_loop_spill.o
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # Allocate 64-byte stack frame
    addi    sp, sp, -64

    # ----------------------------------------------------------
    # ROI BEGIN
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin

    # ----------------------------------------------------------
    # Loop setup
    # ----------------------------------------------------------
    li      s0, 0               # i = 0   (loop counter)
    li      s1, 5               # limit = 5
    li      s2, 0               # accumulator = 0

loop_body:
    bge     s0, s1, loop_done   # if i >= 5 → exit

    # -- SPILL A: loop offset value -------------------------
    addi    t0, s0, 10          # t0 = i + 10
    sd      t0, 16(sp)          # STORE A  → sp+16
    ld      t1, 16(sp)          # LOAD  A  → SPILL (sp+16 was just stored)

    # -- SPILL B: scaled counter ----------------------------
    slli    t2, s0, 2           # t2 = i << 2  (i × 4)
    sd      t2, 24(sp)          # STORE B  → sp+24
    ld      t3, 24(sp)          # LOAD  B  → SPILL (sp+24 was just stored)

    # -- SPILL C: partial accumulation ----------------------
    add     s2, s2, t1          # accumulator += reload of A
    add     s2, s2, t3          # accumulator += reload of B
    sd      s2, 32(sp)          # STORE C  → sp+32 (spill accumulator)
    ld      t5, 32(sp)          # LOAD  C  → SPILL (sp+32 was just stored)

    addi    s0, s0, 1           # i++
    j       loop_body

loop_done:
    # ----------------------------------------------------------
    # ROI END
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end  → writes summary

    # Restore stack and exit
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start

# ==============================================================================
# EXPECTED OUTPUT (riscv_spill_stats.txt):
# ==============================================================================
#
# # ROI SUMMARY  ISA=RISC-V  workid=0
# # roi_stores         : 15
# # roi_loads          : 15
# # roi_spills         : 15
# # spill_rate         : 15 / roi_instructions * 100%
#
# Per-iteration spill breakdown:
#   Iter 0: A=spill(sp+16), B=spill(sp+24), C=spill(sp+32)
#   Iter 1: A=spill(sp+16), B=spill(sp+24), C=spill(sp+32)
#   Iter 2: A=spill(sp+16), B=spill(sp+24), C=spill(sp+32)
#   Iter 3: A=spill(sp+16), B=spill(sp+24), C=spill(sp+32)
#   Iter 4: A=spill(sp+16), B=spill(sp+24), C=spill(sp+32)
#   Total:  15 spills
#
# ==============================================================================
