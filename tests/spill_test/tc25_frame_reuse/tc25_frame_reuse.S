    # Stack frames reused by later calls (metric schema 10). f, g and h each
    # allocate a 32-byte frame at the same place, so their 8(sp) is the same
    # address. A store stays in the store table until a newer store
    # overwrites it; popping its frame does not end it.
    #
    #   f      stores F1 at the slot and returns without reading it
    #   g      stores G at the slot and reads it back -> pair with G
    #          (the newest owner; F1 is never read back)
    #   f      stores F2 at the slot, returns without reading it
    #   h      reads the slot WITHOUT writing it first (an uninitialized
    #          read) -> pairs with F2, whose frame was popped. KNOWN
    #          LIMITATION, asserted so that it cannot change unnoticed: only
    #          a frame-lifetime rule (drop the stores below sp when sp rises)
    #          would refuse this pair. The stack-release diagnostic marks it:
    #          diag_load_after_stack_release = 1 and, as it is F2's first
    #          reload, diag_event_after_stack_release = 1. g's
    #          and k's pairs are not marked (G was written after the release,
    #          A's frame was never released).
    #   _start stores A in its own frame (an outgoing stack argument) and
    #          calls k, which reads it through its own sp -> pair with A
    #          (A's frame is alive)
    #
    # Expected ROI: 3 loads, 4 stores; 4 spill stores, 3 spill events (G, F2,
    # A), 3 spill loads. F1 is the one spill store never read back.
    .text
    .globl _start
    .type _start, @function

_start:
    addi    sp, sp, -64

    li      a0, 6
    li      a1, 0
    .long   0xb400007b          # m5_work_begin(6, 0)

    li      t0, 7
    call    f_store             # F1
    call    g_store_load        # G, read back
    call    f_store             # F2
    call    h_load              # reads F2's slot, F2's frame is gone

    sd      t0, 0(sp)           # A
    call    k_load_arg          # reads A

    li      a0, 6
    li      a1, 0
    .long   0xb600007b          # m5_work_end(6, 0)

    addi    sp, sp, 64
    li      a7, 93
    li      a0, 0
    ecall

f_store:
    addi    sp, sp, -32
    sd      t0, 8(sp)
    addi    sp, sp, 32
    ret

g_store_load:
    addi    sp, sp, -32
    sd      t0, 8(sp)
    ld      t1, 8(sp)
    addi    sp, sp, 32
    ret

h_load:
    addi    sp, sp, -32
    ld      t2, 8(sp)
    addi    sp, sp, 32
    ret

k_load_arg:
    addi    sp, sp, -16
    ld      t3, 16(sp)          # the caller's 0(sp)
    addi    sp, sp, 16
    ret

    .size _start, .-_start
