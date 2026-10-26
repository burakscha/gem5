# ==============================================================================
# TC4d — Spill Evicted By Spill  (self-interference, box #4)
# ==============================================================================
#
# SCENARIO:
#   Two DIFFERENT spilled values compete for the one cache line. The
#   first spill store is evicted by a second, unrelated spill store
#   before the first can be reloaded. This isolates "spill traffic
#   evicting itself" from either of the cross-category cases in TC4a/b.
#
#   Same single-cache-line trick as TC4a/b/c (see Run command).
#
# ROI LAYOUT (3 memory ops):
#   1. sd t0, 0(sp)         SPILL STORE @sp+0 -> installs; store_map[sp+0]
#   2. sd t1, 64(sp)        SPILL STORE @sp+64 -> evicts sp+0's line
#                            ledger[sp+0] = evicted-by-spill
#   3. ld t2, 0(sp)         SPILL LOAD @sp+0 -> matches store_map[sp+0]
#                            (genuine spill, roi_spills++). Cache line now
#                            holds sp+64's data -> MISS.
#                            ledger says sp+0 was evicted by spill
#                            -> spillEvictedBySpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 2
#   roi_loads            : 1
#   roi_spills           : 1
#   roi_nonspill_reuse   : 0
#
# EXPECTED (new eviction-ledger counter, NOT implemented yet):
#   spillEvictedBySpill : 1
#   (all other 3 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4d_spill_evicted_by_spill.o tc4d_spill_evicted_by_spill.S
#   $LD -o tc4d_spill_evicted_by_spill.riscv tc4d_spill_evicted_by_spill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4d_spill_evicted_by_spill/tc4d_spill_evicted_by_spill.riscv \
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

    # 1. SPILL STORE @sp+0 -- installs the (only) cache line
    li      t0, 111
    sd      t0, 0(sp)           # STORE #1 (spill-store candidate)

    # 2. SPILL STORE @sp+64 -- a second, unrelated spill -> evicts sp+0
    li      t1, 222
    sd      t1, 64(sp)          # STORE #2 (spill-store candidate)

    # 3. SPILL LOAD @sp+0 -- matches STORE #1 -> genuine spill. Cache line
    #    now holds sp+64's data -> MISS.
    ld      t2, 0(sp)           # LOAD #1 -> SPILL, and a cache MISS

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
