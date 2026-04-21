# l1miss_l2hit — Spill Load L1-Miss / L2-Hit Micro-Test

## What this test validates

The tagging chain when a spill reload **misses in L1 but hits in L2**:

```
BaseCache::incMissCount(pkt)          ← called at L1 (dcache)
  └─ isDemand() && isSpillLoad()  → dcache.spillLoadMisses++   [base.hh:1308]

Request forwarded to L2 (still carries SPILL_LOAD flag):

BaseCache::incHitCount(pkt)           ← called at L2
  └─ isDemand() && isSpillLoad()  → l2.spillLoadHits++         [base.hh:1317]
```

This is the second link in the chain.  A pass here confirms that the
`SPILL_LOAD` flag survives the L1→L2 forwarding path.

## Expected stats

| Stat | Expected | Meaning |
|------|----------|---------|
| `system.cpu.dcache.spillLoadMisses` | **≥ 1** | x's line evicted from L1 |
| `system.l2.spillLoadHits` | **≥ 1** | x's line found in L2 |
| `system.l2.spillLoadMisses` | **= 0** | Nothing reached DRAM as a spill |
| `system.cpu.dcache.spillLoadHits` | any | May be > 0 for hits before flush |

## Flush design

```
Store x  →  L1 has x's dirty line
│
├─ flush_l1() reads 32 × 64 B from flush_buf (BSS, non-stack)
│    32 lines  >  16 L1 lines  →  L1 fully replaced
│    dirty x line  →  write-back to L2
│    32 lines  <  128 L2 lines  →  x's line stays in L2
│
└─ Load x  →  L1 miss → L2 hit  ✓
```

`flush_buf` is global BSS — loads from it are **not** tagged as spill reloads
because `isStackAddress()` returns false for BSS addresses.

## Timing safety

```
MAX_SPILL_WINDOW = 10,000,000 ticks = 10 µs (at 1 tick = 1 ps)
32 cold DRAM accesses × ~35,000 ticks = ~1,120,000 ticks  ≪  10 µs  ✓
```

## Cache configuration

| Parameter | Value | Reason |
|-----------|-------|--------|
| `--l1d_size=1kB --l1d_assoc=4` | 16 total lines | 32 flush lines guarantee full L1 replacement |
| `--l2_size=8kB  --l2_assoc=4` | 128 total lines | 32 flush lines ≪ 128 → x survives in L2 |
| `--mem-type=SimpleMemory` | 30 ns | Flush fits within MAX_SPILL_WINDOW |

## Files

| File | Purpose |
|------|---------|
| `test.c` | Store x → flush 32 lines → load x |
| `Makefile` | Cross-compile |
| `run.sh` | Launch gem5 |
| `check.sh` | Assert `spillLoadMisses(dcache) >= 1`, `spillLoadHits(l2) >= 1`, `spillLoadMisses(l2) = 0` |

## How to run

```bash
cd load/l1miss_l2hit
make
bash run.sh
bash check.sh
```
