# Register Spill Detection: Complete Build & Test Guide

This guide provides step-by-step instructions for building gem5 from scratch and testing the register spill detection system.

## Prerequisites

- Docker installed and running
- Linux x86_64 environment (via Docker for Apple Silicon Macs)
- At least 8GB free disk space for build
- At least 8GB RAM for compilation

## Overview

The register spill detection system consists of:
- **X86 Spill Detector**: Architecture-specific implementation for x86
- **TimingSimpleCPU Integration**: CPU model with spill tracking
- **ROI Support**: Region of Interest tracking with m5 pseudo instructions
- **Statistics Output**: Detailed spill event logging

## Step 1: Environment Setup

### 1.1 Start Docker Container
```bash
docker run -it --rm -v $(pwd):/gem5 -w /gem5 gem5-dev:amd64
```

### 1.2 Navigate to gem5 Directory
```bash
cd /gem5
```

### 1.3 Verify Source Files
```bash
# Check spill detector files exist
ls -la src/cpu/simple/x86_spill_detector.*
ls -la src/cpu/simple/timing.hh
ls -la src/sim/pseudo_inst.cc
```

Expected output:
```
-rw-r--r-- 1 root root 11554 Oct  7 22:35 src/cpu/simple/x86_spill_detector.cc
-rw-r--r-- 1 root root  6129 Oct  7 22:35 src/cpu/simple/x86_spill_detector.hh
-rw-r--r-- 1 root root 13847 Oct  7 22:35 src/cpu/simple/timing.hh
-rw-r--r-- 1 root root 17234 Oct  7 22:35 src/sim/pseudo_inst.cc
```

## Step 2: Clean Previous Build

### 2.1 Remove Previous Build Artifacts
```bash
# Remove X86 build directory
rm -rf build/X86/

# Clear previous simulation outputs
rm -rf m5out/*

# Verify clean state
echo "Build directory cleaned: $([ ! -d build/X86 ] && echo 'SUCCESS' || echo 'FAILED')"
echo "Output directory cleaned: $([ -z "$(ls -A m5out 2>/dev/null)" ] && echo 'SUCCESS' || echo 'FAILED')"
```

## Step 3: Build gem5 with Spill Detection

### 3.1 Start Build Process
```bash
# Build X86 gem5.opt with maximum parallelism
echo "Starting build at: $(date)"
scons build/X86/gem5.opt -j$(nproc)
echo "Build completed at: $(date)"
```

### 3.2 Verify Build Success
```bash
# Check if binary was created
if [ -f build/X86/gem5.opt ]; then
    echo "✅ Build SUCCESS"
    ls -lh build/X86/gem5.opt
    echo "Binary size: $(du -h build/X86/gem5.opt | cut -f1)"
else
    echo "❌ Build FAILED"
    exit 1
fi
```

Expected output:
```
✅ Build SUCCESS
-rwxr-xr-x 1 root root 834M Oct  8 10:30 build/X86/gem5.opt
Binary size: 834M
```

## Step 4: Prepare Test Programs

### 4.1 Basic Hello World Test
```bash
cd benchmarks/builds/hello_build/

# Verify hello program source
cat hello_folks.c
```

### 4.2 Compile Test Program (if needed)
```bash
# Compile hello program with m5 support
gcc -static -I/gem5/include -o hello_folks_x86 hello_folks.c -lm5

# Verify compilation
if [ -f hello_folks_x86 ]; then
    echo "✅ Test program compiled successfully"
    ls -la hello_folks_x86
else
    echo "❌ Test program compilation failed"
fi
```

### 4.3 Return to gem5 Root
```bash
cd /gem5
```

## Step 5: Run Spill Detection Test

### 5.1 Execute Simulation
```bash
echo "🚀 Starting spill detection simulation..."
echo "Simulation started at: $(date)"

./build/X86/gem5.opt configs/deprecated/example/se.py \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --cmd=benchmarks/builds/hello_build/hello_folks_x86

echo "Simulation completed at: $(date)"
```

### 5.2 Verify Simulation Success
```bash
# Check if simulation produced output
if [ $? -eq 0 ]; then
    echo "✅ Simulation completed successfully"
else
    echo "❌ Simulation failed"
    exit 1
fi
```

## Step 6: Analyze Results

### 6.1 Check Output Files
```bash
echo "📁 Generated output files:"
ls -la m5out/
echo ""
```

