/*
 * Register Spill Test Program
 *
 * This program is designed to force register spilling by using
 * more local variables than available registers.
 *
 * RISC-V has ~32 registers, but many are reserved.
 * Using 20+ local variables should trigger spills.
 *
 * Compile with: riscv64-linux-gnu-gcc -O0 -static spill_test.c -o
 * spill_test.riscv Note: -O0 disables optimization, making spills more
 * predictable
 */

#include <stdio.h>

// Function that uses many variables to force register spilling
int heavy_register_pressure(int input) {
  // Use many local variables to exceed register count
  int a1 = input + 1;
  int a2 = input + 2;
  int a3 = input + 3;
  int a4 = input + 4;
  int a5 = input + 5;
  int a6 = input + 6;
  int a7 = input + 7;
  int a8 = input + 8;
  int a9 = input + 9;
  int a10 = input + 10;
  int a11 = input + 11;
  int a12 = input + 12;
  int a13 = input + 13;
  int a14 = input + 14;
  int a15 = input + 15;
  int a16 = input + 16;
  int a17 = input + 17;
  int a18 = input + 18;
  int a19 = input + 19;
  int a20 = input + 20;

  // Use all variables to prevent optimization from eliminating them
  int sum = a1 + a2 + a3 + a4 + a5;
  sum += a6 + a7 + a8 + a9 + a10;
  sum += a11 + a12 + a13 + a14 + a15;
  sum += a16 + a17 + a18 + a19 + a20;

  // Additional computation to keep variables live
  int product = a1 * a2;
  product += a3 * a4;
  product += a5 * a6;
  product += a7 * a8;
  product += a9 * a10;
  product += a11 * a12;
  product += a13 * a14;
  product += a15 * a16;
  product += a17 * a18;
  product += a19 * a20;

  return sum + product;
}

// Recursive function that creates stack frames
int recursive_spill(int n, int acc) {
  if (n <= 0)
    return acc;

  // Local variables in each stack frame
  int local1 = n * 2;
  int local2 = n * 3;
  int local3 = n * 4;
  int local4 = n * 5;

  return recursive_spill(n - 1, acc + local1 + local2 + local3 + local4);
}

int main() {
  printf("Starting register spill test...\n");

  // Test 1: Heavy register pressure
  int result1 = heavy_register_pressure(10);
  printf("Heavy pressure result: %d\n", result1);

  // Test 2: Recursive spilling
  int result2 = recursive_spill(5, 0);
  printf("Recursive result: %d\n", result2);

  // Test 3: Loop with many variables
  int total = 0;
  for (int i = 0; i < 3; i++) {
    total += heavy_register_pressure(i);
  }
  printf("Loop total: %d\n", total);

  printf("Test complete!\n");
  return 0;
}
