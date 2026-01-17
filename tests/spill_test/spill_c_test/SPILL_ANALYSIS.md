# Compiler-Generated Spill Pattern Analysis

## Source File
`spill_test.c` → compiled with `riscv64-linux-gnu-gcc -O0 -S`

---

## 🔍 Key Findings

### 1. Function Prologue/Epilogue (Callee-Saved Registers)

**Pattern: Save on entry, restore on exit**

```asm
# Function Entry (Prologue)
heavy_register_pressure:
    addi    sp,sp,-128          # Allocate 128 bytes on stack
    sd      s0,120(sp)          # STORE: Save s0 (frame pointer) ← SPILL!

# Function Exit (Epilogue)
    ld      s0,120(sp)          # LOAD: Restore s0 ← SPILL PAIR!
    addi    sp,sp,128           # Deallocate stack
    jr      ra
```

**Observation**: This is a REAL spill - compiler saves callee-saved register `s0` and restores it later.

---

### 2. Local Variable Storage Pattern

**Pattern: Store result, load for next operation**

```asm
# Line 12-13: Store function argument, then load it
    sw      a5,-116(s0)         # STORE: input arg to stack
    lw      a5,-116(s0)         # LOAD: same address → IS THIS A SPILL?
```

**Analysis**:
- This happens because `-O0` doesn't optimize
- Compiler stores every variable, then reloads for each use
- Technically these ARE spills (value temporarily on stack)

---

### 3. Intermediate Result Pattern

```asm
# Lines 73-76: Load multiple values for sum
    lw      a5,-104(s0)         # LOAD a1
    mv      a4,a5
    lw      a5,-100(s0)         # LOAD a2
    addw    a5,a4,a5            # sum = a1 + a2
```

**Observation**:
- Values stored earlier are being loaded back
- Store PC and Load PC are DIFFERENT (not adjacent)
- Distance between store and load can be 10-50 instructions

---

## 📊 Spill Categories Found

| Category | Example | Is Real Spill? | Our Detection |
|----------|---------|----------------|---------------|
| **Callee-saved preservation** | `sd s0` at entry, `ld s0` at exit | ✅ YES | ✅ Detects |
| **Argument save/reload** | `sw a5,-116(s0)` → `lw a5,-116(s0)` | ✅ YES | ✅ Detects |
| **Local variable store/load** | Store a1, load a1 later | ✅ YES | ✅ Detects |
| **Return address save** | `sd ra,40(sp)` → `ld ra,40(sp)` | ✅ YES | ✅ Detects |

---

## 🎯 Key Observations

### What Makes a "Real" Spill:
1. **Address**: Must be on stack (sp-relative or s0/fp-relative)
2. **Temporal Order**: Store happens BEFORE load
3. **Same Address**: Load reads from exact address that was stored

### Our Current Logic:
```cpp
if (load_addr matches recent store_addr) → SPILL
```

### Potential False Positives:
1. ❌ Heap memory access (not stack)
2. ❌ Global variable access
3. ❌ Memory-mapped I/O

### Suggested Improvements:
1. ✅ **Stack proximity check**: Only flag if address is near SP
2. ✅ **Maximum instruction window**: Spill-reload typically within ~100 instructions
3. ⚠️ **Frame pointer awareness**: Account for s0/fp-relative addressing

---

## 📈 Statistics from Generated Assembly

| Metric | Count |
|--------|-------|
| Total `sd` (store double) | 4 |
| Total `sw` (store word) | 48 |
| Total `ld` (load double) | 4 |
| Total `lw` (load word) | 54 |
| **Potential Spill Pairs** | ~52 |

---

## ✅ Conclusion

**Our current detection logic is fundamentally correct!**

The pattern `store → ... → load (same address)` IS how real register spills work in `-O0` compiled code.

**Recommended improvements:**
1. Add stack address check (filter non-stack memory)
2. Optional: Add maximum instruction distance filter
3. Consider frame pointer (s0) relative addressing
