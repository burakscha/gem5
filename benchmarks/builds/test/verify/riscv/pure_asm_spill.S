# Pure Assembly Spill Test - Exactly 9 spills, no C code
# Uses gem5 m5op instructions properly
# RISC-V 64-bit version

#include <gem5/asm/generic/m5ops.h>

.section .text
.global main

main:
    # Adjust stack pointer
    addi sp, sp, -80            # Allocate 80 bytes on stack

    # Call m5_work_begin(0, 0)
    li a0, 0                    # arg0 = 0
    li a1, 0                    # arg1 = 0
    call m5_work_begin

    # ===== TEST 1: 1 SPILL =====
    li t0, 0xAAAAAAAAAAAAAAAA
    sd t0, 0(sp)                # STORE #1
    nop
    nop
    ld t1, 0(sp)                # LOAD #1 -> SPILL #1

    # ===== TEST 2: 3 SPILLS =====
    li t0, 0x1111111111111111
    sd t0, 8(sp)                # STORE #2
    li t1, 0x2222222222222222
    sd t1, 16(sp)               # STORE #3
    li t2, 0x3333333333333333
    sd t2, 24(sp)               # STORE #4
    nop
    ld t3, 8(sp)                # LOAD #2 -> SPILL #2
    ld t4, 16(sp)               # LOAD #3 -> SPILL #3
    ld t5, 24(sp)               # LOAD #4 -> SPILL #4

    # ===== TEST 3: 5 SPILLS =====
    li t0, 0xAAAAAAAAAAAAAAAA
    sd t0, 32(sp)               # STORE #5
    li t1, 0xBBBBBBBBBBBBBBBB
    sd t1, 40(sp)               # STORE #6
    li t2, 0xCCCCCCCCCCCCCCCC
    sd t2, 48(sp)               # STORE #7
    li t3, 0xDDDDDDDDDDDDDDDD
    sd t3, 56(sp)               # STORE #8
    li t4, 0xEEEEEEEEEEEEEEEE
    sd t4, 64(sp)               # STORE #9
    nop
    ld t5, 32(sp)               # LOAD #5 -> SPILL #5
    ld t6, 40(sp)               # LOAD #6 -> SPILL #6
    ld a2, 48(sp)               # LOAD #7 -> SPILL #7
    ld a3, 56(sp)               # LOAD #8 -> SPILL #8
    ld a4, 64(sp)               # LOAD #9 -> SPILL #9

    # Call m5_work_end(0, 0)
    li a0, 0                    # arg0 = 0
    li a1, 0                    # arg1 = 0
    call m5_work_end

    # Restore stack and exit
    addi sp, sp, 80             # Deallocate stack
    li a7, 93                   # exit syscall number for RISC-V
    li a0, 0                    # status 0
    ecall
