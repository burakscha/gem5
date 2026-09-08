    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 6
    li      a1, 0
    .long   0xb400007b

    li      t0, 456
    sd      t0, 8(sp)

    li      a0, 6
    li      a1, 0
    .long   0xb600007b
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
