# ==============================================================================
# Controlled Register Spill Test with ROI (Region of Interest)
# ==============================================================================
#
# RISC-V Assembly - Minimal test with ROI markers and KNOWN spill count
#
# EXPECTED RESULTS (without ROI filtering in detector):
# -----------------------------------------------------
# Total Spills: 4 (same as spill_exact.S)
# Total Instructions: ~21 (17 original + 4 for m5ops)
#
# EXPECTED RESULTS (with ROI filtering in detector - FUTURE):
# -----------------------------------------------------------
# Only spills between m5_work_begin and m5_work_end should count
#
# m5ops encoding for RISC-V:
# M5OP_WORK_BEGIN = 0x5a (90 decimal) -> 0x0000007b | (0x5a << 25) = 0xb400007b
# M5OP_WORK_END   = 0x5b (91 decimal) -> 0x0000007b | (0x5b << 25) = 0xb600007b
#
# Compile: riscv64-linux-gnu-as -o roi_spill_exact.o roi_spill_exact.S
# Link:    riscv64-linux-gnu-ld -o roi_spill_exact.riscv roi_spill_exact.o
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # ==========================================
    # Setup: Allocate stack space (64 bytes)
    # ==========================================
    addi    sp, sp, -64         # 1. Allocate stack

    # ==========================================
    # m5_work_begin(0, 0) - Start ROI
    # ==========================================
    li      a0, 0               # 2. workid = 0
    li      a1, 0               # 3. threadid = 0
    .long   0xb400007b          # 4. m5_work_begin pseudo-instruction

    # ==========================================
    # SPILL #1: Store t0 to stack, then load back
    # ==========================================
    li      t0, 100             # 5. t0 = 100
    sd      t0, 8(sp)           # 6. STORE #1: [sp+8] = 100
    ld      t1, 8(sp)           # 7. LOAD #1:  t1 = [sp+8] -> SPILL!

    # ==========================================
    # SPILL #2: Store t2 to stack, then load back
    # ==========================================
    li      t2, 200             # 8. t2 = 200
    sd      t2, 16(sp)          # 9. STORE #2: [sp+16] = 200
    ld      t3, 16(sp)          # 10. LOAD #2: t3 = [sp+16] -> SPILL!

    # ==========================================
    # SPILL #3: Store t4 to stack, then load back
    # ==========================================
    li      t4, 300             # 11. t4 = 300
    sd      t4, 24(sp)          # 12. STORE #3: [sp+24] = 300
    ld      t5, 24(sp)          # 13. LOAD #3: t5 = [sp+24] -> SPILL!

    # ==========================================
    # SPILL #4: Store t6 to stack, then load back
    # ==========================================
    li      t6, 400             # 14. t6 = 400
    sd      t6, 32(sp)          # 15. STORE #4: [sp+32] = 400
    ld      a0, 32(sp)          # 16. LOAD #4: a0 = [sp+32] -> SPILL!

    # ==========================================
    # m5_work_end(0, 0) - End ROI
    # ==========================================
    li      a0, 0               # 17. workid = 0
    li      a1, 0               # 18. threadid = 0
    .long   0xb600007b          # 19. m5_work_end pseudo-instruction

    # ==========================================
    # Cleanup: Restore stack
    # ==========================================
    addi    sp, sp, 64          # 20. Deallocate stack

    # ==========================================
    # Exit syscall
    # ==========================================
    li      a7, 93              # 21. syscall number for exit (93)
    li      a0, 0               # 22. exit code 0
    ecall                       # 23. make syscall

    .size _start, .-_start
