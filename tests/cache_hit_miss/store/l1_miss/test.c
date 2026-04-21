/*
 * store/l1_miss/test.c — Spill Store L1-Miss Micro-Test
 *
 * What this tests:
 *   A stack store inside the ROI that MISSES the L1 dcache.
 *
 * How:
 *   1. The function prologue stores ra/s0 to main's stack frame → line in L1.
 *   2. flush_l1() reads 32 × 64 B from flush_buf (BSS, not stack).
 *      L1 is 1 kB / 4-way = 4 sets of 4 lines.
 *      32 flush lines saturate every set 8× → LRU evicts main's stack line.
 *      flush_buf is BSS so isStackAddress() will never tag these loads.
 *   3. m5_work_begin(0,0) opens the ROI (no memory access: magic insn + ret).
 *   4. volatile store `x = val`: stack line is NOT in L1 → L1 miss →
 *      RFO (Read-For-Ownership) fetches the line from L2/DRAM.
 *      dcache.spillStoreMisses++.
 *
 * NOTE: Because RISC-V function call (`jal ra, flush_l1`) does not touch
 * memory (ra is written to the register file, not the stack), the stack line
 * remains evicted between flush_l1() returning and the ROI store.
 * m5_work_begin is also a leaf (magic insn + ret, no stack frame), so it
 * does not re-warm the stack line either.
 *
 * Expected:
 *   system.cpu.dcache.spillStoreMisses >= 1
 *   system.cpu.dcache.spillStoreHits    = 0   (or very small if other
 *                                              stack stores happen in ROI)
 */

#include <gem5/m5ops.h>
#include <stdint.h>

#define FLUSH_LINES  32
#define LINE_BYTES   64

/* BSS array — addresses fail isStackAddress() so flush loads are never
 * tagged as spill reloads.  Volatile to prevent dead-store elimination. */
static volatile char flush_buf[FLUSH_LINES * LINE_BYTES];

/* noinline + -O2 → compiler uses only caller-saved regs inside this
 * function; no ra push/pop → no stack accesses inside flush_l1.
 * Returns a sum so the loop cannot be optimised away. */
static __attribute__((noinline)) int flush_l1(void)
{
    int acc = 0;
    int i;
    for (i = 0; i < FLUSH_LINES; i++)
        acc += flush_buf[i * LINE_BYTES];
    return acc;
}

int main(void)
{
    /* Step 1: prologue has already touched main's stack frame line (L1 hot).
     * Step 2: evict it by flooding L1 with BSS accesses. */
    int dummy = flush_l1();

    /* Step 3: open ROI — stack line is evicted, m5_work_begin is leaf. */
    m5_work_begin(0, 0);

    /* Step 4: stack store inside ROI → L1 miss → dcache.spillStoreMisses++ */
    volatile int64_t x;
    x = (int64_t)0xA5A5A5A5A5A5A5A5LL;

    m5_work_end(0, 0);

    return (int)(x & 1) | (dummy & 1);
}
