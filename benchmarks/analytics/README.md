# Gem5 Spill Detection Analytics Tools

This directory contains tools for analyzing gem5 spill detection simulation results.

## Files

### 1. `advanced_spill_analysis.py` (NEW - RECOMMENDED)
**Advanced Python analysis tool** - Includes comprehensive spill metrics and optimization recommendations.

#### Features:
- ✅ **Simulation Configuration**: ISA (X86/ARM/RISCV), CPU type, core count, clock frequency
- ✅ Basic spill statistics
- ✅ **Spill Density**: How many spills per 1000 instructions
- ✅ **Memory Pressure**: Stack frame size and address usage
- ✅ **Code Locality**: Distribution of spills within code
- ✅ **Reload Efficiency**: Cache performance indicator
- ✅ **Register Pressure Indicator**: Number of spills per unit time
- ✅ **Hot Spot Concentration**: Most frequently spilling PCs
- ✅ Automatic optimization recommendations
- ✅ Generates `analysis_report.txt` file

#### Usage:

**Method 1: Static Parameter (Recommended)**
```bash
# 1. Open file and update M5OUT_DIRECTORY variable
vim benchmarks/analytics/advanced_spill_analysis.py
# M5OUT_DIRECTORY = "results5out/m5out_verify_x86/"

# 2. Run (without arguments)
python3 benchmarks/analytics/advanced_spill_analysis.py
```

**Method 2: Command Line Argument (Override)**
```bash
# Run with direct parameter
python3 benchmarks/analytics/advanced_spill_analysis.py <m5out_directory>

# Example 1: Default m5out
python3 benchmarks/analytics/advanced_spill_analysis.py m5out

# Example 2: Custom directory
python3 benchmarks/analytics/advanced_spill_analysis.py results5out/m5out_verify_x86

# Example 3: Different test results
python3 benchmarks/analytics/advanced_spill_analysis.py results/x86_matrix_spill_m5out_roi
```

#### Output:
- Prints detailed report to terminal
- Creates `<m5out_directory>/analysis_report.txt` file
- Shows optimization opportunities with 6 different metrics
- **Re-run command at the top of report file** (can be copied and pasted)

#### Report Format:
```
# ==============================================================================
# 🔄 Re-run Analysis Command:
#    python3 benchmarks/analytics/advanced_spill_analysis.py results5out/m5out_verify_x86/
# ==============================================================================
```
This command is at the top of the report file and can be copied to re-run the analysis.

---

### 2. `analyze_spill_results.sh`
**Shell script-based analysis tool** - For quick CLI analysis.

#### Features:
- Basic spill statistics
- Timing analysis
- Hotspot analysis
- Memory address usage
- Pattern analysis
- Creates `<m5out_dir>/shell_analysis_report.txt` file

#### Usage:
```bash
# Basic usage
./benchmarks/analytics/analyze_spill_results.sh <m5out_directory>

# Example 1: Default m5out
./benchmarks/analytics/analyze_spill_results.sh m5out

# Example 2: Custom directory
./benchmarks/analytics/analyze_spill_results.sh results5out/m5out_verify_x86
```

#### Output:
- Prints detailed analysis to terminal
- Creates `<m5out_directory>/shell_analysis_report.txt` file

---

### 3. `analyze_m5out.py`
**Original Python analysis tool** - General-purpose m5out analysis.

#### Usage:
```bash
python3 benchmarks/analytics/analyze_m5out.py <m5out_directory>
```

---

## Which Tool Should I Use?

| Need | Recommended Tool |
|------|------------------|
| **Advanced spill analysis** | `advanced_spill_analysis.py` ⭐ |
| **Optimization recommendations** | `advanced_spill_analysis.py` ⭐ |
| **Quick CLI check** | `analyze_spill_results.sh` |
| **General m5out analysis** | `analyze_m5out.py` |

---

## Advanced Metrics Explanation

### 1. **Spill Density**
- **Definition**: How many spills occur per 1000 instructions
- **Good value**: < 1 (excellent), < 10 (moderate)
- **Bad value**: > 10 (high register pressure)

