# ==============================================================================
# TC4c — Non-Spill Evicted By Non-Spill  (control group, box #3)
# ==============================================================================
#
# SCENARIO:
#   Baseline / control case: ordinary stack traffic evicts OTHER ordinary
#   stack traffic. No spill is involved anywhere in this test. This is
#   the "spill has nothing to do with it" box -- its count should never
#   be attributed to spilling in the report.
#
#   Same single-cache-line trick as TC4a/b (see Run command).
#
# ROI LAYOUT (3 memory ops):
#   1. sd t0, 0(a3)        NON-SPILL STORE @sp+64 (a3 = sp+64) -> installs
#   2. sd t1, 0(a4)        NON-SPILL STORE @sp+128 (a4 = sp+128) -> evicts
#                           sp+64's line
#                           ledger[sp+64] = evicted-by-non-spill
#   3. ld t2, 0(a3)        NON-SPILL LOAD @sp+64 -> filtered into
#                           roi_nonspill_reuse (not sp/fp-relative). Cache
#                           line holds sp+128's data -> MISS.
#                           ledger says sp+64 was evicted by non-spill
#                           -> nonSpillEvictedByNonSpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 2
#   roi_loads            : 1
#   roi_spills           : 0
#   roi_nonspill_reuse   : 1
#
# EXPECTED (new eviction-ledger counter, NOT implemented yet):
#   nonSpillEvictedByNonSpill : 1
#   (all other 3 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4c_nonspill_evicted_by_nonspill.o tc4c_nonspill_evicted_by_nonspill.S
#   $LD -o tc4c_nonspill_evicted_by_nonspill.riscv tc4c_nonspill_evicted_by_nonspill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4c_nonspill_evicted_by_nonspill/tc4c_nonspill_evicted_by_nonspill.riscv \
#       --cpu-type=TimingSimpleCPU --caches \
#       --l1d_size=64B --l1d_assoc=1 --cacheline_size=64
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -192

    # ----------------------------------------------------------
    # ROI BEGIN
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin

    # 1. NON-SPILL STORE @sp+64 via a3 -- installs the (only) cache line
    addi    a3, sp, 64
    li      t0, 111
    sd      t0, 0(a3)           # STORE #1 (non-spill: base reg is a3)

    # 2. NON-SPILL STORE @sp+128 via a4 -- evicts sp+64's line
    addi    a4, sp, 128
    li      t1, 222
    sd      t1, 0(a4)           # STORE #2 (non-spill: base reg is a4)

    # 3. NON-SPILL LOAD @sp+64 via a3 -- filtered into roi_nonspill_reuse.
    #    Cache line now holds sp+128's data -> MISS.
    ld      t2, 0(a3)           # LOAD #1 -> filtered (non-spill), cache MISS

    # ----------------------------------------------------------
    # ROI END
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end -> writes summary

    addi    sp, sp, 192
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
