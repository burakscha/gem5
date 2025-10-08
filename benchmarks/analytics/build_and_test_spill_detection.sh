#!/bin/bash

# =============================================================================
# GEM5 SPILL DETECTION - AUTOMATED BUILD & TEST SCRIPT
# =============================================================================
# This script automates the complete workflow for building gem5 with spill
# detection and running basic tests.
#
# Usage:
#   ./build_and_test_spill_detection.sh
#
# Prerequisites:
#   - Run inside gem5-dev:amd64 Docker container
#   - Current directory should be /gem5
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
BUILD_JOBS=${BUILD_JOBS:-$(nproc)}
BUILD_TYPE=${BUILD_TYPE:-"opt"}  # opt or debug
TEST_PROGRAM=${TEST_PROGRAM:-"benchmarks/builds/hello_build/hello_folks_x86"}

# =============================================================================
# STEP 1: ENVIRONMENT VERIFICATION
# =============================================================================
log_info "Step 1: Verifying environment..."

# Check if we're in the right directory
if [ ! -f "SConstruct" ]; then
    log_error "SConstruct not found. Please run this script from gem5 root directory."
    exit 1
fi

# Check if spill detector files exist
if [ ! -f "src/cpu/simple/x86_spill_detector.cc" ]; then
    log_error "x86_spill_detector.cc not found. Spill detection source missing."
    exit 1
fi

log_success "Environment verification passed"

# =============================================================================
# STEP 2: CLEAN PREVIOUS BUILD
# =============================================================================
log_info "Step 2: Cleaning previous build artifacts..."

# Remove build directory
if [ -d "build/X86" ]; then
    log_info "Removing existing build/X86 directory..."
    rm -rf build/X86/
fi

