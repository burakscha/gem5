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

    # Same address but different widths is not a pair either.
    li      t1, 42
    sd      t1, 8(sp)
    lw      t2, 8(sp)

    li      a0, 10
    li      a1, 0
    .long   0xb600007b
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
