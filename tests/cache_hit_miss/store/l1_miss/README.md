# store/l1_miss — Spill Store L1-Miss Micro-Test

## What this test validates

The tagging chain for a spill store that **misses in L1 and hits in L2**
(write-allocate RFO path):

```
TimingSimpleCPU::initiateMemWrite()
  └─ spillDetector.onStoreInstruction(addr, ...)
       └─ inside_roi && isStackAddress(addr) → return true
            └─ req->setFlags(Request::SPILL_STORE)

Request reaches L1 dcache (miss):
BaseCache::incMissCount(pkt)
  └─ isDemand() && isSpillStore() → dcache.spillStoreMisses++

L1 emits write-allocate RFO to L2 (packet INHERITS SPILL_STORE flag):
BaseCache::incHitCount(pkt)    ← called at L2
  └─ isDemand() && isSpillStore() → l2.spillStoreHits++
```

## Key discovery: SPILL_STORE propagates through RFO packets

When a store misses in L1, gem5 emits a **ReadExReq** (Read-For-Ownership)
packet toward L2 to fetch the line in exclusive state before writing.
This RFO packet **inherits the `SPILL_STORE` request flag** from the
original store.  Therefore `l2.spillStoreHits` and `l2.spillStoreMisses`
**are** meaningful for spill store analysis — not always zero as one might
naively expect.

## Expected stats

| Stat | Expected | Meaning |
|------|----------|---------|
| `system.cpu.dcache.spillStoreMisses` | **≥ 1** | L1 write-miss on stack line |
| `system.cpu.dcache.spillStoreHits` | **0** | Stack line was evicted before ROI |
| `system.l2.spillStoreHits` | **≥ 1** | Write-allocate RFO hits L2 |
| `system.l2.spillStoreMisses` | **0** | L2 still has the line (32-line flush only evicts from L1) |

## Flush design

```
Prologue:  sd ra, 24(sp)   →  main's stack frame line in L1 (Modified)

flush_l1() reads 32 × 64 B from flush_buf (BSS):
  L1 = 1 kB / 4-way = 4 sets × 4 lines
  32 flush lines → 8 competing lines per set → LRU evicts main's stack line ✓
  L2 = 8 kB / 4-way = 32 sets × 4 lines = 128 total lines
  32 flush lines fill ≤ 1 line per set << 4 ways → stack line SURVIVES in L2 ✓

m5_work_begin(0,0):  magic insn + ret — no stack access — line still absent from L1 ✓

  volatile int64_t x;
  x = 0xA5A5…    ←  stack store in ROI; L1 MISS → RFO to L2 (with SPILL_STORE)
                     dcache.spillStoreMisses++
                     L2 hits → l2.spillStoreHits++
```

## Files

| File | Purpose |
|------|---------|
| `test.c` | Flush L1 before ROI; ROI store misses L1, hits L2 |
| `Makefile` | Cross-compile for RV64GC |
| `run.sh` | Launch gem5 with 1kB/8kB cache |
| `check.sh` | Assert `dcache.spillStoreMisses >= 1`, `l2.spillStoreHits >= 1` |

## How to run

```bash
cd store/l1_miss
make
bash run.sh
bash check.sh
```

## Extension: store/l1miss_l2miss

A natural next step: flush both L1 and L2 before the ROI (160 lines,
same as `load/l1miss_l2miss`) to force `l2.spillStoreMisses >= 1`.
This would complete the store-side symmetric coverage of all cache levels.
