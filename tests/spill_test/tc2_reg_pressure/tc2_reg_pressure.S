# ==============================================================================
# TC2 — Register Pressure Spill (all-spill-then-all-reload)
# ==============================================================================
#
# SCENARIO:
#   Simulates what the register allocator does when the live set exceeds
#   the number of available physical registers.
#
#   Phase 1 (SPILL-OUT): 8 independently computed values are written to 8
#     distinct stack slots. All 8 stores happen before any reload — this is
#     the "spill-out" half of a register pressure event.
#
#   Phase 2 (SPILL-IN):  All 8 values are loaded back in sequence and
#     accumulated into a single result. Each load hits an address that was
#     stored in Phase 1 → 8 spills detected.
#
# WHY THIS DIFFERS FROM TC1:
#   - TC1: 6 stores immediately followed by 6 loads (separated by body work).
#   - TC2: ALL 8 stores complete first (store_map grows to 8 entries),
#          THEN all 8 loads happen. Tests the map holding multiple live entries
#          simultaneously, which is the hallmark of real register pressure.
#
# ROI LAYOUT:
#   [ROI BEGIN]
#     Phase 1 : compute 8 values, sd each to a unique slot  (8 stores, 0 loads)
#     Phase 2 : ld each slot, accumulate into t0            (0 stores, 8 loads)
#   [ROI END]
#
# EXPECTED RESULT:
#   roi_spills  : 8
#   roi_stores  : 8
#   roi_loads   : 8
#
# Stack layout (sp = base, each slot 8 bytes):
#   sp+ 0  ← t0 value (11)
#   sp+ 8  ← t1 value (22)
#   sp+16  ← t2 value (33)
#   sp+24  ← t3 value (44)
#   sp+32  ← t4 value (55)
#   sp+40  ← t5 value (66)
#   sp+48  ← t6 value (77)
#   sp+56  ← a2 value (88)
#
# Build:
#   $AS -o tc2_reg_pressure.o tc2_reg_pressure.S
#   $LD -o tc2_reg_pressure.riscv tc2_reg_pressure.o
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # Allocate 128-byte stack frame (8 slots × 16 bytes, with headroom)
    addi    sp, sp, -128

    # ----------------------------------------------------------
    # ROI BEGIN
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin

    # ----------------------------------------------------------
    # PHASE 1 — SPILL-OUT: compute 8 independent values and
    # spill them all to the stack before any reload occurs.
    # The store_map will hold 8 live entries simultaneously.
    # ----------------------------------------------------------
    li      t0, 11
    sd      t0, 0(sp)           # STORE #1  sp+0   = 11

    li      t1, 22
    sd      t1, 8(sp)           # STORE #2  sp+8   = 22

    li      t2, 33
    sd      t2, 16(sp)          # STORE #3  sp+16  = 33

    li      t3, 44
    sd      t3, 24(sp)          # STORE #4  sp+24  = 44

    li      t4, 55
    sd      t4, 32(sp)          # STORE #5  sp+32  = 55

    li      t5, 66
    sd      t5, 40(sp)          # STORE #6  sp+40  = 66

    li      t6, 77
    sd      t6, 48(sp)          # STORE #7  sp+48  = 77

    li      a2, 88
    sd      a2, 56(sp)          # STORE #8  sp+56  = 88

    # ----------------------------------------------------------
    # PHASE 2 — SPILL-IN: reload all 8 values and accumulate.
    # Each ld matches a prior sd at the same address → SPILL.
    # ----------------------------------------------------------
    ld      t0, 0(sp)           # LOAD #1  → SPILL  (t0 = 11)
    ld      t1, 8(sp)           # LOAD #2  → SPILL  (t1 = 22)
    add     t0, t0, t1          # t0 = 33

    ld      t2, 16(sp)          # LOAD #3  → SPILL  (t2 = 33)
    add     t0, t0, t2          # t0 = 66

    ld      t3, 24(sp)          # LOAD #4  → SPILL  (t3 = 44)
    add     t0, t0, t3          # t0 = 110

    ld      t4, 32(sp)          # LOAD #5  → SPILL  (t4 = 55)
    add     t0, t0, t4          # t0 = 165

    ld      t5, 40(sp)          # LOAD #6  → SPILL  (t5 = 66)
    add     t0, t0, t5          # t0 = 231

    ld      t6, 48(sp)          # LOAD #7  → SPILL  (t6 = 77)
    add     t0, t0, t6          # t0 = 308

    ld      a2, 56(sp)          # LOAD #8  → SPILL  (a2 = 88)
    add     t0, t0, a2          # t0 = 396  (11+22+33+44+55+66+77+88)

    # ----------------------------------------------------------
    # ROI END
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end  → writes summary

    # Restore stack and exit
    addi    sp, sp, 128
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start

# ==============================================================================
# EXPECTED OUTPUT (riscv_spill_stats.txt):
# ==============================================================================
#
# # ROI SUMMARY  ISA=RISC-V  workid=0
# # roi_stores         : 8
# # roi_loads          : 8
# # roi_spills         : 8
# # spill_rate         : 8 / roi_instructions * 100%
#
# ==============================================================================
