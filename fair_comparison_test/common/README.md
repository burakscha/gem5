# Fair Cross-Architecture Register Spill Testing Methodology

## 🎯 Objective
Compare register spill detection behavior between X86 and RISC-V architectures using **identical test code** and **identical simulation parameters**.

## 📋 Test Design Principles

### 1. **Unified Test Code**
- **File**: `common/unified_spill_test.c`
- **Variables**: 25 integer variables (exceeds typical register count)
- **Loop Count**: 150 iterations (optimal for measurable spills)
- **Complexity**: Complex cross-dependencies to force register pressure
- **Architecture Agnostic**: Pure C code, no assembly or architecture-specific constructs

### 2. **Identical Simulation Parameters**
```
CPU Type:       TimingSimpleCPU
L1D Cache:      16kB  
L1I Cache:      16kB
Memory:         8GB DDR3-1600
Clock:          3GHz
```

### 3. **Controlled Variables**
- ✅ **Same**: Test code, simulation config, gem5 version, spill detection algorithm
- ❌ **Different**: Only ISA (X86 vs RISC-V), binary compilation, instruction encoding

## 🏗️ Methodology

### Phase 1: Binary Compilation
```bash
# X86 Binary
cd x86_build/
gcc -static -o unified_test_x86 ../common/unified_spill_test.c

# RISC-V Binary  
cd riscv_build/
riscv64-unknown-elf-gcc -static -o unified_test_riscv ../common/unified_spill_test.c
```

### Phase 2: Simulation Execution
```bash
# X86 Simulation
cd x86_build/
../../build/X86/gem5.opt sim_x86.py

# RISC-V Simulation
cd riscv_build/  
../../build/RISCV/gem5.opt sim_riscv.py
```

### Phase 3: Results Analysis
```bash
# Compare spill counts
echo "X86 Spills: $(grep "^SPILL," x86_build/m5out/cpp_spill_log.txt | wc -l)"
echo "RISC-V Spills: $(grep "^RISCV_SPILL," riscv_build/m5out/riscv_spill_log.txt | wc -l)"

# Detailed analysis
python analysis/compare_results.py
```

## 📊 Expected Outcomes

### Hypothesis
- **X86**: Higher spill count due to complex addressing modes and variable instruction lengths
- **RISC-V**: Lower spill count due to regular instruction encoding and RISC design principles
- **Both**: Should show consistent patterns relative to their architectural characteristics

### Success Criteria
1. Both architectures successfully detect spills
2. Spill patterns reflect architectural differences
3. Algorithm behaves consistently across ISAs
4. Results are reproducible and scientifically valid

## 🔬 Scientific Controls

### Internal Validity
- Identical source code eliminates test bias
- Same simulation parameters control environment variables  
- Same gem5 version ensures consistent simulation engine
- Same spill detection algorithm eliminates implementation bias

### External Validity  
- Representative register pressure scenario
- Realistic compiler optimization levels
- Standard architectural configurations
- Generalizable to other spill detection studies

## 📈 Metrics

### Primary Metrics
- **Total Spill Count**: Number of detected spill events
- **Spill Rate**: Spills per instruction ratio
- **Memory Efficiency**: Spill events per memory operation

### Secondary Metrics
- **Spill Latency**: Average ticks between store-load pairs
- **Address Distribution**: Unique memory addresses involved
- **PC Hotspots**: Instruction locations with highest spill rates

This methodology ensures scientific rigor and fair comparison between architectures.
