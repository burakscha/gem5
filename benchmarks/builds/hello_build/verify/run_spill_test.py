#!/usr/bin/env python3
"""
Run pure assembly spill test
"""

import m5
from m5.objects import *

# Binary path
binary = "benchmarks/builds/hello_build/verify/pure_asm_spill_x86"

print(f"Running pure assembly spill test: {binary}")

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

# Interrupt controller
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
print("🧪 Assembly Spill Verification Test")
print("=" * 70)
print("Expected spills: 9 (1 + 3 + 5)")
print("=" * 70)

exit_event = m5.simulate()

print("=" * 70)
print(f"✅ Simulation finished @ tick {m5.curTick()}")
print(f"   Reason: {exit_event.getCause()}")
print("=" * 70)
print("\n📊 Check results:")
print("   m5out/x86_spill_stats.txt - Should show exactly 9 spills")
print("=" * 70)
