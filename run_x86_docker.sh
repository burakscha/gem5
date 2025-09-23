#!/bin/bash

# Docker x86 Container for gem5 X86 Simulation
# This script starts an x86 Ubuntu container, installs dependencies, and builds gem5

echo "🚀 Starting x86 Docker container for gem5 simulation..."

docker run --rm -it --platform linux/amd64 \
  -v "$(pwd)":/workspace -w /workspace ubuntu:24.04 bash -c "
    echo '📦 Installing dependencies...'
    apt-get update && \
    apt-get install -y build-essential gcc-multilib file python3 python3-pip scons m4 zlib1g-dev libprotobuf-dev protobuf-compiler libgoogle-perftools-dev libboost-all-dev pkg-config && \
    echo '🔨 Building gem5 X86...'
    scons build/X86/gem5.opt -j\$(nproc) && \
    echo '✅ gem5 X86 build completed!'
    echo '🎯 Ready to run simulations!'
    echo 'Example: ./build/X86/gem5.opt configs/deprecated/example/se.py -c fair_comparison/hello_build/hello_folks --cpu-type=TimingSimpleCPU'
    exec bash
"
