# ==============================================================================
# TC1 — Callee-Saved Register Save/Restore (csave class)
# ==============================================================================
#
# SCENARIO:
#   A function prologue/epilogue: s0-s5 are callee-saved under the ABI, so
#   the function saves them to its frame at entry, uses them, and restores
#   them before returning. Every non-leaf function does this.
#
#   At the instruction level this is indistinguishable from a register spill
#   (an SP-relative store, a same-address same-width reload later). It is not
#   one: the register allocator did not run out of registers. The six stores
#   carry csave_store_* labels, which the test runner turns into csave_store
#   records of the stack PC map, the way scripts/build_stack_pc_map.py takes
#   them from a real binary's CFI. All six pairs must land in the csave
#   class, none in spill.
#
# IMPORTANT DETAIL — store and load are NOT adjacent:
#   There is real computation between the sd and ld. The SpillDetector must
#   track sp+0 through sp+40 across the intervening instructions, then match
#   each reload. This tests the store_map's ability to hold entries across a
#   non-trivial basic block.
#
# ROI LAYOUT:
#   [ROI BEGIN]
#     Prologue : sd s0-s5 onto stack    (6 csave stores, no loads yet)
#     Body     : li / add / mul ...     (pure arithmetic)
#     Epilogue : ld s0-s5 from stack    (6 restores -> 6 csave events)
#   [ROI END]
#
# EXPECTED RESULT:
#   csave_store : 6   csave_load : 6   csave_event : 6
#   spill_event : 0   other_stack_event : 0
#   roi_store   : 6   roi_load   : 6
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
csave_store_1:
    sd      s0, 0(sp)           # STORE #1 — save s0
csave_store_2:
    sd      s1, 8(sp)           # STORE #2 — save s1
csave_store_3:
    sd      s2, 16(sp)          # STORE #3 — save s2
csave_store_4:
    sd      s3, 24(sp)          # STORE #4 — save s3
csave_store_5:
    sd      s4, 32(sp)          # STORE #5 — save s4
csave_store_6:
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
    ld      s0, 0(sp)           # LOAD #1  → csave restore (matches STORE #1)
    ld      s1, 8(sp)           # LOAD #2  → csave restore (matches STORE #2)
    ld      s2, 16(sp)          # LOAD #3  → csave restore (matches STORE #3)
    ld      s3, 24(sp)          # LOAD #4  → csave restore (matches STORE #4)
    ld      s4, 32(sp)          # LOAD #5  → csave restore (matches STORE #5)
    ld      s5, 40(sp)          # LOAD #6  → csave restore (matches STORE #6)

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
