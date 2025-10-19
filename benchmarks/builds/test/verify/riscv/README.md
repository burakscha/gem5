# RISC-V Register Spill Detection Verification Test

This directory contains a pure assembly verification test for the gem5 RISC-V register spill detector.

## 📁 Files

| File | Description |
|------|-------------|
| `pure_asm_spill.S` | Pure assembly test with exactly 9 predictable register spills |
| `pure_asm_spill.elf` | Compiled ELF binary for RISC-V 64-bit |
| `m5op.o` | gem5 m5ops library for ROI (Region of Interest) marking |
| `run_riscv_spill_test.py` | gem5 simulation configuration script |
| `README.md` | This documentation file |

---

## 🎯 Test Objective

This test verifies that the **RISC-V SpillDetector** in gem5 correctly identifies register spill events by executing a controlled assembly program with **exactly 9 spills** organized into three test cases.

### Expected Spill Pattern:
- **Test 1:** 1 spill (1 store → 1 load)
- **Test 2:** 3 spills (3 stores → 3 loads)
- **Test 3:** 5 spills (5 stores → 5 loads)
- **Total:** 9 spills

---

## 🧪 Test Design

### Assembly Structure

```assembly
main:
    addi sp, sp, -80           # Allocate stack space
    call m5_work_begin         # Mark ROI start
    
    # TEST 1: Single spill
    li t0, 0xAAAAAAAAAAAAAAAA
    sd t0, 0(sp)              # STORE to stack
    nop
    nop
    ld t1, 0(sp)              # LOAD from stack → SPILL #1
    
    # TEST 2: Three spills
    li t0, 0x1111111111111111
    sd t0, 8(sp)              # STORE #1
    li t1, 0x2222222222222222
    sd t1, 16(sp)             # STORE #2
    li t2, 0x3333333333333333
    sd t2, 24(sp)             # STORE #3
    nop
    ld t3, 8(sp)              # LOAD #1 → SPILL #2
    ld t4, 16(sp)             # LOAD #2 → SPILL #3
    ld t5, 24(sp)             # LOAD #3 → SPILL #4
    
    # TEST 3: Five spills
    # Similar pattern with 5 stores followed by 5 loads
    # → SPILLS #5, #6, #7, #8, #9
    
    call m5_work_end           # Mark ROI end
    addi sp, sp, 80
    ecall                      # Exit
```

### Why This Pattern Detects Spills

1. **Stack-based memory accesses:** All stores/loads use `sp` (stack pointer)
2. **Short temporal proximity:** Loads happen shortly after stores
3. **Same memory addresses:** Each load reads from the same address written by its paired store
4. **Clear pairing:** NOP instructions create separation between store and load phases

---

## 🔧 Building the Test

### Prerequisites
- RISC-V 64-bit GNU toolchain (`riscv64-unknown-linux-gnu-gcc`)
- gem5 with RISC-V support compiled (`build/RISCV/gem5.opt`)
- m5ops library compiled for RISC-V

### Build Commands

```bash
# Navigate to gem5 root directory
cd /path/to/gem5

# Compile assembly test
riscv64-unknown-linux-gnu-gcc -static -nostdlib -nostartfiles \
    -Iutil/m5/build/riscv/out \
    -o benchmarks/builds/test/verify/riscv/pure_asm_spill.elf \
    benchmarks/builds/test/verify/riscv/pure_asm_spill.S \
    benchmarks/builds/test/verify/riscv/m5op.o
```

### Verify Binary

```bash
# Check if properly linked
file benchmarks/builds/test/verify/riscv/pure_asm_spill.elf
# Expected: ELF 64-bit LSB executable, UCB RISC-V, statically linked

# Disassemble to verify instructions
riscv64-unknown-linux-gnu-objdump -d pure_asm_spill.elf | less
```

---

## 🚀 Running the Test

### Basic Execution

```bash
# From gem5 root directory
build/RISCV/gem5.opt \
    benchmarks/builds/test/verify/riscv/run_riscv_spill_test.py
```

### Expected Console Output

```
🧩 Detected ISA: RISCV
Running pure assembly spill test: benchmarks/builds/test/verify/riscv/pure_asm_spill.elf
======================================================================
🧪 Assembly Spill Verification Test (RISCV)
======================================================================
Expected spills: 9 (1 + 3 + 5)
======================================================================
✅ Simulation finished @ tick 6125868
   Reason: exiting with last active thread context
======================================================================
📊 Check results:
   m5out/stats.txt -> should reflect your spill detection counters
======================================================================
```

---

## 📊 Analyzing Results

### 1. Check Spill Detection Output

```bash
cat m5out/riscv_spill_stats.txt
```

