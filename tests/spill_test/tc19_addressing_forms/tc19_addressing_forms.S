    # Base-register recognition for every store/reload form a rv64gc binary
    # uses for stack slots. SPEC is built with -march=rv64gc, so most spill
    # and callee-save code is compressed (c.sdsp/c.ldsp, c.fsdsp/c.fldsp, ...),
    # and gem5 decodes those with different operand layouts than the 32-bit
    # forms. Each form gets its own ROI (workid = form number) holding one
    # store and its reload; every ROI must report one other_stack pair.
    #
    #   1 c.sdsp/c.ldsp     2 c.swsp/c.lwsp     3 c.fsdsp/c.fldsp
    #   4 c.sd/c.ld (s0)    5 c.fsd/c.fld (s0)  6 sd/ld (32-bit)
    #   7 fsd/fld (32-bit)  8 fsw/flw           9 sh/lh          10 sb/lbu
    .option rvc                 # compressed forms on
    .text
    .globl _start
_start:
    addi sp, sp, -256
    mv s0, sp
    li t0, 5
    fmv.d.x fs0, t0
    li a0, 1
    li a1, 0
    .long 0xb400007b
    c.sdsp s1, 8(sp)
    c.ldsp s1, 8(sp)
    li a0, 1
    li a1, 0
    .long 0xb600007b
    li a0, 2
    li a1, 0
    .long 0xb400007b
    c.swsp s1, 16(sp)
    c.lwsp s1, 16(sp)
    li a0, 2
    li a1, 0
    .long 0xb600007b
    li a0, 3
    li a1, 0
    .long 0xb400007b
    c.fsdsp fs0, 24(sp)
    c.fldsp fs0, 24(sp)
    li a0, 3
    li a1, 0
    .long 0xb600007b
    li a0, 4
    li a1, 0
    .long 0xb400007b
    c.sd a0, 32(s0)
    c.ld a0, 32(s0)
    li a0, 4
    li a1, 0
    .long 0xb600007b
    li a0, 5
    li a1, 0
    .long 0xb400007b
    c.fsd fs1, 40(s0)
    c.fld fs1, 40(s0)
    li a0, 5
    li a1, 0
    .long 0xb600007b
    li a0, 6
    li a1, 0
    .long 0xb400007b
    .option norvc
    sd s1, 48(sp)
    ld s1, 48(sp)
    .option rvc                 # compressed forms on
    li a0, 6
    li a1, 0
    .long 0xb600007b
    li a0, 7
    li a1, 0
    .long 0xb400007b
    .option norvc
    fsd fs0, 56(sp)
    fld fs0, 56(sp)
    .option rvc                 # compressed forms on
    li a0, 7
    li a1, 0
    .long 0xb600007b
    li a0, 8
    li a1, 0
    .long 0xb400007b
    fsw fs0, 64(sp)
    flw fs0, 64(sp)
    li a0, 8
    li a1, 0
    .long 0xb600007b
    li a0, 9
    li a1, 0
    .long 0xb400007b
    sh s1, 72(sp)
    lh s1, 72(sp)
    li a0, 9
    li a1, 0
    .long 0xb600007b
    li a0, 10
    li a1, 0
    .long 0xb400007b
    sb s1, 80(sp)
    lbu s1, 80(sp)
    li a0, 10
    li a1, 0
    .long 0xb600007b
    addi sp, sp, 256
    li a7, 93
    li a0, 0
    ecall
