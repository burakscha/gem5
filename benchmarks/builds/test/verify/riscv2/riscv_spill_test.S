.section .text
.global main

main:
    addi sp, sp, -56

    # Statistics'i sıfırla
    li a0, 0
    li a1, 0
    call m5_reset_stats

    # ========== ROI START ==========
    li a0, 0
    li a1, 0
    call m5_work_begin  # ROI başlangıcı işaretle
    
    # --- Spill Pair 1 ---
    addi t0, zero, 1
    sd t0, 0(sp)
    ld t1, 0(sp)

    # --- Spill Pair 2 ---
    addi t0, zero, 2
    sd t0, 8(sp)
    ld t1, 8(sp)

    # --- Spill Pair 3 ---
    addi t0, zero, 3
    sd t0, 16(sp)
    ld t1, 16(sp)

    # --- Spill Pair 4 ---
    addi t0, zero, 4
    sd t0, 24(sp)
    ld t1, 24(sp)

    # --- Spill Pair 5 ---
    addi t0, zero, 5
    sd t0, 32(sp)
    ld t1, 32(sp)

    # --- Spill Pair 6 ---
    addi t0, zero, 6
    sd t0, 40(sp)
    ld t1, 40(sp)

    # --- Spill Pair 7 ---
    sd t0, 48(sp)
    ld t1, 48(sp)

    li a0, 0
    li a1, 0
    call m5_work_end    # ROI sonu işaretle
    # ========== ROI END ==========

    # Statistics'i dump et
    li a0, 0
    li a1, 0
    call m5_dump_stats

    addi sp, sp, 56
    li a7, 93
    li a0, 0
    ecall