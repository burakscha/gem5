    # Loads that do not read a stack store back (metric schema 9: a reload's
    # address must lie in [store address, store address + store size)).
    # Expected ROI: 3 loads, 3 stores, no pair.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 10
    li      a1, 0
    .long   0xb400007b

    # Load-before-store is not a store-to-reload pair.
    ld      t0, 0(sp)
    sd      t0, 0(sp)

    # A load at the store's end address reads the next byte, not the store:
    # the 4-byte store writes [8, 12), the load starts at 12.
    li      t1, 42
    sw      t1, 8(sp)
    lw      t2, 12(sp)

    # A load that starts below the store does not read it back either: the
    # store writes [24, 28), the load starts at 20.
    sw      t1, 24(sp)
    ld      t3, 20(sp)

    li      a0, 10
    li      a1, 0
    .long   0xb600007b
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
