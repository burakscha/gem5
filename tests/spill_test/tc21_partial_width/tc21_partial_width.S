    # Reloads narrower or wider than their store (metric schema 10). A load
    # reads a store back when its START address lies in the bytes the store
    # wrote, [store address, store address + store size); the newest store
    # owns a byte. The forms are the ones GCC emits for RISC-V spill code,
    # e.g. in x264 (pixel_hadamard_ac: two sw read by one ld;
    # x264_me_search_ref: sd read by lw/lh).
    #
    #   A  two 4-byte stores, one 8-byte load at the first one's address
    #      -> pairs with the first store only; the second stays unpaired
    #      although the load reads its bytes (start-address rule: the other
    #      owners of a load's bytes are not counted)
    #   B  8-byte store, 4-byte reload of its upper half          -> pair
    #   C  8-byte store, 2-byte reload at byte 6                  -> pair
    #   D  8-byte store, then a 4-byte store over its upper half: a reload
    #      of the upper half pairs with the newer store; a reload of the
    #      lower half still pairs with the older one, which keeps the bytes
    #      not overwritten
    #
    # Expected ROI: 5 loads, 6 stores; 6 spill stores, 5 spill events (one
    # store unpaired), 5 spill loads.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64
    li      a0, 2
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(2, 0)

    li      t0, 7               # A
spill_store_a1:
    sw      t0, 0(sp)
spill_store_a2:
    sw      t0, 4(sp)
spill_load_a:
    ld      t1, 0(sp)

spill_store_b:                  # B
    sd      t0, 8(sp)
spill_load_b:
    lw      t2, 12(sp)

spill_store_c:                  # C
    sd      t0, 16(sp)
spill_load_c:
    lh      t3, 22(sp)

spill_store_d:                  # D
    sd      t0, 24(sp)
    sw      t0, 28(sp)
    lw      t4, 28(sp)
spill_load_d:
    lw      t5, 24(sp)

    li      a0, 2
    li      a1, 0
    .long   0xb600007b          # m5_work_end(2, 0)
    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

    .size _start, .-_start
