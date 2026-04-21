# l1miss_l2miss — Spill Load L1-Miss / L2-Miss Micro-Test

## What this test validates

The tagging chain for a spill reload that **misses in both L1 and L2**,
forcing a fetch from DRAM:

```
BaseCache::incMissCount(pkt)          ← called at L1 (dcache)
  └─ isDemand() && isSpillLoad()  → dcache.spillLoadMisses++

Request forwarded to L2 (still carries SPILL_LOAD flag):

BaseCache::incMissCount(pkt)          ← called at L2
  └─ isDemand() && isSpillLoad()  → l2.spillLoadMisses++
```

This validates the deepest path: the `SPILL_LOAD` flag must survive
L1→L2 forwarding AND L2→memory forwarding, and `incMissCount` must fire
at both levels.

## Expected stats

| Stat | Expected | Meaning |
|------|----------|---------|
| `system.cpu.dcache.spillLoadMisses` | **≥ 1** | x's line evicted from L1 |
| `system.l2.spillLoadMisses` | **≥ 1** | x's line also evicted from L2 |
| `system.cpu.dcache.spillLoadHits` | any | OK if other spills hit before flush |
| `system.l2.spillLoadHits` | any | OK if some spills hit L2 before full eviction |

## Flush design

```
Store x  →  L1 has x's dirty line
│
├─ flush_l1_l2() reads 160 × 64 B from flush_buf
│    Phase A (first ~16 accesses):
│      L1 fills up → x's dirty line written back to L2
│    Phase B (next ~144 accesses):
│      L2 sets fill up:
│        160 lines / 32 L2-sets = 5 lines per set
│        4-way LRU: set holds 4 → 5th access evicts LRU
│        x's set: evicted on the 5th competing flush line  ✓
│
└─ Load x  →  L1 miss → L2 miss → DRAM  ✓
```

## Timing safety

```
MAX_SPILL_WINDOW = 10,000,000 ticks = 10 µs
160 cold DRAM accesses × ~35,000 ticks = ~5,600,000 ticks  <  10 µs  ✓
```

## Cache configuration

| Parameter | Value | Reason |
|-----------|-------|--------|
| `--l1d_size=1kB --l1d_assoc=4` | 16 total lines | 160 flush lines guarantee L1 replacement |
| `--l2_size=8kB  --l2_assoc=4` | 32 sets, 4-way | 160/32 = 5 per set > 4 ways → overflow |
| `--mem-type=SimpleMemory` | 30 ns | Flush fits within MAX_SPILL_WINDOW |

## Files

| File | Purpose |
|------|---------|
| `test.c` | Store x → flush 160 lines → load x |
| `Makefile` | Cross-compile |
| `run.sh` | Launch gem5 |
| `check.sh` | Assert `spillLoadMisses(dcache) >= 1` AND `spillLoadMisses(l2) >= 1` |

## How to run

```bash
cd load/l1miss_l2miss
make
bash run.sh
bash check.sh
```

## MAX_SPILL_WINDOW requirement

`spill_detector.hh` has a `MAX_SPILL_WINDOW` constant that evicts store_map
entries older than the threshold.  With 160 cold DRAM accesses at ~185K ticks
each, the flush takes ~29M ticks — well above the original 10M limit.

**Required change (already applied):**
```
// spill_detector.hh line 118
static const Tick MAX_SPILL_WINDOW = 50000000;  // 50 µs
```
After this change, rebuild gem5 (`bash gem5/rebuild.sh` or the scons command
in MEMORY.md).  Real benchmark spills are always within a single function frame
(< 1 µs), so 50 µs is still a very conservative upper bound.

## If the l2 miss check fails

The most common cause: the flush array did not fully evict x from L2.
Check that `run.sh` uses exactly `--l2_size=8kB --l2_assoc=4`.
With a larger L2 the 160-line flush may not be enough; increase
`FLUSH_LINES` in `test.c` accordingly (keep total flush time < 10 µs).
