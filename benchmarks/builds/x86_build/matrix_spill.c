#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <gem5/m5ops.h>

// =============================================================
// Matrix Spill Test (X86 / RISC-V compatible)
//
// Purpose:
//   Generates deliberate register pressure during matrix
//   multiplication to trigger compiler register spills.
//
// ROI (Region of Interest):
//   The multiply kernel is enclosed between m5_work_begin/end,
//   so gem5's spill detector only measures that section.
// =============================================================

// Matrix size (can be overridden with -DN=...)
#ifndef N
#define N 256
#endif

// Unroll factor controls register pressure
#ifndef UNROLL
#define UNROLL 8
#endif

// -------------------------------------------------------------
// Kernel with explicit register pressure
// -------------------------------------------------------------
__attribute__((noinline))
static void
matmul_kernel_spill(int n,
                    const double * __restrict A,
                    const double * __restrict B,
                    double * __restrict C)
{
    for (int i = 0; i < n; ++i) {
        for (int k = 0; k < n; ++k) {
            const double a_ik = A[i * n + k];

            int j = 0;
            for (; j + UNROLL - 1 < n; j += UNROLL) {
                // Hold multiple temporaries to extend live ranges
                double b0 = B[k * n + j + 0];
                double b1 = B[k * n + j + 1];
                double b2 = B[k * n + j + 2];
                double b3 = B[k * n + j + 3];
                double b4 = B[k * n + j + 4];
                double b5 = B[k * n + j + 5];
                double b6 = B[k * n + j + 6];
                double b7 = B[k * n + j + 7];

                double c0 = C[i * n + j + 0];
                double c1 = C[i * n + j + 1];
                double c2 = C[i * n + j + 2];
                double c3 = C[i * n + j + 3];
                double c4 = C[i * n + j + 4];
                double c5 = C[i * n + j + 5];
                double c6 = C[i * n + j + 6];
                double c7 = C[i * n + j + 7];

                // Multiply–accumulate: heavy register usage
                c0 += a_ik * b0;  c1 += a_ik * b1;
                c2 += a_ik * b2;  c3 += a_ik * b3;
                c4 += a_ik * b4;  c5 += a_ik * b5;
                c6 += a_ik * b6;  c7 += a_ik * b7;

                // Store back to memory after all accumulations
                C[i * n + j + 0] = c0;
                C[i * n + j + 1] = c1;
                C[i * n + j + 2] = c2;
                C[i * n + j + 3] = c3;
                C[i * n + j + 4] = c4;
                C[i * n + j + 5] = c5;
                C[i * n + j + 6] = c6;
                C[i * n + j + 7] = c7;
            }

            // Remainder loop
            for (; j < n; ++j) {
                C[i * n + j] += a_ik * B[k * n + j];
            }
        }
    }
}

// -------------------------------------------------------------
// Main program
// -------------------------------------------------------------
int main(int argc, char **argv)
{
    int n = N;

    // Allocate aligned memory for better performance
    double *A = aligned_alloc(64, sizeof(double) * n * n);
    double *B = aligned_alloc(64, sizeof(double) * n * n);
    double *C = aligned_alloc(64, sizeof(double) * n * n);
    if (!A || !B || !C) {
        fprintf(stderr, "Allocation failed\n");
        free(A); free(B); free(C);
        return 1;
    }

    // Initialize matrices (outside ROI)
    for (int i = 0; i < n * n; ++i) {
        A[i] = (double)((i * 31 + 7)  % 97) / 97.0;
        B[i] = (double)((i * 17 + 13) % 61) / 61.0;
        C[i] = 0.0;
    }

    // --- ROI START ---
    m5_work_begin(0, 0);
    matmul_kernel_spill(n, A, B, C);
    m5_work_end(0, 0);
    // --- ROI END ---

    // Compute checksum to prevent optimization removal
    double checksum = 0.0;
    for (int i = 0; i < n * n; ++i)
        checksum += C[i];
    printf("N=%d checksum=%.12f\n", n, checksum);

    // Prevent compiler from eliminating work
    volatile double sink = checksum;
    (void)sink;

    free(A);
    free(B);
    free(C);
    return 0;
}