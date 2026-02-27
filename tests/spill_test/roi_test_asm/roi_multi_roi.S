# ==============================================================================
# Multi-ROI Test - RISC-V Assembly
# ==============================================================================
#
# PURPOSE: Tests that two separate ROI windows produce two independent summary
#          blocks in riscv_spill_stats.txt with their own counters.
#          After our refactor, enterROI() resets all ROI counters, so ROI #2
#          must NOT accumulate spills from ROI #1.
#
# DESIGN:
#   Pre-ROI        : 2 spills  (not in any ROI)
#   ROI #1 (id=0)  : 3 spills
#   Between ROIs   : 2 spills  (not in any ROI)
#   ROI #2 (id=1)  : 5 spills
#   Post-ROI       : 1 spill   (not in any ROI)
#
# EXPECTED OUTPUT (riscv_spill_stats.txt) - two summary blocks:
#
#   # ROI SUMMARY  ISA=RISC-V  workid=0
#   # roi_spills : 3
#
#   # ROI SUMMARY  ISA=RISC-V  workid=1
#   # roi_spills : 5
#
# m5ops encoding for RISC-V:
#   M5OP_WORK_BEGIN = 0xb400007b
#   M5OP_WORK_END   = 0xb600007b
#
# Compile: riscv64-linux-gnu-as -o roi_multi_roi.o roi_multi_roi.S
# Link:    riscv64-linux-gnu-ld -o roi_multi_roi.riscv roi_multi_roi.o
# Run:     ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#              --cmd=tests/spill_test/roi_test_asm/roi_multi_roi.riscv \
#              --cpu-type=TimingSimpleCPU --caches
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -128

    # ==========================================
    # PRE-ROI: 2 spills (not counted in any ROI)
    # ==========================================
    li      t0, 10
    sd      t0, 8(sp)
    ld      t1, 8(sp)           # pre-ROI spill #1

    li      t2, 20
    sd      t2, 16(sp)
    ld      t3, 16(sp)          # pre-ROI spill #2

    # ==========================================
    # ROI #1 BEGIN (workid=0)
    # enterROI() clears store_map and resets ROI counters
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    li      t0, 101
    sd      t0, 24(sp)
    ld      t1, 24(sp)          # ROI1 spill #1

    li      t2, 102
    sd      t2, 32(sp)
    ld      t3, 32(sp)          # ROI1 spill #2

    li      t4, 103
    sd      t4, 40(sp)
    ld      t5, 40(sp)          # ROI1 spill #3

    # ==========================================
    # ROI #1 END -> writes summary block: roi_spills=3
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb600007b          # m5_work_end

    # ==========================================
    # BETWEEN ROIs: 2 spills (not counted in any ROI)
    # ==========================================
    li      t0, 50
    sd      t0, 48(sp)
    ld      t1, 48(sp)          # between-ROI spill #1

    li      t2, 60
    sd      t2, 56(sp)
    ld      t3, 56(sp)          # between-ROI spill #2

    # ==========================================
    # ROI #2 BEGIN (workid=1)
    # enterROI() clears store_map and resets ROI counters to 0 again
    # ==========================================
    li      a0, 1               # workid = 1
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    li      t0, 201
    sd      t0, 64(sp)
    ld      t1, 64(sp)          # ROI2 spill #1

    li      t2, 202
    sd      t2, 72(sp)
    ld      t3, 72(sp)          # ROI2 spill #2

    li      t4, 203
    sd      t4, 80(sp)
    ld      t5, 80(sp)          # ROI2 spill #3

    li      t0, 204
    sd      t0, 88(sp)
    ld      t1, 88(sp)          # ROI2 spill #4

    li      t2, 205
    sd      t2, 96(sp)
    ld      t3, 96(sp)          # ROI2 spill #5

    # ==========================================
    # ROI #2 END -> writes summary block: roi_spills=5
    # ==========================================
    li      a0, 1               # workid = 1
    li      a1, 0               # threadid = 0
    .long   0xb600007b          # m5_work_end

    # ==========================================
    # POST-ROI: 1 spill (not counted in any ROI)
    # ==========================================
    li      t4, 999
    sd      t4, 104(sp)
    ld      t5, 104(sp)         # post-ROI spill

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
# | Section        | Spills | Counted in ROI | ROI id |
# |----------------|--------|----------------|--------|
# | Pre-ROI        | 2      | NO             | -      |
# | ROI #1         | 3      | YES            | 0      |
# | Between ROIs   | 2      | NO             | -      |
# | ROI #2         | 5      | YES            | 1      |
# | Post-ROI       | 1      | NO             | -      |
# |----------------|--------|----------------|--------|
# | Global total   | 13     |                |        |
#
# riscv_spill_stats.txt must contain TWO separate summary blocks:
#   Block 1 (workid=0): roi_spills = 3
#   Block 2 (workid=1): roi_spills = 5
#
# If Block 2 shows roi_spills = 8, enterROI() counter reset is broken.
# ==============================================================================
