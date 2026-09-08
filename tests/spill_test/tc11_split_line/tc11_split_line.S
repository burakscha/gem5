    .text
    .globl _start
    .type _start, @function

_start:
    # Force a known 64-byte alignment, then keep the frame in mapped stack
    # space. An 8-byte access at +60 crosses exactly one line boundary.
    andi    sp, sp, -64
    addi    sp, sp, -128
    li      a0, 11
    li      a1, 0
    .long   0xb400007b

    li      t0, 987
    sd      t0, 60(sp)
    ld      t1, 60(sp)

    li      a0, 11
    li      a1, 0
    .long   0xb600007b
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
