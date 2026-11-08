    # Byte ownership (metric schema 10). Every byte belongs to the store that
    # wrote it last; a load reads back the owner of its start byte.
    #
    #   A  sd over [0, 8), then sw over [0, 4) and sw over [4, 8): no single
    #      newer store covers the sd, but every byte of it is overwritten.
    #      ld 0 pairs with the first sw and lw 4 with the second; the sd is
    #      never read back. (Pairing with the oldest covering store instead
    #      would make both loads read the sd: one event, not two.)
    #   B  the same value stored twice to one slot (a silent store): two
    #      stack stores; the reload pairs with the second, the first stays
    #      unpaired.
    #
    # Expected ROI: 3 loads, 5 stores; 5 spill stores, 3 spill events,
    # 3 spill loads.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    li      a0, 4
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(4, 0)

    li      t0, 7
    sd      t0, 0(sp)           # A
    sw      t0, 0(sp)
    sw      t0, 4(sp)
    ld      t1, 0(sp)           # first sw
    lw      t2, 4(sp)           # second sw

    sd      t0, 8(sp)           # B
    sd      t0, 8(sp)           # same value again
    ld      t3, 8(sp)           # second sd

    li      a0, 4
    li      a1, 0
    .long   0xb600007b          # m5_work_end(4, 0)

    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
