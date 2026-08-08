# store/l1miss_l2miss — Spill Store L1-Miss / L2-Miss Micro-Test

## What this test validates

The tagging chain for a spill store that **misses in both L1 and L2**,
forcing a DRAM fetch via the write-allocate RFO path:

```
TimingSimpleCPU::initiateMemWrite()
  └─ spillDetector.onStoreInstruction(addr, ...)
       └─ inside_roi && isStackAddress(addr) → return true
            └─ req->setFlags(Request::SPILL_STORE)

L1 dcache (miss):
BaseCache::incMissCount(pkt)
  └─ isDemand() && isSpillStore() → dcache.spillStoreMisses++

L1 emits RFO to L2 (packet carries SPILL_STORE):
BaseCache::incMissCount(pkt)   ← called at L2
  └─ isDemand() && isSpillStore() → l2.spillStoreMisses++

L2 fetches line from DRAM.
```

This is the deepest store path: SPILL_STORE survives L1 → L2 → DRAM,
and `incMissCount` fires at both cache levels.

## Expected stats

| Stat | Expected | Meaning |
|------|----------|---------|
| `system.cpu.dcache.spillStoreMisses` | **≥ 1** | L1 write-miss (stack line evicted) |
| `system.cpu.dcache.spillStoreHits` | **0** | No hits: line was evicted before ROI |
| `system.l2.spillStoreMisses` | **≥ 1** | Write-allocate RFO also misses L2 |
| `system.l2.spillStoreHits` | **0** | L2 evicted → miss, not hit |

## Flush design

```
x = 0           (pre-ROI, before ROI, pre-warms x's cache line in L1)

flush_l1_l2():  reads 160 × 64 B from flush_buf (BSS)
  L1 = 1 kB, 4-way → 4 sets:
    160 / 4 = 40 competing lines per set >> 4 ways → L1 eviction ✓
  L2 = 8 kB, 4-way → 32 sets:
    160 / 32 = 5 competing lines per set > 4 ways → L2 eviction ✓

m5_work_begin(0,0):  leaf (magic insn + ret), no stack access

  x = 0xA5A5…   L1 miss → RFO (SPILL_STORE) → L2 miss → DRAM
                 dcache.spillStoreMisses++
                 l2.spillStoreMisses++
```

## Symmetry with load/l1miss_l2miss

This test mirrors `load/l1miss_l2miss` exactly:

| | load/l1miss_l2miss | store/l1miss_l2miss |
|---|---|---|
| Flush lines | 160 | 160 |
| L1 eviction | ✓ | ✓ |
| L2 eviction | ✓ | ✓ |
| Primary counter | `dcache.spillLoadMisses` | `dcache.spillStoreMisses` |
| L2 counter | `l2.spillLoadMisses` | `l2.spillStoreMisses` |
| Flag carrier | original load packet | write-allocate RFO packet |

## Files

| File | Purpose |
|------|---------|
| `test.c` | Pre-warm → flush both L1+L2 → ROI store → L1+L2 miss |
| `Makefile` | Cross-compile for RV64GC |
| `run.sh` | Launch gem5 with 1kB/8kB cache |
| `check.sh` | Assert `dcache.spillStoreMisses >= 1` AND `l2.spillStoreMisses >= 1` |

## How to run

```bash
cd store/l1miss_l2miss
make
bash run.sh
bash check.sh
```
