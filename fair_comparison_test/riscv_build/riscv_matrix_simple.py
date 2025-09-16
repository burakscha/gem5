# RISC-V Matrix Spill Test Configuration
# This config runs our matrix spill test for RISC-V architecture

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

# Create RISC-V CPU
system.cpu = RiscvTimingSimpleCPU()

# Create memory bus
system.membus = SystemXBar()

# Connect CPU caches to memory bus
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports

# Create memory controller
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# Connect system port to memory bus
system.system_port = system.membus.cpu_side_ports

# Set binary path - our RISC-V matrix test
thispath = os.path.dirname(os.path.realpath(__file__))
binary_path = os.path.join(thispath, "riscv_matrix_minimal")

# Check if binary exists, otherwise use default hello
if os.path.exists(binary_path):
    binary = binary_path
    print(f"Using RISC-V matrix test: {binary}")
else:
    binary = os.path.join(thispath, "../../tests/test-progs/hello/bin/riscv/linux/hello")
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

print("Beginning RISC-V Matrix Spill Test!")
exit_event = m5.simulate()
print(f"RISC-V simulation finished @ tick {m5.curTick()} because {exit_event.getCause()}")
