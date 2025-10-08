#define N 64
#define M 64
#define K 64

volatile int A[N][K];
volatile int B[K][M];
volatile int C[N][M];

// Simple pseudo-random function to avoid stdlib dependency
volatile int simple_rand(volatile int *seed) {
    *seed = (*seed * 1103515245 + 12345) & 0x7fffffff;
    return *seed;
}

// Register-intensive matrix multiplication
void matrix_multiply() {
    for (volatile int i = 0; i < N; i++) {
        for (volatile int j = 0; j < M; j++) {
            volatile int sum = 0;
            for (volatile int k = 0; k < K; k++) {
                // Complex computation to force register usage
                volatile int a = A[i][k];
                volatile int b = B[k][j];
                volatile int temp1 = a * b;
                volatile int temp2 = a + b;
                volatile int temp3 = a - b;
                volatile int temp4 = temp2 * temp3;
                sum += temp1 ^ temp4;
            }
            C[i][j] = sum;
        }
    }
}

int main() {
    volatile int seed = 42;
    
    // Initialize matrices with pseudo-random values
    for (volatile int i = 0; i < N; i++) {
        for (volatile int k = 0; k < K; k++) {
            A[i][k] = simple_rand(&seed) % 100;
        }
    }
    
    for (volatile int k = 0; k < K; k++) {
        for (volatile int j = 0; j < M; j++) {
            B[k][j] = simple_rand(&seed) % 100;
        }
    }

    matrix_multiply();
    
    // Return a value to prevent optimization
    return C[0][0] % 256;
}
