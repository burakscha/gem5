# ==============================================================================
# TC4e — Spill Store Evicted By Non-Spill  (eviction-attribution box #5)
# ==============================================================================
#
# SCENARIO:
#   The STORE-side sibling of TC4a. Instead of a spill LOAD missing, here
#   the SAME spill slot is written to a SECOND time (as happens whenever a
#   function re-enters the same stack depth, e.g. a loop or a recursive
#   call) and that second WRITE itself misses because a non-spill access
#   evicted the slot in between.
#
#   Same single-cache-line trick as TC4a-d (see Run command).
#
# ROI LAYOUT (3 memory ops, all stores -- no load at all):
#   1. sd t0, 0(sp)        SPILL STORE #1 @sp+0 -- installs (compulsory)
#   2. sd t1, 0(a3)        NON-SPILL STORE @sp+64 (a3, not sp/s0) ->
#                           evicts sp+0's line
#                           ledger[sp+0] = evicted-by-non-spill
#   3. sd t2, 0(sp)        SPILL STORE #2 @sp+0 -- same slot written again
#                           (this is exactly what happens on a loop
#                           iteration or re-entering the same call depth).
#                           Cache line now holds sp+64's data -> MISS.
#                           ledger says sp+0 was evicted by non-spill
#                           -> spillStoreEvictedByNonSpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 3
#   roi_loads            : 0
#   roi_spills           : 0   (no load ever happens, so no spill is
#                                *detected* by the software-side matcher --
#                                that is unrelated to this test, which is
#                                about the cache-level write-miss path)
#   roi_nonspill_reuse   : 0
#
# EXPECTED (new eviction-ledger counter):
#   spillStoreEvictedByNonSpill : 1
#   (all other 7 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4e_spillstore_evicted_by_nonspill.o tc4e_spillstore_evicted_by_nonspill.S
#   $LD -o tc4e_spillstore_evicted_by_nonspill.riscv tc4e_spillstore_evicted_by_nonspill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4e_spillstore_evicted_by_nonspill/tc4e_spillstore_evicted_by_nonspill.riscv \
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

    # 2. NON-SPILL STORE @sp+64 via a3 -- evicts sp+0's line
    addi    a3, sp, 64
    li      t1, 222
    sd      t1, 0(a3)           # STORE #2 (non-spill: base reg is a3)

    # 3. SPILL STORE #2 @sp+0 -- same slot reused (2nd write). Cache line
    #    now holds sp+64's data -> this write MISSES.
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