### 6.2 Spill Detection Analysis
```bash
echo "🔍 SPILL DETECTION ANALYSIS"
echo "================================"

# Check if spill stats file exists
if [ -f m5out/x86_spill_stats.txt ]; then
    echo "✅ Spill stats file generated"
    
    # Count total spills
    TOTAL_SPILLS=$(grep "^SPILL" m5out/x86_spill_stats.txt | wc -l)
    echo "📊 Total spills detected: $TOTAL_SPILLS"
    
    if [ $TOTAL_SPILLS -gt 0 ]; then
        echo "✅ Spill detection is working correctly"
        
        # Detailed statistics
        echo ""
        echo "📈 DETAILED STATISTICS:"
        echo "------------------------"
        echo "Unique store PCs: $(grep "^SPILL" m5out/x86_spill_stats.txt | cut -d',' -f2 | sort -u | wc -l)"
        echo "Unique load PCs: $(grep "^SPILL" m5out/x86_spill_stats.txt | cut -d',' -f3 | sort -u | wc -l)"
        echo "Unique memory addresses: $(grep "^SPILL" m5out/x86_spill_stats.txt | cut -d',' -f4 | sort -u | wc -l)"
        
        # Show first few spills
        echo ""
        echo "🎯 FIRST 5 DETECTED SPILLS:"
        echo "----------------------------"
        echo "Format: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count"
        grep "^SPILL" m5out/x86_spill_stats.txt | head -5
        
    else
        echo "⚠️  No spills detected - check if ROI is properly activated"
    fi
else
    echo "❌ Spill stats file not generated"
    echo "Check if spill detection is properly integrated"
fi
```

### 6.3 General Simulation Statistics
```bash
echo ""
echo "📊 GENERAL SIMULATION STATISTICS:"
echo "==================================="
if [ -f m5out/stats.txt ]; then
    echo "Instructions simulated: $(grep 'simInsts' m5out/stats.txt | awk '{print $2}')"
    echo "Operations simulated: $(grep 'simOps' m5out/stats.txt | awk '{print $2}')"
    echo "Simulation ticks: $(grep 'simTicks' m5out/stats.txt | awk '{print $2}')"
else
    echo "❌ General stats file not found"
fi
```

## Step 7: Advanced Testing

### 7.1 Test with Different Programs
```bash
# Test with gem5's hello program
echo "🧪 Testing with gem5's built-in hello program..."
./build/X86/gem5.opt configs/deprecated/example/se.py \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --cmd=tests/test-progs/hello/bin/x86/linux/hello

# Compare results
echo "Spills with built-in hello: $(grep "^SPILL" m5out/x86_spill_stats.txt | wc -l)"
```

### 7.2 Test with Matrix Program (if available)
```bash
if [ -f benchmarks/builds/x86_build/matrix_spill ]; then
    echo "🧮 Testing with matrix multiplication program..."
    ./build/X86/gem5.opt configs/deprecated/example/se.py \
        --cpu-type=TimingSimpleCPU \
        --caches \
        --cmd=benchmarks/builds/x86_build/matrix_spill
    
    echo "Spills with matrix program: $(grep "^SPILL" m5out/x86_spill_stats.txt | wc -l)"
fi
```

## Step 8: Debug Mode (Optional)

### 8.1 Build Debug Version
```bash
echo "🐛 Building debug version for detailed analysis..."
scons build/X86/gem5.debug -j$(nproc)
```

### 8.2 Run with Debug Flags
```bash
echo "🔍 Running debug simulation..."
./build/X86/gem5.debug \
    --debug-flags=SpillDetector \
    configs/deprecated/example/se.py \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --cmd=benchmarks/builds/hello_build/hello_folks_x86
```

## Troubleshooting

### Common Issues and Solutions

1. **Build Fails with Missing Dependencies**
   ```bash
   # Update package lists and install missing packages
   apt-get update
   apt-get install -y build-essential python3-dev
   ```

2. **Spill Stats File Not Generated**
   - Check if ROI markers (m5_work_begin/end) are in your test program
   - Verify TimingSimpleCPU is being used
   - Check if x86_spill_detector.cc is properly compiled

3. **No Spills Detected**
   - Use more complex programs that cause register pressure
   - Check if the program actually executes code within ROI
   - Verify spill detection logic in isLikelySpill() method

4. **Simulation Crashes**
   - Check memory configuration in se.py
   - Verify test program is properly compiled and statically linked
   - Use debug build for more detailed error messages

## File Locations

- **Spill Detector Source**: `src/cpu/simple/x86_spill_detector.{cc,hh}`
- **CPU Integration**: `src/cpu/simple/timing.{cc,hh}`
- **Pseudo Instructions**: `src/sim/pseudo_inst.cc`
- **Build Configuration**: `src/cpu/simple/SConscript`
- **Test Programs**: `benchmarks/builds/hello_build/`
- **Results**: `m5out/x86_spill_stats.txt`

## Expected Timeline

- **Clean + Build**: 15-30 minutes (depending on CPU cores)
- **Simple Test**: 1-2 minutes
- **Analysis**: 1-2 minutes
- **Total**: ~20-35 minutes for complete workflow

## Success Criteria

✅ **Build Success**: `build/X86/gem5.opt` binary created (~800MB)  
✅ **Simulation Success**: Program executes and prints output  
✅ **Spill Detection**: `x86_spill_stats.txt` contains detected spills  
✅ **Statistics**: Reasonable number of spills for test program complexity  

---

**Last Updated**: October 8, 2025  
**Tested Environment**: Docker container with gem5-dev:amd64  
**gem5 Version**: 25.0.0.0
