    # Cross-checks the SpillDetector ROI against gem5's own ROI handling.
    # The ROI is marked with gem5's work items, m5_work_begin(9, 0) and
    # m5_work_end(9, 0). Hand counts:
    #   pre-ROI   7 insts (1 load, 2 stores) + the work_begin marker
    #   ROI      19 insts (4 loads, 4 stores: four sd/ld pairs on 16(sp))
    #   post-ROI  6 committed insts (1 load, 2 stores) + a faulting ecall
    # The detector excludes both markers, so roi_total_insts = 19. gem5's ROI
    # statistics block also holds the work_end marker, so it reports 20.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      t0, 1
    sd      t0, 0(sp)
    sd      t0, 8(sp)
    ld      t1, 0(sp)
    li      a0, 9
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(9, 0)

    li      t2, 4
1:  sd      t2, 16(sp)
    ld      t3, 16(sp)
    addi    t2, t2, -1
    bnez    t2, 1b
    li      a0, 9
    li      a1, 0
    .long   0xb600007b          # m5_work_end(9, 0)

    ld      t4, 0(sp)
    sd      t4, 32(sp)
    sd      t4, 40(sp)
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
