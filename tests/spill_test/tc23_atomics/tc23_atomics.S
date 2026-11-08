    # Atomic memory operations (metric schema 10). LR/SC and AMOs are out of
    # scope: never stack stores or spill loads. A successful SC or an AMO
    # still owns the bytes it wrote, so a later load does not pair through it
    # with an older store; a failed SC wrote nothing and changes nothing.
    #
    #   A  sd, lr.d of it (not a spill load), sc.d succeeds: the ld after it
    #      reads the SC's value, not a spill load; the sd stays unpaired
    #   B  sd, sc.d without a reservation fails: the ld still reads the sd
    #      -> spill pair
    #   C  sd, amoadd.d on it: the ld after it is not a spill load
    #   D  sd, amoswap.w on its upper half: lw of the lower half -> spill
    #      pair with the sd; lw of the upper half is not a spill load
    #
    # The program exits with status 1 (failing the test) if an SC does not
    # end as expected. gem5 counts LR as a load and SC as a store, AMOs as
    # neither (they are atomic). Expected ROI: 6 loads, 6 stores; 4 stack
    # stores, 2 spill events, 2 spill loads.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    li      a0, 5
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(5, 0)

    li      t0, 7
    li      t2, 9

    sd      t0, 0(sp)           # A
    mv      a2, sp
    lr.d    t1, (a2)
    sc.d    t3, t2, (a2)        # t3 = 0: succeeded
    bnez    t3, fail
    ld      t4, 0(sp)

    sd      t0, 8(sp)           # B
    addi    a2, sp, 8
    sc.d    t3, t2, (a2)        # no reservation: t3 != 0, nothing written
    beqz    t3, fail
    ld      t4, 8(sp)

    sd      t0, 16(sp)          # C
    addi    a2, sp, 16
    amoadd.d t1, t2, (a2)
    ld      t4, 16(sp)

    sd      t0, 24(sp)          # D
    addi    a2, sp, 28
    amoswap.w t1, t2, (a2)
    lw      t4, 24(sp)
    lw      t5, 28(sp)

    li      a0, 5
    li      a1, 0
    .long   0xb600007b          # m5_work_end(5, 0)

    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

fail:
    li      a7, 93
    li      a0, 1
    ecall

    .size _start, .-_start
