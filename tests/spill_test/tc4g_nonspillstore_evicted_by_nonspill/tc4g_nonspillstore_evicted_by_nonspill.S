# ==============================================================================
# TC4g — Non-Spill Store Evicted By Non-Spill  (control group, box #7)
# ==============================================================================
#
# SCENARIO:
#   The STORE-side sibling of TC4c. Baseline / control case: ordinary
#   stack traffic evicts OTHER ordinary stack traffic, and the second
#   write to the displaced slot misses. No spill involved anywhere.
#
#   Same single-cache-line trick as TC4a-d (see Run command).
#
# ROI LAYOUT (3 memory ops, all stores):
#   1. sd t0, 0(a3)        NON-SPILL STORE #1 @sp+64 (a3) -- installs
#   2. sd t1, 0(a4)        NON-SPILL STORE @sp+128 (a4) -> evicts sp+64
#                           ledger[sp+64] = evicted-by-non-spill
#   3. sd t2, 0(a3)        NON-SPILL STORE #2 @sp+64 -- same slot reused.
#                           Cache line now holds sp+128's data -> MISS.
#                           ledger says sp+64 was evicted by non-spill
#                           -> nonSpillStoreEvictedByNonSpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 3
#   roi_loads            : 0
#   roi_spills           : 0
#   roi_nonspill_reuse   : 0
#
# EXPECTED (new eviction-ledger counter):
#   nonSpillStoreEvictedByNonSpill : 1
#   (all other 7 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4g_nonspillstore_evicted_by_nonspill.o tc4g_nonspillstore_evicted_by_nonspill.S
#   $LD -o tc4g_nonspillstore_evicted_by_nonspill.riscv tc4g_nonspillstore_evicted_by_nonspill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4g_nonspillstore_evicted_by_nonspill/tc4g_nonspillstore_evicted_by_nonspill.riscv \
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

    # 1. NON-SPILL STORE #1 @sp+64 via a3 -- installs the (only) cache line
    addi    a3, sp, 64
    li      t0, 111
    sd      t0, 0(a3)           # STORE #1 (non-spill: base reg is a3)

    # 2. NON-SPILL STORE @sp+128 via a4 -- evicts sp+64's line
    addi    a4, sp, 128
    li      t1, 222
    sd      t1, 0(a4)           # STORE #2 (non-spill: base reg is a4)

    # 3. NON-SPILL STORE #2 @sp+64 via a3 -- same slot reused. Cache line
    #    now holds sp+128's data -> this write MISSES.
    li      t2, 333
    sd      t2, 0(a3)           # STORE #3 (non-spill), MISS

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
