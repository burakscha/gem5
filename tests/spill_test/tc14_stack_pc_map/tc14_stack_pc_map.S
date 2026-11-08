    # Stack PC map classes (metric schema 8).
    # The test runner builds the map from the labels in this file:
    #   spill_store_* / spill_load_*  -> spill_store / spill_load records
    #   csave_store_*                 -> csave_store records
    # (scripts/build_stack_pc_map.py takes the same records from GCC -dP and
    # from the binary's CFI.) Unlabelled SP-relative pairs stay other_stack.
    #
    #   A  unlabelled store + reload            -> other_stack
    #   B  spill store + spill load             -> spill
    #   C  csave store + (unlabelled) restore   -> csave
    #   D  spill store + unmapped reload        -> spill, and
    #                                              diag_spill_reload_unmapped
    #   E  unlabelled store + mapped spill load -> other_stack, and
    #                                              diag_spill_load_pc_other_store
    #
    # Expected ROI: 5 loads, 5 stores; spill 2/2, csave 1/1, other_stack 2/2.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 14
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(14, 0)

    li      t0, 100             # A
    sd      t0, 0(sp)
    ld      t1, 0(sp)

    li      t0, 200             # B
spill_store_b:
    sd      t0, 8(sp)
spill_load_b:
    ld      t2, 8(sp)

csave_store_c:                  # C
    sd      s1, 16(sp)
    ld      s1, 16(sp)

spill_store_d:                  # D
    sd      t0, 24(sp)
    ld      t3, 24(sp)

    sd      t0, 32(sp)          # E
spill_load_e:
    ld      t4, 32(sp)

    li      a0, 14
    li      a1, 0
    .long   0xb600007b          # m5_work_end(14, 0)
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
