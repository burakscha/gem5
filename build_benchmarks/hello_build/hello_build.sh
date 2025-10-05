#!/bin/bash

echo "🧪 Testing Hello Folks with Spill Detection (Docker)"
echo "=================================================="

# Clean previous outputs
echo "🧹 Cleaning previous outputs..."
rm -rf m5out
rm -f fair_comparison/hello_build/hello_folks_x86

# Run everything in Docker
echo "🐳 Running in Docker container..."
docker run --rm --platform linux/amd64 \
  -v "$(pwd)/../..":/workspace -w /workspace ubuntu:24.04 bash -c "
    echo '🔨 Installing dependencies...'
    apt-get update -qq && \
    apt-get install -y -qq build-essential gcc-multilib file python3 python3-pip scons m4 zlib1g-dev libprotobuf-dev protobuf-compiler libgoogle-perftools-dev libboost-all-dev pkg-config && \
    echo '🔨 Building m5 library...'
    cd util/m5 && \
    rm -rf build && \
    scons ABI=x86 && \
    cd ../.. && \
    echo '🔨 Compiling hello_folks.c...'
    gcc -I include -L util/m5/build/x86/out -o fair_comparison/hello_build/hello_folks_x86 fair_comparison/hello_build/hello_folks.c -lm5 -static && \
    echo '🔨 Building gem5...'
    scons build/X86/gem5.opt -j\$(nproc) && \
    echo '🚀 Running gem5 simulation with spill detection...'
    mkdir -p m5out/fs && \
    build/X86/gem5.opt configs/deprecated/example/se.py \
        --cpu-type=TimingSimpleCPU --caches \
        -c fair_comparison/hello_build/hello_folks_x86 && \
    echo '✅ Simulation completed successfully'
"

# Check spill detection output
echo ""
echo "🔍 Checking spill detection output..."
if [ -f "m5out/x86_spill_stats.txt" ]; then
    echo "✅ x86_spill_stats.txt found"
    
    # Count spill events
    spill_count=$(grep "^SPILL" m5out/x86_spill_stats.txt | wc -l)
    echo "📊 Total spills detected: $spill_count"
    
    # Show first 20 lines
    echo ""
    echo "📋 First 20 lines of spill stats:"
    head -20 m5out/x86_spill_stats.txt
    
else
    echo "❌ x86_spill_stats.txt NOT found"
    echo "📁 Files in m5out/:"
    ls -la m5out/
fi

echo ""
echo "🎯 Test completed!"
