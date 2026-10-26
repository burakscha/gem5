# ==============================================================================
# TC4h — Spill Store Evicted By Spill  (self-interference, box #8)
# ==============================================================================
#
# SCENARIO:
#   The STORE-side sibling of TC4d. Two different spilled values compete
#   for the one cache line; the first spill's slot is evicted by a
#   second, unrelated spill store, and the first spill's slot is then
#   written to AGAIN (e.g. next loop iteration) -- that second write
#   misses because of the other spill.
#
#   Same single-cache-line trick as TC4a-d (see Run command).
#
# ROI LAYOUT (3 memory ops, all stores):
#   1. sd t0, 0(sp)         SPILL STORE #1 @sp+0 -- installs
#   2. sd t1, 64(sp)        SPILL STORE @sp+64 -> evicts sp+0
#                            ledger[sp+0] = evicted-by-spill
#   3. sd t2, 0(sp)         SPILL STORE #2 @sp+0 -- same slot reused.
#                            Cache line now holds sp+64's data -> MISS.
#                            ledger says sp+0 was evicted by spill
#                            -> spillStoreEvictedBySpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 3
#   roi_loads            : 0
#   roi_spills           : 0
#   roi_nonspill_reuse   : 0
#
# EXPECTED (new eviction-ledger counter):
#   spillStoreEvictedBySpill : 1
#   (all other 7 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4h_spillstore_evicted_by_spill.o tc4h_spillstore_evicted_by_spill.S
#   $LD -o tc4h_spillstore_evicted_by_spill.riscv tc4h_spillstore_evicted_by_spill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4h_spillstore_evicted_by_spill/tc4h_spillstore_evicted_by_spill.riscv \
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

    # 1. SPILL STORE #1 @sp+0 -- installs the (only) cache line
    li      t0, 111
    sd      t0, 0(sp)           # STORE #1 (spill-store candidate)

    # 2. SPILL STORE @sp+64 -- a second, unrelated spill -> evicts sp+0
    li      t1, 222
    sd      t1, 64(sp)          # STORE #2 (spill-store candidate)

    # 3. SPILL STORE #2 @sp+0 -- same slot reused. Cache line now holds
    #    sp+64's data -> this write MISSES.
    li      t2, 333
    sd      t2, 0(sp)           # STORE #3 (spill-store candidate), MISS

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
