/*
 * negative/size_mismatch/test.c
 *
 * Guard tested: isLikelySpill() size check — store_info.size != load_size
 *
 * 8-byte stack store followed by a 4-byte load from the same address.
 * store_map entry has size=8; the load presents size=4.
 * isLikelySpill() at line 169: if (load_size != store_info.size) return false;
 *
 * Expected:
 *   dcache.spillLoadHits   = 0
 *   dcache.spillLoadMisses = 0
 */

#include <gem5/m5ops.h>
#include <stdint.h>

int main(void)
{
    m5_work_begin(0, 0);

    volatile int64_t x;
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL;    /* 8-byte store → store_map[&x] = {size=8} */

    volatile int32_t *p = (volatile int32_t *)&x;
    int32_t v = *p;                          /* 4-byte load → load_size=4 ≠ 8 → no spill */

    m5_work_end(0, 0);

    return (int)(v & 1);
}
