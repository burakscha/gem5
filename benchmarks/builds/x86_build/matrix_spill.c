#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <gem5/m5ops.h>

// Intentionally large N to exercise registers but keep runtime reasonable
#ifndef N
#define N 256
#endif

// Unroll factor and number of accumulators per inner loop to force register pressure
#define UNROLL 8

int main(int argc, char **argv)
{
    int n = N;
    double *A = aligned_alloc(64, sizeof(double) * n * n);
    double *B = aligned_alloc(64, sizeof(double) * n * n);
    double *C = aligned_alloc(64, sizeof(double) * n * n);
    if (!A || !B || !C) {
        fprintf(stderr, "Allocation failed\n");
        return 1;
    }
    
    // ROI START: Matrix multiplication region
    m5_work_begin(0, 0);

    // Initialize matrices with pseudo-random but deterministic values
    for (int i = 0; i < n * n; ++i) {
        A[i] = (double)((i * 31 + 7) % 97) / 97.0;
        B[i] = (double)((i * 17 + 13) % 61) / 61.0;
        C[i] = 0.0;
    }

    
    // Multiply: C = A * B
    // Use loop order and manual inner unrolling with multiple accumulators
    for (int i = 0; i < n; ++i) {
        for (int k = 0; k < n; ++k) {
            double a_ik = A[i * n + k];
            int j = 0;
            for (; j + UNROLL - 1 < n; j += UNROLL) {
                // Use UNROLL accumulators to force many live values
                C[i * n + j + 0] += a_ik * B[(k * n) + j + 0];
                C[i * n + j + 1] += a_ik * B[(k * n) + j + 1];
                C[i * n + j + 2] += a_ik * B[(k * n) + j + 2];
                C[i * n + j + 3] += a_ik * B[(k * n) + j + 3];
                C[i * n + j + 4] += a_ik * B[(k * n) + j + 4];
                C[i * n + j + 5] += a_ik * B[(k * n) + j + 5];
                C[i * n + j + 6] += a_ik * B[(k * n) + j + 6];
                C[i * n + j + 7] += a_ik * B[(k * n) + j + 7];
            }
            for (; j < n; ++j) {
                C[i * n + j] += a_ik * B[(k * n) + j];
            }
        }
    }
    
    m5_work_end(0, 0);
    // ROI END: Matrix multiplication region

    // Compute checksum so compiler cannot remove computations
    double checksum = 0.0;
    for (int i = 0; i < n * n; ++i) checksum += C[i];

    printf("N=%d checksum=%.12f\n", n, checksum);

    // Prevent compiler from optimizing away memory (volatile write)
    volatile double sink = checksum;
    (void)sink;

    free(A);
    free(B);
    free(C);
    return 0;
}
