#!/usr/bin/env python3
"""
Run x86 matrix multiplication spill test with gem5

Usage:
    docker run --rm -v "$(pwd)":/workspace/gem5 -w /workspace/gem5 \
        gem5-universal:latest \
        build/X86/gem5.opt benchmarks/builds/x86_build/run_x86_matrix_spill.py

This script simulates matrix_spill_x86 binary and detects register spills.
"""

import m5
from m5.objects import *

# Binary path (using -O0 version to force register spills)
binary = "benchmarks/builds/x86_build/matrix_spill_x86_O0"

print(f"Running X86 matrix spill test: {binary}")

# Create system
system = System()
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "3GHz"
system.clk_domain.voltage_domain = VoltageDomain()
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("8GiB")]

# CPU with spill detection
system.cpu = X86TimingSimpleCPU()

# Memory bus
system.membus = SystemXBar()
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports

# Interrupt controller for X86
system.cpu.createInterruptController()
system.cpu.interrupts[0].pio = system.membus.mem_side_ports
system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports

# System port
system.system_port = system.membus.cpu_side_ports

# Memory controller
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# Load binary
system.workload = SEWorkload.init_compatible(binary)
process = Process()
process.cmd = [binary]
system.cpu.workload = process
system.cpu.createThreads()

# Run simulation
root = Root(full_system=False, system=system)
m5.instantiate()

print("=" * 70)
print("🧪 X86 Matrix Multiplication Spill Detection Test")
print("=" * 70)
print("Binary: matrix_spill_x86")
print("Matrix size: 256x256")
print("Expected: Register spills during matrix multiplication")
print("=" * 70)

exit_event = m5.simulate()

print("=" * 70)
print(f"✅ Simulation finished @ tick {m5.curTick()}")
print(f"   Reason: {exit_event.getCause()}")
print("=" * 70)
print("\n📊 Check results:")
print("   m5out/x86_spill_stats.txt - Contains detected spill information")
print("=" * 70)
