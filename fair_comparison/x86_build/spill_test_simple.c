#include <stdio.h>

// Simple register-intensive function to trigger spills
void register_pressure_function() {
    // Force many register uses simultaneously to cause spills
    volatile int r1 = 1, r2 = 2, r3 = 3, r4 = 4;
    volatile int r5 = 5, r6 = 6, r7 = 7, r8 = 8;
    volatile int r9 = 9, r10 = 10, r11 = 11, r12 = 12;
    volatile int r13 = 13, r14 = 14, r15 = 15, r16 = 16;
    volatile int r17 = 17, r18 = 18, r19 = 19, r20 = 20;
    
    // Perform operations that require all these registers
    for (volatile int i = 0; i < 1000; i++) {
        r1 += r2 * r3 + r4;
        r5 += r6 * r7 + r8;
        r9 += r10 * r11 + r12;
        r13 += r14 * r15 + r16;
        r17 += r18 * r19 + r20;
        
        r2 ^= r1 + r5;
        r6 ^= r9 + r13;
        r10 ^= r17 + r1;
        r14 ^= r5 + r9;
        r18 ^= r13 + r17;
    }
    
    // Use results to prevent optimization
    printf("Computation result: %d\n", (r1 + r5 + r9 + r13 + r17) % 1000);
}

int main(int argc, char* argv[]) {
    printf("Starting register spill test...\n");
    
    register_pressure_function();
    
    printf("Register spill test completed!\n");
    return 0;
}
