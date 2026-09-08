    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 14
    li      a1, 0
    .long   0xb400007b

    # This pair looks like a spill to the heuristic, but is deliberately not
    # present in the compiler map and must therefore be excluded in exact mode.
    li      t0, 100
excluded_store:
    sd      t0, 0(sp)
excluded_load:
    ld      t1, 0(sp)

    # Only this pair is compiler-labelled in the generated PC map.
    li      t0, 200
exact_store:
    sd      t0, 8(sp)
exact_load:
    ld      t2, 8(sp)

    li      a0, 14
    li      a1, 0
    .long   0xb600007b
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
