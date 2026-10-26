# ==============================================================================
# TC1 — Callee-Save Register Spill
# ==============================================================================
#
# SCENARIO:
#   Simulates a real function prologue/epilogue spill pattern.
#   A function must preserve the caller's s0-s5 registers (callee-saved ABI).
#   It saves them to the stack frame at entry, uses them for computation,
#   then restores them before returning.
#
#   This is the most common real-world source of register spills:
#   every non-leaf function does exactly this.
#
# IMPORTANT DETAIL — store and load are NOT adjacent:
#   Unlike simpler tests, there is real computation between the sd and ld.
#   The SpillDetector must track sp+0 through sp+40 across the intervening
#   instructions, then match each reload. This tests the store_map's ability
#   to hold entries across a non-trivial basic block.
#
# ROI LAYOUT:
#   [ROI BEGIN]
#     Prologue : sd s0-s5 onto stack    (6 stores, no loads yet)
#     Body     : li / add / mul ...     (pure arithmetic, no spill hazard)
#     Epilogue : ld s0-s5 from stack    (6 loads matching the 6 stores → 6 SPILLS)
#   [ROI END]
#
# EXPECTED RESULT:
#   roi_spills  : 6
#   roi_stores  : 6
#   roi_loads   : 6
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc1_callee_save.o tc1_callee_save.S
#   $LD -o tc1_callee_save.riscv tc1_callee_save.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc1_callee_save/tc1_callee_save.riscv \
#       --cpu-type=TimingSimpleCPU --caches
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # Allocate 64-byte stack frame (holds 8 x 8-byte slots)
    addi    sp, sp, -64

    # ----------------------------------------------------------
    # ROI BEGIN — everything inside counts for spill detection
    # ----------------------------------------------------------
    li      a0, 0               # workid  = 0
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    # ----------------------------------------------------------
    # PROLOGUE: save callee-saved regs s0-s5 onto the stack frame
    # The compiler emits exactly this code for non-leaf functions.
    # ----------------------------------------------------------
    sd      s0, 0(sp)           # STORE #1 — save s0
    sd      s1, 8(sp)           # STORE #2 — save s1
    sd      s2, 16(sp)          # STORE #3 — save s2
    sd      s3, 24(sp)          # STORE #4 — save s3
    sd      s4, 32(sp)          # STORE #5 — save s4
    sd      s5, 40(sp)          # STORE #6 — save s5

    # ----------------------------------------------------------
    # FUNCTION BODY: use s0-s5 for an independent computation.
    # These instructions create distance between store and load,
    # confirming the store_map retains entries across real work.
    # ----------------------------------------------------------
    li      s0, 3               # s0 = 3
    li      s1, 7               # s1 = 7
    add     s2, s0, s1          # s2 = 10
    mul     s3, s2, s0          # s3 = 30
    add     s4, s3, s1          # s4 = 37
    add     s5, s4, s2          # s5 = 47
    # (result in s5 — not used further; body is for instruction distance)

    # ----------------------------------------------------------
    # EPILOGUE: restore s0-s5 — each ld matches its earlier sd → SPILL
    # ----------------------------------------------------------
    ld      s0, 0(sp)           # LOAD #1  → SPILL (matches STORE #1)
    ld      s1, 8(sp)           # LOAD #2  → SPILL (matches STORE #2)
    ld      s2, 16(sp)          # LOAD #3  → SPILL (matches STORE #3)
    ld      s3, 24(sp)          # LOAD #4  → SPILL (matches STORE #4)
    ld      s4, 32(sp)          # LOAD #5  → SPILL (matches STORE #5)
    ld      s5, 40(sp)          # LOAD #6  → SPILL (matches STORE #6)

    # ----------------------------------------------------------
    # ROI END
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end  → writes summary

    # Restore stack and exit
    addi    sp, sp, 64
    li      a7, 93              # Linux syscall: exit
    li      a0, 0               # exit code 0
    ecall

    .size _start, .-_start

# ==============================================================================
# EXPECTED OUTPUT (riscv_spill_stats.txt):
# ==============================================================================
#
# # ROI SUMMARY  ISA=RISC-V  workid=0
# # roi_stores         : 6
# # roi_loads          : 6
# # roi_spills         : 6
# # spill_rate         : 6 / roi_instructions * 100%
#
# ==============================================================================
