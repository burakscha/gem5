#include <stdio.h>
// m5ops YOK - sadece karşılaştırma için
int heavy_register_pressure(int input) {
    int a1 = input + 1, a2 = input + 2, a3 = input + 3, a4 = input + 4, a5 = input + 5;
    int a6 = input + 6, a7 = input + 7, a8 = input + 8, a9 = input + 9, a10 = input + 10;
    int a11 = input + 11, a12 = input + 12, a13 = input + 13, a14 = input + 14, a15 = input + 15;
    int a16 = input + 16, a17 = input + 17, a18 = input + 18, a19 = input + 19, a20 = input + 20;
    int sum = a1+a2+a3+a4+a5+a6+a7+a8+a9+a10+a11+a12+a13+a14+a15+a16+a17+a18+a19+a20;
    int product = a1*a2 + a3*a4 + a5*a6 + a7*a8 + a9*a10 + a11*a12 + a13*a14 + a15*a16 + a17*a18 + a19*a20;
    return sum + product;
}
int main() {
    printf("=== NO-ROI Test ===\n");
    int pre = heavy_register_pressure(5);
    printf("Pre result: %d\n", pre);

    printf(">>> (No ROI markers here) <<<\n");
    int r1 = heavy_register_pressure(10);
    int r2 = heavy_register_pressure(20);
    int r3 = heavy_register_pressure(30);
    printf("Results: %d, %d, %d\n", r1, r2, r3);

    int post = heavy_register_pressure(100);
    printf("Post result: %d\n", post);
    printf("=== Complete ===\n");
    return 0;
}
