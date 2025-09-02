#!/bin/bash
# SFK Complete Test Pipeline for Extensive Test
# Usage: ./test_sfk_pipeline.sh

echo "🧪 SFK INSTRUCTION SET EXTENSIVE TEST PIPELINE 🧪"
echo "================================================"

echo "Step 1: Compiling extensive test program..."
riscv64-unknown-elf-gcc -o test_sfk_extensive -nostartfiles test_sfk_extensive.s

if [ $? -ne 0 ]; then
    echo "❌ Assembly compilation failed!"
    exit 1
fi
echo "✅ Compilation successful: 'test_sfk_extensive' created."
echo ""

echo "Step 2: Running gem5 simulation and analyzing output..."
# The simulation output is piped to tee.
# tee saves the output to sfk_debug_output.txt AND passes it to the python script.
build/RISCV/gem5.opt configs/deprecated/example/se.py --cpu-type=TimingSimpleCPU -c test_sfk_extensive 2>&1 | tee sfk_debug_output.txt | python3 sfk_stats_analyzer.py

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "❌ gem5 simulation failed!"
    exit 1
fi

echo ""
echo "✅ SFK INSTRUCTION SET TEST COMPLETED SUCCESSFULLY!"
echo "📁 Full simulation log: sfk_debug_output.txt"
echo "� Analysis results have been printed above."
