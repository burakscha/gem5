    # A store to a stack page touched for the first time (metric schema 10).
    # gem5 maps only the stack pages the loader wrote, and the stack check
    # is stackMin <= address < stackBase. The first access to a deeper page
    # lies below stackMin: its translation returns a page fault, the
    # detector discards that attempt, the fault handler grows the stack
    # (MemState::fixupFault: "Increasing stack size by one page"), and the
    # store re-executes, now inside [stackMin, stackBase). It must count
    # once: not zero times (missed) and not twice (the faulted attempt).
    #
    # sp moves 8 KiB down, at least one page below every mapped page. The
    # first sd touches the new page, the second one an already grown page;
    # both are read back.
    #
    # Expected ROI: 2 loads, 2 stores; 2 spill stores, 2 spill events,
    # 2 spill loads. run_tests.py also checks gem5's stack growth message.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    li      a0, 7
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(7, 0)

    li      t0, 7
    li      t1, 8192
    sub     sp, sp, t1
    sd      t0, 0(sp)           # first touch of the page
    ld      t2, 0(sp)
    sd      t0, 8(sp)
    ld      t2, 8(sp)
    add     sp, sp, t1

    li      a0, 7
    li      a1, 0
    .long   0xb600007b          # m5_work_end(7, 0)

    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
