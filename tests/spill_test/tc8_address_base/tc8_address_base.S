    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 8
    li      a1, 0
    .long   0xb400007b

    # s0 is the value operand, not the effective-address base. This store
    # must remain non-spill because the base is the computed pointer a3.
    addi    a3, sp, 16
    li      s0, 789
    sd      s0, 0(a3)
    ld      t0, 0(a3)

    li      a0, 8
    li      a1, 0
    .long   0xb600007b
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
