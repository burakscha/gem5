# Fair Cross-Architecture Register Spill Comparison

## Objective
Compare register spill behavior between X86 and RISC-V architectures using identical test conditions.

## Methodology

### Test Program Design
- **File**: `unified_spill_test.c`
- **Variables**: 25 integer variables for maximum register pressure
- **Iterations**: 150 loops for measurable spill generation
- **Complexity**: Multi-level arithmetic dependencies

### Compilation Strategy
- **Optimization**: `-O0` (no optimization) for both architectures
- **Linking**: `-static` for standalone execution
- **Flags**: Identical compiler flags for fair comparison

### Expected Compilation Commands

#### X86 Compilation:
```bash
cd x86_build/
gcc -O0 -static -o x86_unified_test ../common/unified_spill_test.c
```

#### RISC-V Compilation:
```bash
cd riscv_build/
riscv64-linux-gnu-gcc -O0 -static -o riscv_unified_test ../common/unified_spill_test.c
```

### Simulation Configuration
- **gem5 CPU**: TimingSimpleCPU for both architectures
- **Spill Detection**: MAX_SPILL_WINDOW = 100,000 ticks
- **Memory**: Identical memory hierarchy
- **Cache**: Same cache configuration

### Analysis Framework
Results will be compared in `analysis/` directory:
- Spill count comparison
- Spill rate analysis
- Architecture-specific patterns
- Performance impact assessment

## Scientific Controls
1. **Single Source Code**: Same C file for both architectures
2. **Identical Flags**: Same compilation options
3. **Same gem5 Config**: Identical simulation parameters
4. **Controlled Variables**: Only ISA differences matter

This ensures any differences in spill behavior are due to architectural characteristics, not implementation variations.
