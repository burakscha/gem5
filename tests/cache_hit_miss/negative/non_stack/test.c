/*
 * negative/non_stack/test.c
 *
 * Guard tested: isStackAddress(addr, tc) → false
 *
 * Store and load to a BSS global inside ROI.
 * SpillDetector calls isStackAddress() for both paths:
 *   onStoreInstruction: returns inside_roi && isStackAddress() → false → no SPILL_STORE
 *   onLoadInstruction:  isLikelySpill() checks isStackAddress() → false → no SPILL_LOAD
 *
 * Expected: all spill counters = 0
 */

#include <gem5/m5ops.h>
#include <stdint.h>

/* BSS — not on the stack; isStackAddress() returns false for this address. */
static volatile int64_t bss_var;

int main(void)
{
    m5_work_begin(0, 0);

    bss_var = (int64_t)0xA5A5A5A5A5A5A5A5LL;  /* BSS store: no SPILL_STORE */
    int64_t v = bss_var;                        /* BSS load:  no SPILL_LOAD  */

    m5_work_end(0, 0);

    return (int)(v & 1);
}
