.text
.globl _start

_start:
    # Extensive test with more instructions
    # =====================================
    
    # Loop counter
    li t6, 10          # Loop 10 times
    li t5, 0           # Counter
    
main_loop:
    # Increment counter
    addi t5, t5, 1
    
    # Test 1: SFP operations
    li a0, 0x1000
    add a0, a0, t5     # Make address unique per iteration
    .word 0x000545AB   # sfk_setsfp rd=a1, rs1=a0
    
    # Verify result
    li t0, 0x1000
    add t0, t0, t5
    bne a1, t0, test_failed
    
    # Increment SFP
    .word 0x100055AB   # sfk_incsfp rd=a1, imm=0x100
    
    # Test 2: Multiple spill/fill operations
    li s0, 0x2000
    sll t1, t5, 3      # t1 = t5 * 8 (unique offset per iteration)
    add s0, s0, t1     # Unique address per iteration
    
    # Prepare test data (more complex calculations)
    li s1, 0xDEAD
    sll s1, s1, 16
    addi s1, s1, 0x7EF  # 0xBEEF = 0x7EF + 0x400
    addi s1, s1, 0x400
    add s1, s1, t5     # Make data unique per iteration
    
    li s2, 0xCAFE
    sll s2, s2, 16
    addi s2, s2, 0x2BE  # 0xBABE = 0x2BE + 0x800
    li t1, 0x800
    add s2, s2, t1
    sub s2, s2, t5     # Make data unique per iteration
    
    # Multiple arithmetic operations
    add s3, s1, s2
    sub s4, s1, s2
    and s5, s1, s2
    or s6, s1, s2
    xor s7, s1, s2
    
    # Spill operations
    mv a0, s0
    mv a1, s3
    .word 0x00B5002B   # sfk_spill rs1=a0, rs2=a1, offset=0
    
    addi a0, s0, 8
    mv a1, s4
    .word 0x00B5002B   # sfk_spill rs1=a0, rs2=a1, offset=0
    
    addi a0, s0, 16
    mv a1, s5
    .word 0x00B5002B   # sfk_spill rs1=a0, rs2=a1, offset=0
    
    # Clear registers with more operations
    li a1, 0
    li a2, 0
    li a3, 0
    add a1, a1, a2     # Some dummy operations
    or a2, a2, a3
    and a3, a1, a2
    
    # Fill operations
    mv a0, s0
    .word 0x000515AB   # sfk_fill rd=a1, rs1=a0, offset=0
    bne a1, s3, test_failed
    
    addi a0, s0, 8
    .word 0x0005162B   # sfk_fill rd=a2, rs1=a0, offset=0
    bne a2, s4, test_failed
    
    addi a0, s0, 16
    .word 0x000535AB   # sfk_fill rd=a3, rs1=a0, offset=0
    bne a3, s5, test_failed
    
    # Test 3: Kill operation
    mv a0, s0
    .word 0x0005202B   # sfk_kill rs1=a0, offset=0
    
    # Verify kill worked
    .word 0x000515AB   # sfk_fill rd=a1, rs1=a0, offset=0
    bnez a1, test_failed
    
    # More arithmetic for instruction count (no multiply/divide)
    add t2, t5, t5     # t2 = t5 * 2
    add t3, t2, t2     # t3 = t5 * 4
    add t4, t3, t2     # t4 = t5 * 6
    sub t2, t4, t5     # t2 = t5 * 5
    
    # Loop condition check
    blt t5, t6, main_loop
    
    # Success path with more instructions
    li a0, 0
    li t0, 42
    add a0, a0, t0
    sub a0, a0, t0
    j exit

test_failed:
    li a0, 1
    li t0, 100
    add a0, a0, t0
    sub a0, a0, t0

exit:
    li a7, 93
    ecall