**Expected format:**
```
SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count
SPILL,10130,10136,7ffffffffffffec0,844488,985347,140859,14,17
SPILL,10152,1018e,7ffffffffffffec8,1477854,2548449,1070595,26,46
...
(9 spill lines total)
```

### 2. Verify Instruction Counts

```bash
grep -E "simInsts|numLoadInsts|numStoreInsts" m5out/stats.txt
```

**Expected values:**
- `simInsts`: ~108 (includes pseudo-instruction expansion)
- `numLoadInsts`: 9 (exactly 9 ld instructions)
- `numStoreInsts`: 9 (exactly 9 sd instructions)

### 3. Advanced Analysis

```bash
# Run the analysis script
python3 benchmarks/analytics/advanced_spill_analysis.py m5out/

# This generates:
# - m5out/analysis_report.txt (comprehensive spill analysis)
# - ROI-specific statistics
# - Spill-to-load/store ratios
```

---

## 📈 Understanding Instruction Count

The assembly test appears to have ~42 manual instructions, but gem5 reports **108 instructions**. This is due to **pseudo-instruction expansion** in RISC-V:

### Pseudo-Instruction Expansion

| Pseudo-Instruction | Real Instructions | Count |
|-------------------|------------------|-------|
| `li t0, 0xAAAAAAAAAAAAAAAA` | `lui` + `addi` + `slli` + `addi` + ... | 4-6 instructions |
| `call m5_work_begin` | `auipc ra, offset` + `jalr ra, ra, offset` | 2 instructions |

**Calculation:**
- 10× `li` (64-bit immediates) → ~50 instructions
- 2× `call` → 4 instructions
- Other instructions → 42 instructions
- **Total: ~96-110 instructions** ✅

This is **completely normal** and expected behavior in RISC-V.

---

## ✅ Validation Checklist

- [ ] Binary builds without errors
- [ ] gem5 simulation completes successfully
- [ ] Exactly **9 spills** detected in `riscv_spill_stats.txt`
- [ ] `numLoadInsts` = 9 in `stats.txt`
- [ ] `numStoreInsts` = 9 in `stats.txt`
- [ ] All spill events use stack addresses (0x7fff...)
- [ ] Store and load PCs are correctly paired
- [ ] No false positives (non-spill memory accesses misidentified)

---

## 🐛 Troubleshooting

### Problem: No spills detected

**Solution:**
1. Verify SpillDetector is enabled in gem5 build
2. Check that `timing.cc` includes the correct RISC-V spill detector
3. Ensure binary is using stack pointer (`sp`) for memory accesses

### Problem: Wrong number of spills

**Solution:**
1. Disassemble binary to verify instruction sequence
2. Check if compiler optimizations altered the code
3. Verify `nop` instructions are present (prevent optimization)

### Problem: Simulation crashes

**Solution:**
1. Check binary is statically linked
2. Verify m5ops library is correctly linked
3. Ensure RISC-V gem5 binary is used (not X86)

---

## 🔬 Extending the Test

### Add More Spill Patterns

```assembly
# Test with different registers
sd a0, 72(sp)
ld a1, 72(sp)

# Test with different temporal distances
sd t0, 0(sp)
nop
nop
nop
nop
nop
ld t1, 0(sp)
```

### Modify ROI Boundaries

```assembly
# Multiple ROI regions
call m5_work_begin
# ... spill test 1 ...
call m5_work_end

call m5_work_begin
# ... spill test 2 ...
call m5_work_end
```

---

## 📚 Related Documentation

- **SpillDetector Implementation:** `src/cpu/riscv_spill_detector.cc/hh`
- **gem5 m5ops Documentation:** [gem5.org/documentation/general_docs/m5ops](https://www.gem5.org/documentation/general_docs/m5ops/)
- **RISC-V Assembly Reference:** RISC-V Instruction Set Manual
- **Analysis Script:** `benchmarks/analytics/advanced_spill_analysis.py`

---

## 📝 Notes

1. This test uses **pure assembly** to eliminate compiler uncertainty
2. All spills are **intentional and predictable**
3. The test uses **m5ops** to mark the Region of Interest (ROI)
4. Spill detection is based on **temporal and spatial locality** of stack accesses
5. The test is designed for **verification**, not performance benchmarking

---

## 👥 Contributing

To improve this test:
1. Add more edge cases (overlapping spills, different stack offsets)
2. Create x86 equivalent for cross-ISA validation
3. Add automated validation scripts
4. Document false positive/negative scenarios

---

**Last Updated:** October 2025  
**gem5 Version:** Tested on gem5 v23+  
**ISA:** RISC-V 64-bit (RV64GC)
