# ==============================================================================
# Loop-Reload Spill Test - RISC-V Assembly
# ==============================================================================
#
# PURPOSE: The complement / contrast to spill_vs_loop.S.
#
#   spill_vs_loop.S Section 3:  loop with stores ONLY (no reload) -> 0 spills
#   THIS FILE:                  loop with store+reload every iteration -> 10 spills
#
#   The only difference is the extra "ld" inside the loop body.
#   This shows that the spill signal is the store-then-load pair,
#   NOT the store alone.
#
# DESIGN:
#   Pre-ROI  : 2 spills  (not counted in ROI)
#   ROI loop : 10 iterations x 1 spill per iteration = 10 ROI spills
#   Post-ROI : 1 spill   (not counted in ROI)
#
# HOW THE LOOP SPILL WORKS:
#   slot sp+16 is reused each iteration:
#     sd t0, 16(sp)  -> store_map[sp+16] = {t0, tick, ...}
#     ld t1, 16(sp)  -> map hit! erase entry, roi_spills++
#   Next iteration: sd puts sp+16 back in the map -> clean cycle.
#
# EXPECTED RESULTS (riscv_spill_stats.txt):
#   roi_spills  : 10
#   spill_rate  : 10 / roi_instructions * 100%
#
# COMPARISON:
#   spill_vs_loop.S  loop body:  sd a7, 0(a5)              -> 0 loop spills
#   THIS FILE        loop body:  sd t0, 16(sp) / ld t1, 16(sp) -> 10 loop spills
#
# m5ops encoding for RISC-V:
#   M5OP_WORK_BEGIN = 0xb400007b
#   M5OP_WORK_END   = 0xb600007b
#
# Compile: riscv64-linux-gnu-as -o loop_reload_spills.o loop_reload_spills.S
# Link:    riscv64-linux-gnu-ld -o loop_reload_spills.riscv loop_reload_spills.o
# Run:     ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#              --cmd=tests/spill_test/spill_vs_loop/loop_reload_spills.riscv \
#              --cpu-type=TimingSimpleCPU --caches
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    # ==========================================
    # PRE-ROI: 2 spills (not counted in ROI)
    # ==========================================
    li      t0, 11
    sd      t0, 8(sp)
    ld      t1, 8(sp)           # pre-ROI spill #1

    li      t2, 22
    sd      t2, 40(sp)
    ld      t3, 40(sp)          # pre-ROI spill #2

    # ==========================================
    # m5_work_begin(0, 0) - ROI START
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    # ==========================================
    # ROI LOOP: 10 iterations, 1 spill per iteration = 10 ROI spills
    #
    # Loop uses a single stack slot (sp+16) that is stored then reloaded.
    # store_map[sp+16] is erased on each matching load, so the next
    # iteration's store re-enters the slot cleanly.
    # ==========================================
    li      s0, 0               # i = 0
    li      s1, 10              # limit = 10

reload_loop:
    bge     s0, s1, reload_loop_done

    addi    t0, s0, 50          # t0 = i + 50  (unique value each iteration)
    sd      t0, 16(sp)          # STORE -> sp+16
    ld      t1, 16(sp)          # LOAD  -> sp+16  =>  SPILL (iteration i)

    addi    s0, s0, 1           # i++
    j       reload_loop

reload_loop_done:
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
    sd      t4, 48(sp)
    ld      t5, 48(sp)          # post-ROI spill

    # ==========================================
    # Cleanup and Exit
    # ==========================================
    addi    sp, sp, 64
    li      a7, 93              # syscall: exit
    li      a0, 0               # exit code 0
    ecall

    .size _start, .-_start

# ==============================================================================
# EXPECTED RESULTS SUMMARY:
# ==============================================================================
#
# | Section         | Iterations | Spills/Iter | Total Spills | ROI Counted |
# |-----------------|------------|-------------|--------------|-------------|
# | Pre-ROI         | 1          | 2           | 2            | NO          |
# | ROI loop        | 10         | 1           | 10           | YES         |
# | Post-ROI        | 1          | 1           | 1            | NO          |
# |-----------------|------------|-------------|--------------|-------------|
# | Global total    |            |             | 13           |             |
# | ROI only        |            |             | 10           |             |
#
# Verify: roi_spills = 10 in riscv_spill_stats.txt
#
# Key insight — loop body comparison:
#   spill_vs_loop.S : sd a7, 0(a5)                   -> store only  -> 0 spills
#   THIS FILE       : sd t0, 16(sp) / ld t1, 16(sp)  -> store+load  -> 1 spill/iter
# ==============================================================================
