# Spill Detection Analysis - Comparison Report

## 📊 Executive Summary

| Metric | spill_exact.S (Controlled) | spill_test.c (Real) |
|--------|---------------------------|---------------------|
| **Total Instructions** | 17 | 10,360 |
| **Load Instructions** | 4 | 2,124 |
| **Store Instructions** | 4 | 1,855 |
| **Detected Spills** | 4 | 1,094 |
| **Spill Rate (spills/stores)** | 100% | 59% |
| **Spill Rate (spills/loads)** | 100% | 51.5% |

---

## 🔍 Pattern Analysis

### Stack Proximity from DEBUG Output

The DEBUG logs show `Addr | SP | Diff` where Diff = |Addr - SP|

**Valid Stack Accesses (small Diff values):**
```
Diff: 0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40...
      ↑ These are LOCAL VARIABLES on stack
```

**Non-Stack Accesses (huge Diff values):**
```
Diff: 9223372036854291176, 9223372036854296600...
      ↑ These are GLOBAL/HEAP memory accesses
```

### Key Observation
The huge Diff values (9e18+) indicate memory accesses FAR from the stack pointer. These are likely:
- Global variables
- Heap allocations
- Library code (libc)

**⚠️ These should NOT be counted as spills!**

---

## 📈 Spill Frequency Analysis

### From spill_test.c execution:

| Category | Count | Percentage |
|----------|-------|------------|
| Total Spills Logged | 1,094 | 100% |
| Estimated True Stack Spills | ~200-400 | 20-40% |
| Likely False Positives | ~700-900 | 60-80% |

### Why False Positives?
1. **Global variable access**: `Diff: 9223372036854296600` (address `0x74e98`)
2. **Library code**: `printf`, `puts` use memory for buffers
3. **Heap memory**: Dynamic allocations

---

## 🧮 Theoretical Spill Estimation

### From spill_test_generated.s (static analysis):

**heavy_register_pressure() function:**
- Uses 20+ local variables
- Each variable: 1 store (init) + 1-3 loads (use)
- Expected spills per call: ~20-30
- Called 4 times (1 + 3 loop iterations)
- **Estimated: 80-120 spills**

**recursive_spill() function:**
- Uses 4 local variables per frame
- Recursion depth: 5
- **Estimated: 20 spills**

**main() function:**
- Callee-saved registers (ra, s0): 4 spills
- Local variables: ~10 spills
- **Estimated: 14 spills**

**Total Theoretical (user code only): ~120-160 spills**

---

## 🎯 Accuracy Assessment

| Measurement | Value |
|-------------|-------|
| Theoretical Spills (user code) | ~150 |
| Detected Spills | 1,094 |
| **Over-detection Ratio** | **~7x** |

### Root Cause
The current logic counts ALL store-load pairs to the same address, including:
- ❌ Library function memory access (printf buffers, etc.)
- ❌ Global variables
- ❌ Non-stack memory

---

## ✅ What's Working

1. **Core logic is correct**: Store → Load to same address IS detected
2. **Stack spills ARE captured**: User function spills included
3. **Temporal ordering correct**: Store always before Load

## ❌ What Needs Improvement

1. **Stack boundary check**: Filter addresses not near SP
2. **Maximum distance filter**: Difference from SP should be < stack_frame_size
3. **Global address exclusion**: Exclude addresses in .data/.bss sections

---

## 🔧 Recommended Filter

```cpp
bool isStackSpill(Addr addr, Addr sp) {
    // Stack grows downward in RISC-V
    // Valid spill: addr should be >= sp (in current frame)
    // and addr < sp + MAX_FRAME_SIZE (typically 4096 bytes)

    int64_t diff = (int64_t)(addr - sp);

    return (diff >= 0 && diff < 4096);  // 4KB frame limit
}
```

---

## 📋 Next Steps

1. [ ] Add stack proximity filter to spill_detector.cc
2. [ ] Re-run spill_exact.S → Should still get 4 spills
3. [ ] Re-run spill_test.c → Should get ~150 spills (not 1094)
4. [ ] Validate with additional test cases
