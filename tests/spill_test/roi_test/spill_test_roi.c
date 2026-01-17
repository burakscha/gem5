/*
 * Register Spill Test Program with ROI (Region of Interest)
 *
 * This program tests spill detection within a specific code region.
 * Only spills inside m5_work_begin/end markers should be counted (when ROI is
 * enabled).
 *
 * Compile with:
 *   riscv64-linux-gnu-gcc -O0 -static -I/workspace/include \
 *     spill_test_roi.c /workspace/util/m5/src/abi/riscv/m5op.o \
 *     -o spill_test_roi.riscv
 */

#include <gem5/m5ops.h>
#include <stdio.h>

// Heavy computation function (same as before)
int heavy_register_pressure(int input) {
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

  int sum = a1 + a2 + a3 + a4 + a5;
  sum += a6 + a7 + a8 + a9 + a10;
  sum += a11 + a12 + a13 + a14 + a15;
  sum += a16 + a17 + a18 + a19 + a20;

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

int main() {
  printf("=== ROI Spill Test ===\n");

  // ============================================
  // PRE-ROI: Spills here should NOT be counted
  // ============================================
  printf("Pre-ROI: Running setup...\n");
  int pre_result = heavy_register_pressure(5);
  printf("Pre-ROI result: %d\n", pre_result);

  // ============================================
  // ROI BEGIN - Start measuring spills here
  // ============================================
  printf(">>> Entering ROI (workid=0) <<<\n");
  m5_work_begin(0, 0);

  // Heavy computation INSIDE ROI - spills should be counted
  int roi_result1 = heavy_register_pressure(10);
  int roi_result2 = heavy_register_pressure(20);
  int roi_result3 = heavy_register_pressure(30);

  m5_work_end(0, 0);
  printf(">>> Exiting ROI <<<\n");
  // ============================================
  // ROI END - Stop measuring spills
  // ============================================

  printf("ROI results: %d, %d, %d\n", roi_result1, roi_result2, roi_result3);

  // ============================================
  // POST-ROI: Spills here should NOT be counted
  // ============================================
  printf("Post-ROI: Running cleanup...\n");
  int post_result = heavy_register_pressure(100);
  printf("Post-ROI result: %d\n", post_result);

  printf("=== Test Complete ===\n");
  return 0;
}
