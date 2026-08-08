# l1_hit — Spill Load L1 Hit Micro-Test

## What this test validates

The complete tagging chain for a spill reload that **hits in L1**:

```
timing.cc::readMem()
  └─ spillDetector.onLoadInstruction()
        └─ store_map.find(addr)  → found
        └─ isLikelySpill()       → temporal order ✓ / size match ✓ / isStackAddress ✓
        └─ inside_roi            → true
        └─ returns true
  └─ req->setFlags(Request::SPILL_LOAD)     [timing.cc:508]
BaseCache::incHitCount(pkt)
  └─ isDemand() && isSpillLoad()  → spillLoadHits++   [base.hh:1317]
```

## Expected stats

| Stat | Expected | Meaning |
|------|----------|---------|
| `system.cpu.dcache.spillLoadHits` | **≥ 1** | Spill reload found in L1 |
| `system.cpu.dcache.spillLoadMisses` | **= 0** | No L1 eviction occurred |
| `system.l2.spillLoadHits` | **= 0** | L2 never consulted for spill |
| `system.l2.spillLoadMisses` | **= 0** | — |

## Cache configuration

| Parameter | Value | Reason |
|-----------|-------|--------|
| `--l1d_size=1kB --l1d_assoc=4` | 16 total lines | Small → easy to flush in other tests |
| `--l2_size=8kB  --l2_assoc=4` | 128 total lines | — |
| `--mem-type=SimpleMemory` | 30 ns latency | Within `MAX_SPILL_WINDOW` (10 µs) |

## Files

| File | Purpose |
|------|---------|
| `test.c` | Store then immediately load a `volatile int64_t` on the stack |
| `Makefile` | Cross-compile with `riscv64-unknown-elf-gcc -O2 -static` |
| `run.sh` | Launch gem5 with small caches; writes to `m5out/` |
| `check.sh` | Grep `stats.txt` and assert pass/fail conditions |

## How to run

```bash
cd load/l1_hit
make
bash run.sh
bash check.sh
```

## Key constraint: MAX_SPILL_WINDOW

`spill_detector.hh` enforces `MAX_SPILL_WINDOW = 10,000,000 ticks = 10 µs`.
A store is removed from `store_map` if the matching load does not arrive within
this window.  This test has **no flush between store and load**, so the window
is not a concern here.  It matters in the miss tests.
