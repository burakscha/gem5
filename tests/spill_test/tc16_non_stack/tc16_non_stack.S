    # Store -> load reuse on a NON-stack (.bss) address.
    # Same address, same width, store first: it would pair if the address were
    # on the stack, but S2/L2 (stack region) must reject it.
    # Expected ROI: 1 load, 1 store, every spill and diag counter 0.
    .text
    .globl _start
    .type _start, @function

_start:
    li      a0, 0
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(0, 0)

    lla     a3, heap_slot
    li      t0, 5
    sd      t0, 0(a3)
    ld      t1, 0(a3)

    li      a0, 0
    li      a1, 0
    .long   0xb600007b          # m5_work_end(0, 0)

    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start

    .bss
    .balign 64
heap_slot:
    .zero   64
