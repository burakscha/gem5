#!/bin/bash
# SFK Complete Test Pipeline
# Usage: ./test_sfk_pipeline.sh

echo "🧪 SFK INSTRUCTION SET TEST PIPELINE 🧪"
echo "========================================"

echo "Step 1: Running gem5 simulation..."
build/RISCV/gem5.opt configs/deprecated/example/se.py -c test_sfk > sfk_debug_output.txt 2>&1

if [ $? -ne 0 ]; then
    echo "❌ gem5 simulation failed!"
    exit 1
fi

echo "Step 2: Extracting SFK debug output..."
grep "SFK_" sfk_debug_output.txt
sfk_count=$(grep "SFK_" sfk_debug_output.txt | wc -l)

if [ $sfk_count -eq 0 ]; then
    echo "❌ No SFK instructions found!"
    exit 1
fi

echo "Step 3: Running stats analyzer..."
python3 sfk_stats_analyzer.py sfk_debug_output.txt

if [ $? -ne 0 ]; then
    echo "❌ Stats analyzer failed!"
    exit 1
fi

echo "Step 4: Test Results:"
echo "===================="
head -25 m5out/sfk_stats_interpreted.txt

echo ""
echo "✅ SFK INSTRUCTION SET TEST COMPLETED SUCCESSFULLY!"
echo "📁 Full report: m5out/sfk_stats_interpreted.txt"
echo "📁 Debug output: sfk_debug_output.txt"
