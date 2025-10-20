# This is a basic gem5 configuration script for running a RISC-V
# executable in Syscall Emulation (SE) mode.
"""
# 1. Build m5op.o
riscv64-linux-gnu-gcc -c -I/workspace/include /workspace/util/m5/src/abi/riscv/m5op.S -o m5op.o

# 2. Compile and link ELF
riscv64-linux-gnu-gcc -nostartfiles -static -I/workspace/include riscv_spill_test.S m5op.o -o riscv_spill_test.elf

# 3. Check ELF
file riscv_spill_test.elf

# 4. Run gem5 simulation for RISC-V
build/RISCV/gem5.opt benchmarks/builds/test/verify/riscv2/run_riscv2_spill_test.py

# 5. Analyze output
python benchmarks/analytics/stat_analyzer.py

"""
import m5
from m5.objects import *

# --- 1. Create the System Object ---
# The system object is the parent of all other objects in the simulation.
system = System()

# --- 2. Set up the Clock and Memory ---
# Set the clock frequency for the system.
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = '1GHz'
system.clk_domain.voltage_domain = VoltageDomain()

# Set up the memory system. We are using 'timing' mode, which is a
# more detailed and accurate memory simulation than 'atomic'.
system.mem_mode = 'timing'
system.mem_ranges = [AddrRange('512MB')]

# --- 3. Create the CPU ---
# We will use a simple timing-based CPU model for RISC-V.
system.cpu = RiscvTimingSimpleCPU()

# --- 4. Create the Memory Bus ---
# A system-wide memory bus.
system.membus = SystemXBar()

# --- 5. Connect CPU Caches to the Bus ---
# Connect the instruction and data cache ports of the CPU to the memory bus.
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports

# --- 6. Connect the Memory Controller ---
# Create a memory controller and connect it to the bus.
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# Required for RISC-V to work correctly.
system.cpu.createInterruptController()

# --- 7. Set up the Workload (Your Executable) ---
# This defines the program we want to run.
# The binary needs to be in the same directory as this script,
# or you must provide a full path.
binary_name = "benchmarks/builds/test/verify/riscv2/riscv_spill_test.elf" # The name of your compiled binary

system.workload = SEWorkload.init_compatible(binary_name)

process = Process()
process.cmd = [binary_name]
system.cpu.workload = process
system.cpu.createThreads()

# --- 8. Instantiate and Simulate ---
# This creates the C++ objects from the Python descriptions.
root = Root(full_system=False, system=system)
m5.instantiate()

# --- Start the Simulation ---
print(f"🚀 Starting simulation of '{binary_name}'...")
exit_event = m5.simulate()

print(f"✅ Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")