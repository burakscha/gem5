# ==============================================================================
# TC4f — Non-Spill Store Evicted By Spill  (eviction-attribution box #6)
# ==============================================================================
#
# SCENARIO:
#   The STORE-side sibling of TC4b. An ordinary (non-spill) stack slot is
#   written to a SECOND time, and that second write misses because a
#   spill access evicted it in between.
#
#   Same single-cache-line trick as TC4a-d (see Run command).
#
# ROI LAYOUT (3 memory ops, all stores):
#   1. sd t0, 0(a3)        NON-SPILL STORE #1 @sp+64 (a3) -- installs
#   2. sd t1, 0(sp)        SPILL STORE @sp+0 -> evicts sp+64's line
#                           ledger[sp+64] = evicted-by-spill
#   3. sd t2, 0(a3)        NON-SPILL STORE #2 @sp+64 -- same slot written
#                           again. Cache line now holds sp+0's data -> MISS.
#                           ledger says sp+64 was evicted by spill
#                           -> nonSpillStoreEvictedBySpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 3
#   roi_loads            : 0
#   roi_spills           : 0
#   roi_nonspill_reuse   : 0
#
# EXPECTED (new eviction-ledger counter):
#   nonSpillStoreEvictedBySpill : 1
#   (all other 7 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4f_nonspillstore_evicted_by_spill.o tc4f_nonspillstore_evicted_by_spill.S
#   $LD -o tc4f_nonspillstore_evicted_by_spill.riscv tc4f_nonspillstore_evicted_by_spill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4f_nonspillstore_evicted_by_spill/tc4f_nonspillstore_evicted_by_spill.riscv \
#       --cpu-type=TimingSimpleCPU --caches \
#       --l1d_size=64B --l1d_assoc=1 --cacheline_size=64
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -128

    # ----------------------------------------------------------
    # ROI BEGIN
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin

    # 1. NON-SPILL STORE #1 @sp+64 via a3 -- installs the (only) cache line
    addi    a3, sp, 64
    li      t0, 111
    sd      t0, 0(a3)           # STORE #1 (non-spill: base reg is a3)

    # 2. SPILL STORE @sp+0 -- evicts sp+64's line
    li      t1, 222
    sd      t1, 0(sp)           # STORE #2 (spill-store candidate)

    # 3. NON-SPILL STORE #2 @sp+64 via a3 -- same slot reused. Cache line
    #    now holds sp+0's data -> this write MISSES.
    li      t2, 333
    sd      t2, 0(a3)           # STORE #3 (non-spill), MISS

    # ----------------------------------------------------------
    # ROI END
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end -> writes summary

    addi    sp, sp, 128
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
