    # One spill pair separated by a 120,000-instruction delay loop
    # (about 120 us of simulated time at the default 2 GHz clock).
    # The retired 50 us tick window would have dropped this pair; the detector
    # must still pair it. Store-to-reload distance is 120,003 committed
    # instructions (`li t2, 60000` is two), reuse histogram bucket 16.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -16
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(0, 0)

    li      t0, 7
    sd      t0, 0(sp)
    li      t2, 60000
1:  addi    t2, t2, -1
    bnez    t2, 1b
    ld      t1, 0(sp)

    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end(0, 0)

    addi    sp, sp, 16
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
