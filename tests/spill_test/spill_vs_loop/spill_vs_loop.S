# ==============================================================================
# Spill vs Loop Test - RISC-V Assembly
# ==============================================================================
#
# PURPOSE: Test that spill detection correctly:
#   1. Detects real spills (store followed by load to same address)
#   2. Does NOT count normal loop stores as spills (no reload)
#
# EXPECTED RESULTS:
#   - Total Spills: 7 (2 pre-ROI + 4 ROI + 1 post-ROI)
#   - ROI Spills: 4 (NOT 6, loop stores should NOT be counted!)
#   - Loop stores: 5 (should NOT be counted as spills)
#
# m5ops encoding for RISC-V:
#   M5OP_WORK_BEGIN = 0x5a -> 0xb400007b
#   M5OP_WORK_END   = 0x5b -> 0xb600007b
#
# Compile: riscv64-linux-gnu-as -o spill_vs_loop.o spill_vs_loop.S
# Link:    riscv64-linux-gnu-ld -o spill_vs_loop.riscv spill_vs_loop.o
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # ==========================================
    # Stack Setup: Allocate 128 bytes
    # ==========================================
    addi    sp, sp, -128

    # ==========================================
    # SECTION 1: PRE-ROI Spills (2 spills)
    # These should be counted in GLOBAL but NOT in ROI
    # ==========================================

    # Spill #1: t0 -> stack -> t1
    li      t0, 111             # t0 = 111
    sd      t0, 8(sp)           # STORE #1
    ld      t1, 8(sp)           # LOAD #1 -> SPILL!

    # Spill #2: t2 -> stack -> t3
    li      t2, 222             # t2 = 222
    sd      t2, 16(sp)          # STORE #2
    ld      t3, 16(sp)          # LOAD #2 -> SPILL!

    # ==========================================
    # m5_work_begin(0, 0) - ROI START
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    # ==========================================
    # SECTION 2: ROI - Real Spills (2 spills)
    # ==========================================

    # Spill #3: t4 -> stack -> t5
    li      t4, 333             # t4 = 333
    sd      t4, 24(sp)          # STORE #3
    ld      t5, 24(sp)          # LOAD #3 -> SPILL!

    # Spill #4: t6 -> stack -> a2
    li      t6, 444             # t6 = 444
    sd      t6, 32(sp)          # STORE #4
    ld      a2, 32(sp)          # LOAD #4 -> SPILL!

    # ==========================================
    # SECTION 3: ROI - Loop with NO SPILLS
    # ==========================================
    # This loop stores to array but NEVER reloads
    # Therefore: 5 stores, 0 spills

    addi    a0, sp, 64          # a0 = array base (sp+64)
    li      a1, 0               # a1 = i = 0
    li      a3, 5               # a3 = limit = 5

loop_start:
    bge     a1, a3, loop_end    # if i >= 5, exit

    # Calculate array[i] address
    slli    a4, a1, 3           # a4 = i * 8 (offset)
    add     a5, a0, a4          # a5 = &array[i]

    # Store value (NO RELOAD!)
    li      a6, 10
    mul     a7, a1, a6          # a7 = i * 10
    sd      a7, 0(a5)           # array[i] = i*10 (STORE - no reload!)

    # Loop increment
    addi    a1, a1, 1           # i++
    j       loop_start

loop_end:
    # Loop done - 5 stores happened but NO reloads
    # These should NOT be counted as spills!

    # ==========================================
    # SECTION 4: ROI - More Real Spills (2 spills)
    # ==========================================

    # Spill #5: t0 -> stack -> t1
    li      t0, 555             # t0 = 555
    sd      t0, 40(sp)          # STORE #5
    ld      t1, 40(sp)          # LOAD #5 -> SPILL!

    # Spill #6: t2 -> stack -> t3
    li      t2, 666             # t2 = 666
    sd      t2, 48(sp)          # STORE #6
    ld      t3, 48(sp)          # LOAD #6 -> SPILL!

    # ==========================================
    # m5_work_end(0, 0) - ROI END
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb600007b          # m5_work_end

    # ==========================================
    # SECTION 5: POST-ROI Spill (1 spill)
    # Should be counted in GLOBAL but NOT in ROI
    # ==========================================

    # Spill #7: t4 -> stack -> t5
    li      t4, 777             # t4 = 777
    sd      t4, 56(sp)          # STORE #7
    ld      t5, 56(sp)          # LOAD #7 -> SPILL! (but outside ROI)

    # ==========================================
    # Cleanup and Exit
    # ==========================================
    addi    sp, sp, 128         # Restore stack
    li      a7, 93              # syscall: exit
    li      a0, 0               # exit code 0
    ecall

    .size _start, .-_start

# ==============================================================================
# EXPECTED RESULTS SUMMARY:
# ==============================================================================
#
# | Section      | Stores | Loads | Spills | ROI Counted |
# |--------------|--------|-------|--------|-------------|
# | Pre-ROI      | 2      | 2     | 2      | NO          |
# | ROI Spills 1 | 2      | 2     | 2      | YES         |
# | ROI Loop     | 5      | 0     | 0      | N/A         |
# | ROI Spills 2 | 2      | 2     | 2      | YES         |
# | Post-ROI     | 1      | 1     | 1      | NO          |
# |--------------|--------|-------|--------|-------------|
# | TOTAL        | 12     | 7     | 7      | -           |
# | ROI ONLY     | 9      | 4     | 4      | -           |
#
# CRITICAL: Loop's 5 stores should NOT appear as spills!
# ==============================================================================
