    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    li      t0, 10
    sd      t0, 0(sp)
    ld      t1, 0(sp)

    li      a0, 9
    li      a1, 0
    .long   0xb400007b
    li      t0, 20
    sd      t0, 8(sp)
    ld      t1, 8(sp)
    li      a0, 9
    li      a1, 0
    .long   0xb600007b

    li      t0, 30
    sd      t0, 16(sp)
    ld      t1, 16(sp)

    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
