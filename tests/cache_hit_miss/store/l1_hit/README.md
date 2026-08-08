# store/l1_hit — Spill Store L1-Hit Micro-Test

## What this test validates

The tagging chain for a spill store that **hits in L1**:

```
TimingSimpleCPU::initiateMemWrite()
  └─ spillDetector.onStoreInstruction(addr, ...)
       └─ inside_roi && isStackAddress(addr) → return true
            └─ req->setFlags(Request::SPILL_STORE)

Request reaches L1 dcache:
BaseCache::incHitCount(pkt)
  └─ isDemand() && isSpillStore() → dcache.spillStoreHits++
```

This validates the simplest store path: the `SPILL_STORE` flag is set
and the hit counter increments when the stack line is already in L1.

## Expected stats

| Stat | Expected | Meaning |
|------|----------|---------|
| `system.cpu.dcache.spillStoreHits` | **≥ 1** | L1 write-hit on stack line |
| `system.cpu.dcache.spillStoreMisses` | **0** | No misses expected |
| `system.l2.spillStoreHits` | **0** | L2 never receives store-hit packet |
| `system.l2.spillStoreMisses` | **0** | See L2 note below |

## Why L2 counters are 0 for this test

When L1 **hits**, the request is satisfied entirely within L1 and no
packet is forwarded to L2.  Therefore `l2.spillStore{Hits,Misses}` are
both 0 for this specific test.

Note: when L1 **misses** (see `store/l1_miss`), gem5's write-allocate
RFO packet **does** carry the `SPILL_STORE` flag to L2, so
`l2.spillStoreHits` and `l2.spillStoreMisses` are meaningful in that case.

## Test design

```
main's prologue:
  sd ra, 24(sp)    ← stores to stack frame → line in L1 (Modified)
  sd s0, 16(sp)

m5_work_begin(0,0) ← ROI opens; no memory access (magic insn + ret)

  volatile int64_t x;
  x = 0xA5A5…    ← stack store inside ROI; line is in L1 → HIT
                    → dcache.spillStoreHits++

m5_work_end(0,0)
```

## Key difference from store/l1_miss

`store/l1_hit` performs **no flush** between the prologue and ROI.
The stack line is warm in L1 (Modified) when the volatile store fires.

## Files

| File | Purpose |
|------|---------|
| `test.c` | Prologue warms L1 → ROI store hits |
| `Makefile` | Cross-compile for RV64GC |
| `run.sh` | Launch gem5 with 1kB/8kB cache |
| `check.sh` | Assert `spillStoreHits >= 1`, misses = 0 |

## How to run

```bash
cd store/l1_hit
make
bash run.sh
bash check.sh
```
