#!/bin/bash
# gem5 RISC-V Simulator Build Script
# gem5 itself runs on x86-64, simulates RISC-V

set -e

echo "🧹 Cleaning environment..."
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH

echo "🐍 Setting Python paths..."
export CPATH="$CONDA_PREFIX/include:$CONDA_PREFIX/include/python3.10"
export C_INCLUDE_PATH="$CPATH"
export CPLUS_INCLUDE_PATH="$CPATH"
export LIBRARY_PATH="$CONDA_PREFIX/lib"
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

echo "🔧 Removing RISC-V cross-compiler from PATH..."
export PATH=$(echo $PATH | tr ':' '\n' | grep -v '/cta/research/level0/RISCV' | tr '\n' ':' | sed 's/:$//')
export PATH="$CONDA_PREFIX/bin:$PATH"

echo "✅ Using compiler:"
/usr/bin/gcc --version | head -1

echo "🔨 Building gem5..."
rm -rf build/RISCV

scons build/RISCV/gem5.opt -j12 \
    CC=/usr/bin/gcc \
    CXX=/usr/bin/g++ \
    PYTHON_CONFIG=$CONDA_PREFIX/bin/python3-config

echo "✅ Build complete!"
echo "gem5 executable: build/RISCV/gem5.opt"
