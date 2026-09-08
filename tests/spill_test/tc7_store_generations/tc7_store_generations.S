    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 7
    li      a1, 0
    .long   0xb400007b

    li      t0, 111
    sd      t0, 0(sp)
    ld      t1, 0(sp)
    li      t0, 222
    sd      t0, 0(sp)
    ld      t2, 0(sp)

    li      a0, 7
    li      a1, 0
    .long   0xb600007b
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
