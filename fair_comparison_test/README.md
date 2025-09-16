# Fair Cross-Architecture Register Spill Comparison

## 🎯 **Project Overview**
This project implements a professional architecture-aware register spill detection system for gem5, enabling fair comparison between X86 and RISC-V architectures using identical test conditions.

## 🏗️ **Architecture-Aware Spill Detection System**

### 📁 **System Components**
- **X86 Spill Detector**: `src/cpu/simple/x86_spill_detector.cc` (16 GPRs, CISC-aware)
- **RISC-V Spill Detector**: `src/cpu/simple/riscv_spill_detector.cc` (32 GPRs, RISC-aware)
- **Fallback Detector**: `src/cpu/simple/spill_detector.cc` (Other architectures)
- **Build System Integration**: `src/cpu/simple/SConscript` (Automatic selection)

### 🔧 **Professional Build System**
- **SCons Integration**: Uses `env['CONF']['USE_X86_ISA']` and `env['CONF']['USE_RISCV_ISA']` flags
- **Automatic Selection**: Build system automatically selects appropriate spill detector
- **Clean Architecture**: No conditional compilation in source code
- **Gemini's Approach**: Most professional method for gem5 integration

## 🧪 **Unified Test Framework**

### 📋 **Test Program Characteristics**
- **File**: `common/unified_spill_test.c`
- **Architecture-Agnostic**: Pure C code (no stdio.h dependency)
- **Register Pressure**: 25 integer variables for maximum stress
- **Computation Load**: 150 iterations for measurable spill generation
- **Cross-Dependencies**: Complex arithmetic patterns to force spilling
- **Fair Comparison**: Identical compilation with `-O0` flag

### 🔄 **Build & Execution Workflow**
- **X86 Build**: `scons build/X86/gem5.opt -j12` → Selects `x86_spill_detector.cc`
- **RISC-V Build**: `scons build/RISCV/gem5.opt -j12` → Selects `riscv_spill_detector.cc`
- **Test Execution**: Both architectures run identical `unified_spill_test` program

## 📊 **Expected Results**

### 🎯 **Architecture Differences**
- **X86 (CISC)**: Higher spill count due to 16 GPRs and complex addressing
- **RISC-V (RISC)**: Lower spill count due to 32 GPRs and simple instructions
- **Fair Analysis**: Same program reveals true architectural differences

## 🚀 **Current Implementation Status**

### ✅ **Completed Features**
1. **Architecture-Specific Spill Detectors** → Implemented for X86 and RISC-V
2. **Professional Build System** → SCons integration with automatic selection
3. **Unified Test Framework** → Cross-architecture test program ready
4. **Clean Repository Structure** → All legacy files removed, organized codebase
5. **Git Integration** → Clean commit with professional architecture

### 🔄 **Next Steps**
1. **Compile Test Program** → Create binaries for both architectures
2. **Execute X86 Simulation** → Validate X86 spill detector functionality
3. **Execute RISC-V Simulation** → Validate RISC-V spill detector functionality
4. **Compare Results** → Analyze architectural spill differences
5. **Generate Report** → Document findings and performance analysis

## 📁 **File Structure**

```
fair_comparison_test/
├── README.md                           # This comprehensive guide
├── BINARY_STATUS.md                    # Pre-compiled binary information
├── common/
│   ├── unified_spill_test.c           # Cross-architecture test program
│   └── README.md                       # Test program documentation
├── x86_build/
│   └── unified_x86_static             # Pre-compiled X86 binary
├── riscv_build/
│   └── unified_riscv_static           # Pre-compiled RISC-V binary
└── analysis/                          # Results and analysis (future)
```

## 🛠️ **Usage Instructions**

### **Method 1: Use Pre-compiled Binaries**
```bash
# X86 Simulation
./build/X86/gem5.opt configs/deprecated/example/se.py \
  --cmd=fair_comparison_test/x86_build/unified_x86_static \
  --mem-size=2GB --caches --l2cache

# RISC-V Simulation  
./build/RISCV/gem5.opt configs/deprecated/example/se.py \
  --cmd=fair_comparison_test/riscv_build/unified_riscv_static \
  --mem-size=2GB --caches --l2cache
```

### **Method 2: Compile from Source**
```bash
# X86 Compilation
cd fair_comparison_test/x86_build/
gcc -O0 -static -o unified_x86_test ../common/unified_spill_test.c

# RISC-V Compilation
cd fair_comparison_test/riscv_build/
riscv64-linux-gnu-gcc -O0 -static -o unified_riscv_test ../common/unified_spill_test.c
```

## 🔬 **Technical Specifications**

### **Spill Detection Parameters**
- **Sensitivity**: MAX_SPILL_WINDOW = 100,000 ticks
- **Architecture-Specific**: X86 (16 GPR) vs RISC-V (32 GPR) optimizations
- **Logging**: Real-time spill events logged to `m5out/cpp_spill_log.txt`

### **Simulation Configuration**
- **CPU Model**: TimingSimpleCPU for accurate timing simulation
- **Memory Hierarchy**: Identical L1/L2 cache configuration
- **System Call Emulation**: SE mode for user-space program execution

## 📈 **Professional Implementation Notes**

This implementation follows **Gemini's recommended approach** for clean architecture:
- ✅ **No conditional compilation** in source files
- ✅ **SCons-based automatic selection** of spill detectors
- ✅ **Clean separation** of architecture-specific logic
- ✅ **Professional gem5 integration** using standard environment flags
- Spill rate analysis
- Architecture-specific patterns
- Performance impact assessment

## Scientific Controls
1. **Single Source Code**: Same C file for both architectures
2. **Identical Flags**: Same compilation options
3. **Same gem5 Config**: Identical simulation parameters
4. **Controlled Variables**: Only ISA differences matter

This ensures any differences in spill behavior are due to architectural characteristics, not implementation variations.
