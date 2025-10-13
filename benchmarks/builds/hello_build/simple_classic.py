#!/usr/bin/env python3
"""
Classic gem5 configuration (v21.0 style) - works with spill detector
"""

import m5
from m5.objects import *

# Create the system
system = System()

# Set clock and voltage
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "3GHz"
system.clk_domain.voltage_domain = VoltageDomain()

# Set memory mode and range
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("8GiB")]

# Create CPU (X86TimingSimpleCPU uses TimingSimpleCPU with spill detector)
system.cpu = X86TimingSimpleCPU()

# Create memory bus
system.membus = SystemXBar()

# Connect CPU directly to membus (no caches for simplicity)
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports

# Connect interrupt controller (X86 specific)
system.cpu.createInterruptController()
system.cpu.interrupts[0].pio = system.membus.mem_side_ports
system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports

# Connect system port
system.system_port = system.membus.cpu_side_ports

# Create memory controller
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# Set up the workload
binary = "benchmarks/builds/hello_build/hello_folks_x86"
system.workload = SEWorkload.init_compatible(binary)

process = Process()
process.cmd = [binary]
system.cpu.workload = process
system.cpu.createThreads()

# Instantiate and run
root = Root(full_system=False, system=system)
m5.instantiate()

print("Beginning simulation with spill detection!")
exit_event = m5.simulate()

print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")
