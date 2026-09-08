    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -32
    li      t0, 321
    sd      t0, 0(sp)
    ld      t1, 0(sp)
    addi    sp, sp, 32
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
