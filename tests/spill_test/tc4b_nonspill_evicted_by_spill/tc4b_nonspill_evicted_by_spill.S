# ==============================================================================
# TC4b — Non-Spill Evicted By Spill  (eviction-attribution box #2)
# ==============================================================================
#
# SCENARIO:
#   Ordinary stack traffic (a computed-pointer access, e.g. a local array
#   slot -- NOT a spill) is stored first. Before it is read back, a
#   register SPILL is stored to a different address that maps to the SAME
#   cache line, evicting the non-spill data. When the non-spill value is
#   read back, it misses -- and the ledger must say a spill did it.
#
#   Same single-cache-line trick as TC4a (see Run command).
#
# ROI LAYOUT (3 memory ops):
#   1. sd t0, 0(a3)        NON-SPILL STORE @sp+64 (a3 = sp+64) -> installs;
#                           store_map[sp+64] recorded with sp_relative=false
#   2. sd t1, 0(sp)        SPILL STORE @sp+0 -> evicts sp+64's line
#                           ledger[sp+64] = evicted-by-spill
#   3. ld t2, 0(a3)        NON-SPILL LOAD @sp+64 -> store_map has an entry
#                           for sp+64, but its sp_relative flag is false
#                           (recorded at store time) AND this load is also
#                           not sp/fp-relative -> filter fails on BOTH
#                           sides -> NOT a genuine spill, counted instead
#                           in roi_nonspill_reuse. Cache line holds sp+0's
#                           data now -> MISS.
#                           ledger says sp+64 was evicted by spill
#                           -> nonSpillEvictedBySpill += 1
#
# EXPECTED (existing SpillDetector counters, verifiable with current code):
#   roi_stores          : 2
#   roi_loads            : 1
#   roi_spills           : 0
#   roi_nonspill_reuse   : 1   (load #3 -- filtered out by SP/FP filter)
#
# EXPECTED (new eviction-ledger counter, NOT implemented yet):
#   nonSpillEvictedBySpill : 1
#   (all other 3 boxes: 0)
#
# m5ops encoding:
#   m5_work_begin = 0xb400007b
#   m5_work_end   = 0xb600007b
#
# Build:
#   AS=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as
#   LD=/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld
#   $AS -o tc4b_nonspill_evicted_by_spill.o tc4b_nonspill_evicted_by_spill.S
#   $LD -o tc4b_nonspill_evicted_by_spill.riscv tc4b_nonspill_evicted_by_spill.o
#
# Run:
#   ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
#       --cmd=tests/spill_test/tc4b_nonspill_evicted_by_spill/tc4b_nonspill_evicted_by_spill.riscv \
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

    # 1. NON-SPILL STORE @sp+64 via computed pointer a3 -- installs the
    #    (only) cache line. This models e.g. a stack array element write.
    addi    a3, sp, 64
    li      t0, 111
    sd      t0, 0(a3)           # STORE #1 (non-spill: base reg is a3)

    # 2. SPILL STORE @sp+0 -- sp-relative -> evicts sp+64's line
    li      t1, 222
    sd      t1, 0(sp)           # STORE #2 (spill-store candidate)

    # 3. NON-SPILL LOAD @sp+64 via a3 -- store_map has an entry for sp+64
    #    but it is not sp/fp-relative on either side, so this is filtered
    #    into roi_nonspill_reuse, not counted as a spill. Cache line now
    #    holds sp+0's data -> MISS.
    ld      t2, 0(a3)           # LOAD #1 -> filtered (non-spill), cache MISS

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
