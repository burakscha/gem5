/*
 * Fair Cross-Architecture Register Spill Test
 * ===========================================
 * 
 * This unified test program is designed for IDENTICAL compilation and execution
 * across X86 and RISC-V architectures to enable fair register spill comparison.
 * 
 * Key Design Principles:
 * - Architecture-agnostic C code (no stdio.h dependency)
 * - High register pressure with 25 variables
 * - Complex arithmetic to prevent optimization
 * - Identical compilation: -O0 for both architectures
 * - Controlled iteration count for measurable results
 * 
 * Compilation:
 * X86:    gcc -O0 -o x86_unified_test unified_spill_test.c
 * RISC-V: riscv64-elf-gcc -O0 -nostdlib -nostartfiles -o riscv_unified_test unified_spill_test.c
 */

int main() {
    // 25 variables for maximum register pressure on both architectures
    int a1 = 1, a2 = 2, a3 = 3, a4 = 4, a5 = 5;
    int b1 = 6, b2 = 7, b3 = 8, b4 = 9, b5 = 10;
    int c1 = 11, c2 = 12, c3 = 13, c4 = 14, c5 = 15;
    int d1 = 16, d2 = 17, d3 = 18, d4 = 19, d5 = 20;
    int e1 = 21, e2 = 22, e3 = 23, e4 = 24, e5 = 25;
    
    // Optimal iteration counts for fair comparison
    // 150 iterations: enough to generate measurable spills without excessive runtime
    for (int iter = 0; iter < 150; iter++) {
        // Complex arithmetic patterns to force register spilling
        // Each line creates dependencies that require temporary storage
        
        // Round 1: Basic arithmetic with cross-dependencies
        a1 = a1 + a2 * a3 - a4 + a5;
        b1 = b1 * b2 + b3 - b4 * b5;
        c1 = c1 + c2 - c3 * c4 + c5;
        d1 = d1 * d2 - d3 + d4 * d5;
        e1 = e1 + e2 * e3 - e4 + e5;
        
        // Round 2: Cross-group dependencies
        a2 = a2 + b1 * c1 - d1 + e1;
        b2 = b2 * a1 + c2 - d2 * e2;
        c2 = c2 + a3 - b3 * d3 + e3;
        d2 = d2 * b4 - c4 + a4 * e4;
        e2 = e2 + c5 * d5 - a5 + b5;
        
        // Round 3: Complex expressions with multiple operations
        a3 = (a1 + a2) * (b1 - b2) + (c1 * c2) - (d1 + d2);
        b3 = (a3 - a4) + (b4 * b5) - (c3 + c4) * (d3 - d4);
        c3 = (a5 + b1) * (c5 - d1) + (e1 * e2) - (a2 + b3);
        d3 = (b2 - c1) + (d4 * d5) - (e3 + e4) * (a1 - c2);
        e3 = (c4 + d2) * (e5 - a3) + (b4 * c5) - (d1 + a4);
        
        // Round 4: Maximum complexity operations
        a4 = a1 * a2 + a3 * a4 - a5 * b1 + b2 * b3 - b4 * b5;
        b4 = c1 * c2 + c3 * c4 - c5 * d1 + d2 * d3 - d4 * d5;
        c4 = e1 * e2 + e3 * e4 - e5 * a1 + a2 * a3 - a4 * a5;
        d4 = b1 * b2 + b3 * b4 - b5 * c1 + c2 * c3 - c4 * c5;
        e4 = d1 * d2 + d3 * d4 - d5 * e1 + e2 * e3 - e4 * e5;
        
        // Round 5: Final complex assignments
        a5 = (a1 + a2 + a3) * (b1 + b2) - (c1 * c2 * c3) + (d1 - d2);
        b5 = (a4 + a5 + b3) * (c4 + c5) - (d3 * d4 * d5) + (e1 - e2);
        c5 = (b4 + b5 + c1) * (d2 + e3) - (a1 * a2 * a3) + (b1 - c2);
        d5 = (c3 + c4 + d1) * (e4 + e5) - (b2 * b3 * b4) + (a4 - d2);
        e5 = (d3 + d4 + e1) * (a5 + b1) - (c2 * c3 * c4) + (d5 - a1);
    }
    
    // Create a simple checksum to prevent optimization and provide return value
    int checksum = a1 + a2 + a3 + a4 + a5 + b1 + b2 + b3 + b4 + b5 +
                   c1 + c2 + c3 + c4 + c5 + d1 + d2 + d3 + d4 + d5 +
                   e1 + e2 + e3 + e4 + e5;
    
    // Architecture-specific exit system calls for bare metal
#ifdef __riscv
    // RISC-V exit system call
    asm volatile("li a7, 93\n\t"           // sys_exit syscall number for RISC-V
                 "mv a0, %0\n\t"           // exit code (first argument)
                 "ecall"                   // RISC-V system call
                 :
                 : "r"((long)(checksum & 0xFF))
                 : "a0", "a7");
#else
    // X86-64 exit system call
    asm volatile("movq $60, %%rax\n\t"      // sys_exit
                 "movq %0, %%rdi\n\t"        // exit code
                 "syscall"
                 :
                 : "r"((long)(checksum & 0xFF))
                 : "rax", "rdi");
#endif
    
    return checksum & 0xFF; // Fallback return
}
