    # A SimPoint interval (metric schema 10). The run restores a checkpoint,
    # simulates the warmup, and the SpillDetector ROI is the interval after
    # it (configs/common/Simulation.py, restoreSimpointCheckpoint). Stores of
    # the warmup are not tracked: a reload of one inside the interval does
    # not pair.
    #
    # run_tests.py takes the checkpoint of interval 1 with interval length 40
    # and warmup 20, i.e. at instruction 20. AtomicSimpleCPU, which takes it,
    # services the instruction-count event at the start of its next tick and
    # still executes that instruction (atomic.cc), so the checkpoint lies
    # after instruction 21: the warmup is instructions 22-41 and the interval
    # 42-81, counted from the first instruction of _start. The program has no
    # ROI markers.
    #
    # Expected interval: 40 instructions, 3 loads, 2 stores; 2 spill stores,
    # 2 spill events, 2 spill loads. The restore run executes 60 instructions,
    # 3 loads, 4 stores, and exits at the end of the interval.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64         # 1
    li      t0, 5               # 2
    .rept 19
    nop                         # 3-21
    .endr

    # warmup
    sd      t0, 0(sp)           # 22  read back inside the interval
    sd      t0, 8(sp)           # 23  overwritten inside the interval
    .rept 18
    nop                         # 24-41
    .endr

    # interval; its first instruction must be counted
    sd      t0, 16(sp)          # 42
    ld      t1, 0(sp)           # 43  reads the store of 22: no pair
    ld      t2, 16(sp)          # 44  pair with 42
    sd      t0, 8(sp)           # 45  overwrites the store of 23
    ld      t3, 8(sp)           # 46  pair with 45
    .rept 35
    nop                         # 47-81
    .endr

    # not reached by the restore run
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