### 2. **Memory Pressure**
- **Definition**: How many different memory addresses are used per spill
- **Good value**: < 0.5 (same addresses reused)
- **Bad value**: ≈ 1.0 (each spill uses different address, large stack frame)

### 3. **Code Locality**
- **Definition**: Average number of spills per store PC
- **Good value**: > 10 (concentrated in loops, can be optimized)
- **Bad value**: < 2 (spills scattered)

### 4. **Reload Efficiency**
- **Definition**: Average store-to-load tick difference (latency)
- **Good value**: < 100 ticks (L1 cache hit)
- **Moderate value**: 100-1000 ticks (L2/L3 cache)
- **Bad value**: > 1000 ticks (memory access, cache miss)

### 5. **Register Pressure Indicator**
- **Definition**: How many spills occur per second
- **Good value**: < 1000 (low pressure)
- **Bad value**: > 10000 (high pressure, optimization needed)

### 6. **Hot Spot Concentration**
- **Definition**: Percentage of total spills from top 5 store PCs
- **Good value**: > 80% (easy to optimize, concentrated)
- **Bad value**: < 50% (spills scattered)

---

## Example Workflow

```bash
# 1. Run simulation
build/X86/gem5.opt benchmarks/builds/test/verify/run_spill_test.py

# 2. Quick check (shell script)
./benchmarks/analytics/analyze_spill_results.sh m5out

# 3. Detailed analysis (Python, recommended)
python3 benchmarks/analytics/advanced_spill_analysis.py m5out

# 4. Read report
cat m5out/analysis_report.txt

# 5. Compare different optimization levels
python3 benchmarks/analytics/advanced_spill_analysis.py results_O0/m5out
python3 benchmarks/analytics/advanced_spill_analysis.py results_O3/m5out

# 6. Compare with diff
diff results_O0/m5out/analysis_report.txt results_O3/m5out/analysis_report.txt
```

---

## Requirements

- Python 3.6+
- Bash shell
- gem5 spill detector active simulation (`X86TimingSimpleCPU`)
- `x86_spill_stats.txt` and `stats.txt` files

---

## Troubleshooting

### File Not Found Error
```bash
❌ Error: Directory not found: m5out
```
**Solution**: Specify the correct m5out directory:
```bash
python3 benchmarks/analytics/advanced_spill_analysis.py results5out/m5out_verify_x86
```

### Empty Spill File
```bash
⚠️ Spill stats file is empty
```
**Solution**:
1. Check if ROI (Region of Interest) is active in simulation
2. Verify `m5_workbegin()` and `m5_workend()` calls
3. Make sure the binary is compiled correctly

---

## Information Extracted from Config.json

`advanced_spill_analysis.py` automatically extracts the following information from the `config.json` file:

### Simulation Configuration:
- **ISA Architecture**: X86, ARM, RISCV, MIPS, SPARC, POWER
- **CPU Type**: TimingSimpleCPU, O3CPU, MinorCPU, AtomicSimpleCPU, etc.
- **Number of Cores**: Single or multi-core simulation
- **Clock Frequency**: Clock speed in GHz
- **Memory Mode**: timing, atomic, etc.
- **Memory Size**: Total memory in GB
- **Cache Line Size**: Cache line size in bytes

This information is displayed in the **"SIMULATION CONFIGURATION"** section of the report and can be used to compare different configurations.

### Example Output:
```
⚙️  SIMULATION CONFIGURATION
--------------------------------------------------------------------------------
  ISA Architecture:                              X86
  CPU Type:                          BaseTimingSimpleCPU
  Number of Cores:                                 1
  Clock Frequency:                              3.00 GHz
  Memory Mode:                                timing
  Memory Size:                                  8.00 GB
  Cache Line Size:                                64 bytes
```

---

## More Information

- Spill detector source code: `src/cpu/simple/timing.cc`
- Test files: `benchmarks/builds/hello_build/verify/`
- Documentation: `REGISTER_SPILL_README.md`
