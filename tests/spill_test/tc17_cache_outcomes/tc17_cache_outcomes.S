    # Pins the absolute cache outcome of three spill pairs.
    # Run with a 1-line L1D (64B, direct mapped) and a 1KiB direct-mapped L2,
    # so the L2 has 16 sets and set = (addr >> 6) & 15.
    #
    #   pair A (768(sp), L2 set 12): store L1 hit,            reload L1 hit
    #   pair B (832(sp), L2 set 13): store L1 miss + L2 miss, reload L1 miss + L2 hit
    #   pair C (896(sp), L2 set 14): store L1 miss + L2 miss, reload L1 miss + L2 miss
    #
    # sp is aligned to 1 KiB first, so the slot sets do not depend on the
    # initial stack pointer (which moves with the binary path length).
    # The code lines sit in L2 sets 2-5, away from the slots.
    .text
    .globl _start
    .type _start, @function

_start:
    andi    sp, sp, -1024
    addi    sp, sp, -1024
    sd      zero, 768(sp)       # pre-ROI: bring slot A into the 1-line L1D
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(0, 0)

    # Pair A: A is still the only line in L1D -> hit on both sides.
    li      t0, 1
    sd      t0, 768(sp)
    ld      t1, 768(sp)

    # Pair B: B was never touched -> store misses L1 and L2. A non-stack
    # load to L2 set 0 then pushes B out of L1 only, so the reload hits L2.
    li      t0, 2
    sd      t0, 832(sp)
    lla     a3, flush_buf
    ld      t3, 0(a3)
    ld      t1, 832(sp)

    # Pair C: store misses L1 and L2. Walking 2 KiB of .bss sweeps every set
    # of the 1 KiB L2 twice, so C is gone from both levels at reload time.
    li      t0, 3
    sd      t0, 896(sp)
    lla     a3, flush_buf
    li      t4, 32
1:  ld      t5, 0(a3)
    addi    a3, a3, 64
    addi    t4, t4, -1
    bnez    t4, 1b
    ld      t1, 896(sp)

    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end(0, 0)

    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start

    .bss
    .balign 1024
flush_buf:
    .zero   2048
