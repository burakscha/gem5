# ==============================================================================
# Zero-Spill ROI Test - RISC-V Assembly
# ==============================================================================
#
# PURPOSE: Verifies that the detector produces NO false positives.
#          The ROI window contains memory accesses that do NOT form valid
#          spill patterns. Expected roi_spills = 0.
#
# DESIGN - three "non-spill" cases inside the ROI:
#
#   Case 1 - "Orphan load":
#     A value is stored to [sp+8] BEFORE the ROI.
#     enterROI() calls store_map.clear(), erasing that entry.
#     The load inside ROI finds no match in the map -> NOT a spill.
#
#   Case 2 - "Orphan stores":
#     Three stores inside the ROI to unique addresses ([sp+16], [sp+24], [sp+32]).
#     None of them is ever followed by a load -> no spill pattern completes.
#
#   Case 3 - "Pure arithmetic":
#     li, add, mul, xor instructions only.
#     No memory access at all -> spill detection not even triggered.
#
# EXPECTED RESULTS (riscv_spill_stats.txt):
#   roi_spills  : 0
#   spill_rate  : 0.0000%
#
# m5ops encoding for RISC-V:
#   M5OP_WORK_BEGIN = 0xb400007b
#   M5OP_WORK_END   = 0xb600007b
#
# Compile: riscv64-linux-gnu-as -o roi_zero_spill.o roi_zero_spill.S
# Link:    riscv64-linux-gnu-ld -o roi_zero_spill.riscv roi_zero_spill.o
# Run:     ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#              --cmd=tests/spill_test/spill_exact/roi_zero_spill.riscv \
#              --cpu-type=TimingSimpleCPU --caches
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    # ==========================================
    # PRE-ROI: Store to [sp+8] = 42
    # This entry will be in store_map when ROI begins.
    # enterROI() calls store_map.clear() -> it will be gone.
    # ==========================================
    li      t0, 42
    sd      t0, 8(sp)           # STORE pre-roi: [sp+8] = 42

    # ==========================================
    # m5_work_begin(0, 0) - ROI START
    # store_map is cleared here -> pre-ROI store disappears
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb400007b          # m5_work_begin

    # ------------------------------------------
    # Case 1: Orphan load
    # [sp+8] was stored before ROI; store_map was cleared.
    # Load finds nothing -> no spill.
    # ------------------------------------------
    ld      t1, 8(sp)           # LOAD: store_map empty for this address -> no spill

    # ------------------------------------------
    # Case 2: Orphan stores (never reloaded inside ROI)
    # These sit in store_map until ROI ends or window expires.
    # No matching load -> no spill.
    # ------------------------------------------
    li      t2, 100
    sd      t2, 16(sp)          # STORE [sp+16] = 100  (never reloaded)

    li      t3, 200
    sd      t3, 24(sp)          # STORE [sp+24] = 200  (never reloaded)

    li      t4, 300
    sd      t4, 32(sp)          # STORE [sp+32] = 300  (never reloaded)

    # ------------------------------------------
    # Case 3: Pure arithmetic - no memory access
    # None of these can trigger spill detection.
    # ------------------------------------------
    li      t0, 7
    li      t1, 13
    add     t2, t0, t1          # t2 = 20
    mul     t3, t2, t0          # t3 = 140
    xor     t4, t3, t1          # t4 = 140 ^ 13 = 129
    add     t5, t4, t2          # t5 = 149   (pure computation, no memory)

    # ==========================================
    # m5_work_end(0, 0) - ROI END
    # ==========================================
    li      a0, 0               # workid = 0
    li      a1, 0               # threadid = 0
    .long   0xb600007b          # m5_work_end

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
# | ROI Memory Access          | Type   | Spill? | Reason                           |
# |----------------------------|--------|--------|----------------------------------|
# | ld t1, 8(sp)               | LOAD   | NO     | store_map cleared at ROI entry   |
# | sd [sp+16], [sp+24],[sp+32]| STORE  | NO     | Never followed by a load in ROI  |
# | li, add, mul, xor          | ARITH  | NO     | No memory access at all          |
# |----------------------------|--------|--------|----------------------------------|
# | roi_spills                 |        |   0    |                                  |
#
# Verify: roi_spills = 0 and spill_rate = 0.0000% in riscv_spill_stats.txt
#
# If roi_spills > 0, the detector has a false positive bug.
# ==============================================================================
