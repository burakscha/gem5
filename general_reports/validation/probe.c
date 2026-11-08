/* Small program with each kind of stack traffic the heuristic may see. */
#include <gem5/m5ops.h>

struct pair { long a, b; };
volatile long sink;

/* 1. Real register-allocator spills: more live values than registers. */
__attribute__((noinline)) long pressure(const long *v, int n) {
    long a0=0,a1=1,a2=2,a3=3,a4=4,a5=5,a6=6,a7=7,a8=8,a9=9,a10=10,a11=11,
         a12=12,a13=13,a14=14,a15=15,a16=16,a17=17,a18=18,a19=19,a20=20,
         a21=21,a22=22,a23=23,a24=24,a25=25,a26=26,a27=27,a28=28,a29=29;
    for (int i = 0; i < n; i++) {
        long x = v[i];
        a0+=x*3; a1^=a0+x; a2+=a1*x; a3-=a2^x; a4+=a3*a0; a5^=a4+a1; a6+=a5*a2;
        a7-=a6^a3; a8+=a7*a4; a9^=a8+a5; a10+=a9*a6; a11-=a10^a7; a12+=a11*a8;
        a13^=a12+a9; a14+=a13*a10; a15-=a14^a11; a16+=a15*a12; a17^=a16+a13;
        a18+=a17*a14; a19-=a18^a15; a20+=a19*a16; a21^=a20+a17; a22+=a21*a18;
        a23-=a22^a19; a24+=a23*a20; a25^=a24+a21; a26+=a25*a22; a27-=a26^a23;
        a28+=a27*a24; a29^=a28+a25;
    }
    return a0+a1+a2+a3+a4+a5+a6+a7+a8+a9+a10+a11+a12+a13+a14+a15+a16+a17+a18
          +a19+a20+a21+a22+a23+a24+a25+a26+a27+a28+a29;
}
/* 2. Stack-passed arguments: more than 8 integer arguments. */
__attribute__((noinline)) long many(long p0,long p1,long p2,long p3,long p4,
    long p5,long p6,long p7,long p8,long p9,long p10) {
    return p0+p1+p2+p3+p4+p5+p6+p7+p8*p9-p10;
}
/* 3. A memory-resident local reached at constant sp offsets. */
__attribute__((noinline)) void fill(struct pair *p) { p->a += 1; }
__attribute__((noinline)) long local_struct(long x) {
    struct pair s = { x, x * 2 };
    fill(&s);
    return s.a + s.b;
}
/* 4. Non-leaf function: ra and callee-saved registers saved and restored. */
__attribute__((noinline)) long nonleaf(long x) {
    long y = many(x,1,2,3,4,5,6,7,8,9,10);
    return y + local_struct(y);
}
static long data[64];
int main(void) {
    for (int i = 0; i < 64; i++) data[i] = i * 7 + 1;
    m5_work_begin(0, 0);
    long r = 0;
    for (int k = 0; k < 20; k++) r += pressure(data, 64) + nonleaf(k);
    m5_work_end(0, 0);
    sink = r;
    return 0;
}
