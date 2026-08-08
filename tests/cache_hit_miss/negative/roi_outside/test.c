/*
 * negative/roi_outside/test.c
 *
 * Guard tested: inside_roi == false at load time
 *
 * Stack store happens INSIDE the ROI (entry added to store_map).
 * Stack load happens OUTSIDE the ROI (after m5_work_end).
 * onLoadInstruction finds the entry in store_map and isLikelySpill()
 * returns true — but inside_roi is false, so the function returns false
 * and no SPILL_LOAD flag is set.
 *
 * Expected:
 *   dcache.spillLoadHits   = 0
 *   dcache.spillLoadMisses = 0
 *   (spillStore* may be non-zero: the store IS inside ROI on the stack)
 */

#include <gem5/m5ops.h>
#include <stdint.h>

int main(void)
{
    volatile int64_t x;

    m5_work_begin(0, 0);
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL;  /* stack store inside ROI → store_map */
    m5_work_end(0, 0);

    int64_t v = x;   /* stack load OUTSIDE ROI → inside_roi=false → no SPILL_LOAD */

    return (int)(v & 1);
}
