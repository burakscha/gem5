    # Cache organisation check: the same two spill pairs give a different L1
    # outcome under direct-mapped, 8-way and fully associative L1D, so a
    # mis-configured profile cannot go unnoticed. Run with the small sizes
    # (L1D 4 KiB = 64 lines of 64 B):
    #
    #   pair A: one other line in A's set (A+4096) before the reload
    #   pair B: eight other lines in B's set (B+512*i, i=1..8) before the reload
    #
    #                     sets   pair A reload   pair B reload
    #   direct-mapped      64    miss            miss (B+4096 conflicts)
    #   8-way               8    hit (2 of 8)    miss (9 lines > 8 ways)
    #   fully associative   1    hit             hit  (11 lines < 64)
    #
    # The conflicting lines are read through a computed pointer (a3), so they
    # are not stack-class accesses themselves. Both stores are first touches:
    # L1 miss and L2 miss under every organisation. sp is aligned to 4 KiB so
    # the set of every line is fixed.
    .text
    .globl _start
    .type _start, @function

_start:
    li      t6, -4096
    and     sp, sp, t6
    li      t6, 8192
    sub     sp, sp, t6
    li      a0, 2
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(2, 0)

    li      t0, 1               # pair A, slot sp+0
spill_store_a:
    sd      t0, 0(sp)
    li      t1, 4096
    add     a3, sp, t1
    ld      t2, 0(a3)           # A+4096: same set under DM and 8-way
spill_load_a:
    ld      t3, 0(sp)

    li      t0, 2               # pair B, slot sp+64
spill_store_b:
    sd      t0, 64(sp)
    addi    a3, sp, 64
    li      t4, 8
1:  addi    a3, a3, 512         # B+512*i: B's set in the 8-set L1D
    ld      t2, 0(a3)
    addi    t4, t4, -1
    bnez    t4, 1b
spill_load_b:
    ld      t3, 64(sp)

    li      a0, 2
    li      a1, 0
    .long   0xb600007b          # m5_work_end(2, 0)
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
