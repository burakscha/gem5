# Pure Assembly Spill Test - Exactly 9 spills, no C code
# Uses gem5 m5op instructions properly

#include <gem5/asm/generic/m5ops.h>

.section .text
.global main

main:
    # Call m5_work_begin(0, 0)
    xor %rdi, %rdi              # arg0 = 0
    xor %rsi, %rsi              # arg1 = 0
    call m5_work_begin

    # ===== TEST 1: 1 SPILL =====
    mov $0xAAAAAAAAAAAAAAAA, %rax
    mov %rax, -8(%rsp)          # STORE #1
    nop
    nop
    mov -8(%rsp), %rbx          # LOAD #1 -> SPILL #1

    # ===== TEST 2: 3 SPILLS =====
    mov $0x1111111111111111, %rax
    mov %rax, -16(%rsp)         # STORE #2
    mov $0x2222222222222222, %rcx
    mov %rcx, -24(%rsp)         # STORE #3
    mov $0x3333333333333333, %rdx
    mov %rdx, -32(%rsp)         # STORE #4
    nop
    mov -16(%rsp), %r8          # LOAD #2 -> SPILL #2
    mov -24(%rsp), %r9          # LOAD #3 -> SPILL #3
    mov -32(%rsp), %r10         # LOAD #4 -> SPILL #4

    # ===== TEST 3: 5 SPILLS =====
    mov $0xAAAAAAAAAAAAAAAA, %rax
    mov %rax, -40(%rsp)         # STORE #5
    mov $0xBBBBBBBBBBBBBBBB, %rbx
    mov %rbx, -48(%rsp)         # STORE #6
    mov $0xCCCCCCCCCCCCCCCC, %rcx
    mov %rcx, -56(%rsp)         # STORE #7
    mov $0xDDDDDDDDDDDDDDDD, %rdx
    mov %rdx, -64(%rsp)         # STORE #8
    mov $0xEEEEEEEEEEEEEEEE, %rsi
    mov %rsi, -72(%rsp)         # STORE #9
    nop
    mov -40(%rsp), %r11         # LOAD #5 -> SPILL #5
    mov -48(%rsp), %r12         # LOAD #6 -> SPILL #6
    mov -56(%rsp), %r13         # LOAD #7 -> SPILL #7
    mov -64(%rsp), %r14         # LOAD #8 -> SPILL #8
    mov -72(%rsp), %r15         # LOAD #9 -> SPILL #9

    # Call m5_work_end(0, 0)
    xor %rdi, %rdi              # arg0 = 0
    xor %rsi, %rsi              # arg1 = 0
    call m5_work_end

    # Exit syscall
    mov $60, %rax               # exit
    xor %rdi, %rdi              # status 0
    syscall
