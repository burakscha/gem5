#include <stdio.h>

int main() {
    // Create register pressure with many local variables and a loop
    // This should force the compiler to spill some registers to memory
    
    int a = 1, b = 2, c = 3, d = 4, e = 5;
    int f = 6, g = 7, h = 8, i = 9, j = 10;
    int k = 11, l = 12, m = 13, n = 14, o = 15;
    int p = 16, q = 17, r = 18, s = 19, t = 20;
    
    // Loop with many operations that should cause register spilling
    for (int loop = 0; loop < 1000; loop++) {
        // Complex calculations using many variables
        a = a + b * c - d;
        e = e * f + g - h;
        i = i + j * k - l;
        m = m * n + o - p;
        q = q + r * s - t;
        
        // More operations to increase register pressure
        b = b + a * e - i;
        f = f * c + m - q;
        j = j + g * k - n;
        d = d * h + l - r;
        t = t + o * p - s;
        
        // Even more complex expressions
        c = (a + b) * (e - f) + (i * j) - (m + n);
        g = (k - l) * (o + p) + (q - r) + (s * t);
        h = (a * b + c) - (d + e * f) + (g - h);
        k = (i + j * k) + (l - m * n) - (o + p);
        l = (q * r - s) + (t + a * b) - (c + d);
    }
    
    // Print result to ensure variables aren't optimized away
    printf("Result: %d %d %d %d %d\n", a, e, i, m, q);
    printf("More: %d %d %d %d %d\n", b, f, j, d, t);
    
    return 0;
}
