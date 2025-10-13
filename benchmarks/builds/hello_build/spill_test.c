/*
 * Controlled Spill Test - Manual verification of spill detection
 *
 * This program intentionally creates known register spills to verify
 * the spill detector's accuracy.
 */

#include <stdint.h>
#include <stdio.h>

#include "gem5/m5ops.h"

// Test 1: Simple known spill pattern
void test_simple_spill() {
    volatile uint64_t stack_var = 0xDEADBEEF;
    uint64_t result;

    printf("Test 1: Simple spill (1 expected spill)\n");

    // Store to stack (spill)
    stack_var = 0x1234567890ABCDEF;

    // Some operations to create distance
    volatile int dummy = 0;
    for (int i = 0; i < 10; i++) {
        dummy += i;
    }

    // Load from stack (reload)
    result = stack_var;

    printf("  Result: 0x%lx (expected: 0x1234567890ABCDEF)\n", result);
}

// Test 2: Multiple consecutive spills
void test_multiple_spills() {
    volatile uint64_t var1 = 1;
    volatile uint64_t var2 = 2;
    volatile uint64_t var3 = 3;
    volatile uint64_t var4 = 4;
    volatile uint64_t var5 = 5;

    printf("Test 2: Multiple spills (5 expected spills)\n");

    // Force spills by storing multiple values
    var1 = 0xAAAAAAAAAAAAAAAA;
    var2 = 0xBBBBBBBBBBBBBBBB;
    var3 = 0xCCCCCCCCCCCCCCCC;
    var4 = 0xDDDDDDDDDDDDDDDD;
    var5 = 0xEEEEEEEEEEEEEEEE;

    // Dummy work
    volatile int dummy = 0;
    for (int i = 0; i < 5; i++) {
        dummy += i;
    }

    // Reload all (should detect 5 spills)
    uint64_t r1 = var1;
    uint64_t r2 = var2;
    uint64_t r3 = var3;
    uint64_t r4 = var4;
    uint64_t r5 = var5;

    printf("  Results: 0x%lx, 0x%lx, 0x%lx, 0x%lx, 0x%lx\n",
           r1, r2, r3, r4, r5);
}

// Test 3: Inline assembly with explicit spill
void test_explicit_asm_spill() {
    uint64_t value = 0x0FEDCBA987654321;
    uint64_t result;

    printf("Test 3: Explicit assembly spill (1 expected spill)\n");

    __asm__ volatile (
        // Store value to stack (explicit spill)
        "movq %1, -8(%%rsp)\n\t"

        // Some nop operations to create distance
        "nop\n\t"
        "nop\n\t"
        "nop\n\t"
        "nop\n\t"
        "nop\n\t"

        // Load value back from stack (reload)
        "movq -8(%%rsp), %0\n\t"

        : "=r" (result)
        : "r" (value)
        : "memory"
    );

    printf("  Result: 0x%lx (expected: 0x0FEDCBA987654321)\n", result);
}

// Test 4: Loop with repeated spills
void test_loop_spills() {
    printf("Test 4: Loop spills (10 expected spills)\n");

    uint64_t sum = 0;

    for (int i = 0; i < 10; i++) {
        volatile uint64_t temp = i * 123456;

        // Dummy work
        volatile int dummy = temp % 7;

        // Reload (creates spill pattern)
        sum += temp;
    }

    printf("  Sum: %lu\n", sum);
}

// Test 5: Known exact count with assembly
void test_exact_count_asm() {
    printf("Test 5: Exact count test (3 expected spills)\n");

    uint64_t val1 = 0x1111111111111111;
    uint64_t val2 = 0x2222222222222222;
    uint64_t val3 = 0x3333333333333333;
    uint64_t r1, r2, r3;

    __asm__ volatile (
        // Spill #1: Store val1
        "movq %3, -8(%%rsp)\n\t"

        // Spill #2: Store val2
        "movq %4, -16(%%rsp)\n\t"

        // Spill #3: Store val3
        "movq %5, -24(%%rsp)\n\t"

        // Some operations
        "nop\n\t"
        "nop\n\t"
        "nop\n\t"

        // Reload #1
        "movq -8(%%rsp), %0\n\t"

        // Reload #2
        "movq -16(%%rsp), %1\n\t"

        // Reload #3
        "movq -24(%%rsp), %2\n\t"

        : "=r" (r1), "=r" (r2), "=r" (r3)
        : "r" (val1), "r" (val2), "r" (val3)
        : "memory"
    );

    printf("  Results: 0x%lx, 0x%lx, 0x%lx\n", r1, r2, r3);
}

int main() {
    printf("==============================================\n");
    printf("Register Spill Detection Verification Test\n");
    printf("==============================================\n\n");

    // Start gem5 ROI (Region of Interest)
    printf("Starting ROI for spill detection...\n\n");
    m5_work_begin(0, 0);

    // Run tests
    test_simple_spill();
    printf("\n");

    test_multiple_spills();
    printf("\n");

    test_explicit_asm_spill();
    printf("\n");

    test_loop_spills();
    printf("\n");

    test_exact_count_asm();
    printf("\n");

    // End gem5 ROI
    m5_work_end(0, 0);
    printf("\n==============================================\n");
    printf("ROI ended. Check m5out/x86_spill_stats.txt\n");
    printf("Expected total: ~20 spills\n");
    printf("==============================================\n");

    return 0;
}
