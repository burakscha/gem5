# ==============================================================================
# Controlled Register Spill Test for gem5
# ==============================================================================
#
# RISC-V Assembly - Minimal test with KNOWN spill count
#
# EXPECTED RESULTS:
# -----------------
# Total Stores: 4
# Total Loads:  4
# Total Spills: 4 (each load reads from recently stored address)
#
# SPILL PATTERN:
# Store to [sp-8]  -> Load from [sp-8]   = SPILL #1
# Store to [sp-16] -> Load from [sp-16]  = SPILL #2
# Store to [sp-24] -> Load from [sp-24]  = SPILL #3
# Store to [sp-32] -> Load from [sp-32]  = SPILL #4
#
# Compile: riscv64-linux-gnu-as -o spill_exact.o spill_exact.S
# Link:    riscv64-linux-gnu-ld -o spill_exact.riscv spill_exact.o
#
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # ==========================================
    # Setup: Allocate stack space (64 bytes)
    # ==========================================
    addi    sp, sp, -64         # Allocate stack

    # ==========================================
    # SPILL #1: Store t0 to stack, then load back
    # ==========================================
    li      t0, 100             # t0 = 100
    sd      t0, 8(sp)           # STORE #1: [sp+8] = 100
    ld      t1, 8(sp)           # LOAD #1:  t1 = [sp+8] -> SPILL!

    # ==========================================
    # SPILL #2: Store t2 to stack, then load back
    # ==========================================
    li      t2, 200             # t2 = 200
    sd      t2, 16(sp)          # STORE #2: [sp+16] = 200
    ld      t3, 16(sp)          # LOAD #2:  t3 = [sp+16] -> SPILL!

    # ==========================================
    # SPILL #3: Store t4 to stack, then load back
    # ==========================================
    li      t4, 300             # t4 = 300
    sd      t4, 24(sp)          # STORE #3: [sp+24] = 300
    ld      t5, 24(sp)          # LOAD #3:  t5 = [sp+24] -> SPILL!

    # ==========================================
    # SPILL #4: Store t6 to stack, then load back
    # ==========================================
    li      t6, 400             # t6 = 400
    sd      t6, 32(sp)          # STORE #4: [sp+32] = 400
    ld      a0, 32(sp)          # LOAD #4:  a0 = [sp+32] -> SPILL!

    # ==========================================
    # Cleanup: Restore stack
    # ==========================================
    addi    sp, sp, 64          # Deallocate stack

    # ==========================================
    # Exit syscall
    # ==========================================
    li      a7, 93              # syscall number for exit (93)
    li      a0, 0               # exit code 0
    ecall                       # make syscall

    .size _start, .-_start
