# X86 Matrix Spill Test Configuration
# This config runs our matrix spill test for X86 architecture

import m5
import sys
import os
from m5.objects import *

# Create the system
system = System()

# Set clock frequency
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "1GHz"
system.clk_domain.voltage_domain = VoltageDomain()

# Set memory size
system.mem_ranges = [AddrRange("512MiB")]

# Create X86 CPU
system.cpu = X86TimingSimpleCPU()

# Create memory bus
system.membus = SystemXBar()

# Connect CPU caches to memory bus
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports

# Create interrupt controllers for x86
system.cpu.createInterruptController()

# For x86, connect interrupts to the IO bus
system.cpu.interrupts[0].pio = system.membus.mem_side_ports
system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports

# Create memory controller
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# Connect system port to memory bus
system.system_port = system.membus.cpu_side_ports

# Set binary path - our X86 matrix test
thispath = os.path.dirname(os.path.realpath(__file__))
binary_path = os.path.join(thispath, "x86_matrix_linux")

# Check if binary exists, otherwise use default hello
if os.path.exists(binary_path):
    binary = binary_path
    print(f"Using X86 matrix test: {binary}")
else:
    binary = os.path.join(thispath, "../../tests/test-progs/hello/bin/x86/linux/hello")
    print(f"Matrix binary not found, using default: {binary}")

system.workload = SEWorkload.init_compatible(binary)

# Create process
process = Process()
process.cmd = [binary]
system.cpu.workload = process
system.cpu.createThreads()

# Set up simulation
root = Root(full_system=False, system=system)
m5.instantiate()

print("Beginning X86 Matrix Spill Test!")
exit_event = m5.simulate()
print(f"X86 simulation finished @ tick {m5.curTick()} because {exit_event.getCause()}")
