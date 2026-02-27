# ==============================================================================
# ROI Loop Spill Test - RISC-V Assembly
# ==============================================================================
#
# PURPOSE: Tests that spills produced INSIDE a loop body, within the ROI,
#          are all correctly counted — once per iteration.
#
# DESIGN:
#   Pre-ROI  : 1 spill  (should NOT appear in roi_spills)
#   ROI loop : 8 iterations × 2 spills per iteration = 16 ROI spills
#   Post-ROI : 1 spill  (should NOT appear in roi_spills)
#
# HOW THE LOOP SPILLS WORK:
#   Each iteration stores to sp+16, then immediately loads from sp+16.
#   store_map[sp+16] is erased by the matching load (detected as spill).
#   Next iteration's store re-enters sp+16 cleanly -> another spill.
#   Same happens for sp+24 (Spill B). Hence 2 spills per iteration.
#
# EXPECTED RESULTS (riscv_spill_stats.txt):
#   roi_spills  : 16
#   spill_rate  : 16 / roi_instructions * 100%
#
# m5ops encoding for RISC-V:
#   M5OP_WORK_BEGIN = 0xb400007b
#   M5OP_WORK_END   = 0xb600007b
#
# Compile: riscv64-linux-gnu-as -o roi_loop_spills.o roi_loop_spills.S
# Link:    riscv64-linux-gnu-ld -o roi_loop_spills.riscv roi_loop_spills.o
# Run:     ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#              --cmd=tests/spill_test/roi_test_asm/roi_loop_spills.riscv \
#              --cpu-type=TimingSimpleCPU --caches
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # Allocate stack: 128 bytes
    addi    sp, sp, -128

    # ==========================================
    # PRE-ROI: 1 spill (not counted in ROI)
    # ==========================================
    li      t0, 11
    sd      t0, 8(sp)           # STORE pre-roi: [sp+8] = 11
    ld      t1, 8(sp)           # LOAD  pre-roi: -> SPILL (pre-ROI only)

    # ==========================================
    # m5_work_begin(0, 0) - ROI START
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    # ==========================================
    # ROI LOOP: 8 iterations x 2 spills = 16 ROI spills
    #
    # Spill slot A: sp+16  (store then load every iteration)
    # Spill slot B: sp+24  (store then load every iteration)
    # ==========================================
    li      s0, 0               # i = 0
    li      s1, 8               # limit = 8

roi_loop:
    bge     s0, s1, roi_loop_done

    # Spill A: store -> load same slot
    addi    t0, s0, 100         # t0 = i + 100
    sd      t0, 16(sp)          # STORE -> sp+16
    ld      t1, 16(sp)          # LOAD  -> sp+16  =>  SPILL (2i+1)

    # Spill B: store -> load same slot
    addi    t2, s0, 200         # t2 = i + 200
    sd      t2, 24(sp)          # STORE -> sp+24
    ld      t3, 24(sp)          # LOAD  -> sp+24  =>  SPILL (2i+2)

    addi    s0, s0, 1           # i++
    j       roi_loop

roi_loop_done:
    # ==========================================
    # m5_work_end(0, 0) - ROI END
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb600007b          # m5_work_end

    # ==========================================
    # POST-ROI: 1 spill (not counted in ROI)
    # ==========================================
    li      t4, 99
    sd      t4, 32(sp)          # STORE post-roi: [sp+32] = 99
    ld      t5, 32(sp)          # LOAD  post-roi: -> SPILL (post-ROI only)

    # ==========================================
    # Cleanup and Exit
    # ==========================================
    addi    sp, sp, 128
    li      a7, 93              # syscall: exit
    li      a0, 0               # exit code 0
    ecall

    .size _start, .-_start

# ==============================================================================
# EXPECTED RESULTS SUMMARY:
# ==============================================================================
#
# | Section      | Iterations | Spills/Iter | Total Spills | ROI Counted |
# |--------------|------------|-------------|--------------|-------------|
# | Pre-ROI      | 1          | 1           | 1            | NO          |
# | ROI loop     | 8          | 2           | 16           | YES         |
# | Post-ROI     | 1          | 1           | 1            | NO          |
# |--------------|------------|-------------|--------------|-------------|
# | Global total |            |             | 18           |             |
# | ROI only     |            |             | 16           |             |
#
# Verify: roi_spills = 16 in riscv_spill_stats.txt
# ==============================================================================