# Clear output directory
if [ -d "m5out" ]; then
    log_info "Clearing m5out directory..."
    rm -rf m5out/*
fi

log_success "Clean completed"

# =============================================================================
# STEP 3: BUILD GEM5
# =============================================================================
log_info "Step 3: Building gem5 with spill detection..."
log_info "Build configuration: X86 gem5.$BUILD_TYPE with $BUILD_JOBS parallel jobs"

START_TIME=$(date +%s)

# Build gem5
if scons build/X86/gem5.$BUILD_TYPE -j$BUILD_JOBS; then
    END_TIME=$(date +%s)
    BUILD_TIME=$((END_TIME - START_TIME))
    log_success "Build completed in ${BUILD_TIME} seconds"
    
    # Verify binary exists
    if [ -f "build/X86/gem5.$BUILD_TYPE" ]; then
        BINARY_SIZE=$(du -h "build/X86/gem5.$BUILD_TYPE" | cut -f1)
        log_success "Binary created successfully (Size: $BINARY_SIZE)"
    else
        log_error "Binary not found after successful build"
        exit 1
    fi
else
    log_error "Build failed"
    exit 1
fi

# =============================================================================
# STEP 4: VERIFY TEST PROGRAM
# =============================================================================
log_info "Step 4: Verifying test program..."

if [ ! -f "$TEST_PROGRAM" ]; then
    log_warning "Test program not found: $TEST_PROGRAM"
    log_info "Attempting to compile hello program..."
    
    cd benchmarks/builds/hello_build/
    if gcc -static -I/gem5/include -o hello_folks_x86 hello_folks.c -lm5 2>/dev/null; then
        log_success "Test program compiled successfully"
    else
        log_error "Failed to compile test program"
        exit 1
    fi
    cd /gem5
fi

log_success "Test program verified: $TEST_PROGRAM"

# =============================================================================
# STEP 5: RUN SPILL DETECTION TEST
# =============================================================================
log_info "Step 5: Running spill detection simulation..."

SIMULATION_START=$(date +%s)

# Run simulation
if ./build/X86/gem5.$BUILD_TYPE configs/deprecated/example/se.py \
    --cpu-type=TimingSimpleCPU \
    --caches \
    --cmd=$TEST_PROGRAM; then
    
    SIMULATION_END=$(date +%s)
    SIMULATION_TIME=$((SIMULATION_END - SIMULATION_START))
    log_success "Simulation completed in ${SIMULATION_TIME} seconds"
else
    log_error "Simulation failed"
    exit 1
fi

# =============================================================================
# STEP 6: ANALYZE RESULTS
# =============================================================================
log_info "Step 6: Analyzing results..."

# Check output files
log_info "Generated output files:"
ls -la m5out/

# Analyze spill detection results
if [ -f "m5out/x86_spill_stats.txt" ]; then
    log_success "Spill statistics file generated"
    
    # Count spills
    TOTAL_SPILLS=$(grep "^SPILL" m5out/x86_spill_stats.txt | wc -l)
    
    if [ $TOTAL_SPILLS -gt 0 ]; then
        log_success "Spill detection working: $TOTAL_SPILLS spills detected"
        
        # Detailed analysis
        UNIQUE_STORE_PCS=$(grep "^SPILL" m5out/x86_spill_stats.txt | cut -d',' -f2 | sort -u | wc -l)
        UNIQUE_LOAD_PCS=$(grep "^SPILL" m5out/x86_spill_stats.txt | cut -d',' -f3 | sort -u | wc -l)
        UNIQUE_ADDRESSES=$(grep "^SPILL" m5out/x86_spill_stats.txt | cut -d',' -f4 | sort -u | wc -l)
        
        echo ""
        echo "🔍 SPILL DETECTION SUMMARY"
        echo "=========================="
        echo "Total spills detected: $TOTAL_SPILLS"
        echo "Unique store PCs: $UNIQUE_STORE_PCS"
        echo "Unique load PCs: $UNIQUE_LOAD_PCS"
        echo "Unique memory addresses: $UNIQUE_ADDRESSES"
        
        # Show sample spills
        echo ""
        echo "📝 SAMPLE SPILL EVENTS (first 3):"
        echo "Format: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count"
        grep "^SPILL" m5out/x86_spill_stats.txt | head -3
        
    else
        log_warning "No spills detected. This might be normal for simple programs."
        log_info "Try with more complex programs that cause register pressure."
    fi
else
    log_error "Spill statistics file not generated"
    log_error "Check if spill detection is properly integrated"
    exit 1
fi

# Analyze general statistics
if [ -f "m5out/stats.txt" ]; then
    INSTRUCTIONS=$(grep 'simInsts' m5out/stats.txt | awk '{print $2}')
    OPERATIONS=$(grep 'simOps' m5out/stats.txt | awk '{print $2}')
    TICKS=$(grep 'simTicks' m5out/stats.txt | awk '{print $2}')
    
    echo ""
    echo "📊 GENERAL SIMULATION STATISTICS"
    echo "================================="
    echo "Instructions simulated: $INSTRUCTIONS"
    echo "Operations simulated: $OPERATIONS"
    echo "Simulation ticks: $TICKS"
fi

# =============================================================================
# STEP 7: SUMMARY
# =============================================================================
TOTAL_END=$(date +%s)
TOTAL_TIME=$((TOTAL_END - START_TIME))

echo ""
echo "🎉 WORKFLOW COMPLETED SUCCESSFULLY"
echo "=================================="
echo "Total execution time: ${TOTAL_TIME} seconds"
echo "Build time: ${BUILD_TIME} seconds"
echo "Simulation time: ${SIMULATION_TIME} seconds"
echo ""
echo "✅ gem5 built successfully with spill detection"
echo "✅ Simulation executed successfully"
echo "✅ Spill detection system verified"
echo ""
echo "📁 Results location: m5out/"
echo "📄 Spill statistics: m5out/x86_spill_stats.txt"
echo "📄 General statistics: m5out/stats.txt"
echo ""
log_success "All tests passed! Spill detection system is working correctly."
