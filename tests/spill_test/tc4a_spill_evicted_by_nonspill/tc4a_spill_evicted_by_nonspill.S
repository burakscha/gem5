# ==============================================================================
# TC4a — Spill Evicted By Non-Spill  (eviction-attribution box #1)
# ==============================================================================
#
# SCENARIO:
#   A register spill is stored to the stack. Before it is reloaded, a
#   NON-spill access (stack traffic via a computed pointer, not sp/fp
#   relative) touches a different address that maps to the SAME cache
#   line and evicts the spill's data. When the spill is finally reloaded,
#   it misses -- and the "who evicted it" ledger must say: a non-spill
#   access did it.
#
#   Requires a cache with exactly ONE line (see Run command) so that any
#   second distinct address is guaranteed to evict the first.
#
# ROI LAYOUT (3 memory ops):
#   1. sd t0, 0(sp)        SPILL STORE  @sp+0   (installs; store_map[sp+0])
#   2. sd t1, 0(a3)        NON-SPILL STORE @sp+64 (a3 = sp+64, NOT sp/s0
#                           relative) -> evicts sp+0's line
#                           ledger[sp+0] = evicted-by-non-spill
#   3. ld t2, 0(sp)        SPILL LOAD @sp+0 -> matches store_map[sp+0]
#                           (genuine spill, roi_spills++) but the line now
#                           holds sp+64's data -> MISS
#                           ledger says sp+0 was evicted by non-spill
#                           -> spillEvictedByNonSpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 2
#   roi_loads            : 1
#   roi_spills           : 1   (load #3 matches store #1, both sp-relative)
#   roi_nonspill_reuse   : 0
#
# EXPECTED (new eviction-ledger counter, requires the cache instrumentation
# described in our design discussion -- NOT implemented yet):
#   spillEvictedByNonSpill : 1
#   (all other 3 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4a_spill_evicted_by_nonspill.o tc4a_spill_evicted_by_nonspill.S
#   $LD -o tc4a_spill_evicted_by_nonspill.riscv tc4a_spill_evicted_by_nonspill.o
#
# Run (note the single-cache-line config -- this is what forces the evict):
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4a_spill_evicted_by_nonspill/tc4a_spill_evicted_by_nonspill.riscv \
#       --cpu-type=TimingSimpleCPU --caches \
#       --l1d_size=64B --l1d_assoc=1 --cacheline_size=64
# ==============================================================================

    .text
    .globl _start
    .type _start, @function

_start:
    # Frame big enough for offsets 0 and 64 with headroom
    addi    sp, sp, -128

    # ----------------------------------------------------------
    # ROI BEGIN
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin

    # 1. SPILL STORE @sp+0 -- sp-relative, installs the (only) cache line
    li      t0, 111
    sd      t0, 0(sp)           # STORE #1 (spill-store candidate)

    # 2. NON-SPILL STORE @sp+64 via a computed pointer (a3), NOT sp/s0
    #    -> evicts sp+0's line (only 1 line exists)
    addi    a3, sp, 64
    li      t1, 222
    sd      t1, 0(a3)           # STORE #2 (non-spill: base reg is a3)

    # 3. SPILL LOAD @sp+0 -- matches STORE #1 in store_map -> genuine spill.
    #    But the cache line now holds sp+64's data -> MISS.
    ld      t2, 0(sp)           # LOAD #1 -> SPILL, and a cache MISS

    # ----------------------------------------------------------
    # ROI END
    # ----------------------------------------------------------
    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end -> writes summary

    addi    sp, sp, 128
    li      a7, 93               # Linux syscall: exit
    li      a0, 0
    ecall

    .size _start, .-_start
