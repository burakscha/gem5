"""
This gem5 configuration script creates a simple board to run an X86
"hello world" binary and provides detailed memory operation statistics.

This script runs the simulation and then parses the output statistics
to show load and store operation counts and cache performance.

Usage
-----

```
scons build/X86/gem5.opt
./build/X86/gem5.fast hello_world/memory_analysis_sim.py
```
"""

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (
    PrivateL1CacheHierarchy,
)
from gem5.components.memory import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires
import m5

# This check ensures the gem5 binary is compiled to the X86 ISA target. 
# If not, an exception will be thrown.
requires(isa_required=ISA.X86)

# We use simple caches for this example
cache_hierarchy = PrivateL1CacheHierarchy(l1d_size="64kB", l1i_size="16kB")

# We use a single channel DDR3_1600 memory system
memory = SingleChannelDDR3_1600(size="32MiB")

# We use a simple Timing processor with one core.
processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=1)

# The gem5 library simple board which can be used to run simple SE-mode
# simulations.
board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Here we set the workload. In this case we want to run a simple "Hello World!"
# program compiled to the X86 ISA.
board.set_se_binary_workload(
    BinaryResource(local_path="/Users/catnys/Documents/Academia/Register Spilling/gem5/tests/test-progs/hello/bin/x86/linux/hello")
)

# Lastly we run the simulation.
simulator = Simulator(board=board)
simulator.run()

print("=" * 60)
print("SIMULATION RESULTS")
print("=" * 60)
print(f"Simulation completed at tick: {simulator.get_current_tick()}")
print(f"Exit reason: {simulator.get_last_exit_event_cause()}")
print("")

# Extract key statistics from the simulation
stats = simulator.get_stats()

print("INSTRUCTION AND OPERATION COUNTS:")
print("-" * 40)
print(f"Total Instructions Executed: {stats['simInsts']['value']:.0f}")
print(f"Total Operations (including micro-ops): {stats['simOps']['value']:.0f}")
print("")

print("CACHE STATISTICS:")
print("-" * 40)

# L1 Data Cache Statistics
print("L1 Data Cache:")
l1d_reads = stats['board.cache_hierarchy.l1dcaches.ReadReq.accesses::total']['value']
l1d_writes = stats['board.cache_hierarchy.l1dcaches.WriteReq.accesses::total']['value']
l1d_read_hits = stats['board.cache_hierarchy.l1dcaches.ReadReq.hits::total']['value']
l1d_write_hits = stats['board.cache_hierarchy.l1dcaches.WriteReq.hits::total']['value']
l1d_read_misses = stats['board.cache_hierarchy.l1dcaches.ReadReq.misses::total']['value']
l1d_write_misses = stats['board.cache_hierarchy.l1dcaches.WriteReq.misses::total']['value']

print(f"  Read Operations: {l1d_reads:.0f}")
print(f"  Write Operations: {l1d_writes:.0f}")
print(f"  Total Memory Operations: {l1d_reads + l1d_writes:.0f}")
print(f"  Read Hits: {l1d_read_hits:.0f}")
print(f"  Write Hits: {l1d_write_hits:.0f}")
print(f"  Read Misses: {l1d_read_misses:.0f}")
print(f"  Write Misses: {l1d_write_misses:.0f}")
print(f"  Read Hit Rate: {l1d_read_hits/l1d_reads*100:.2f}%")
print(f"  Write Hit Rate: {l1d_write_hits/l1d_writes*100:.2f}%")
print("")

# L1 Instruction Cache Statistics
print("L1 Instruction Cache:")
l1i_hits = stats['board.cache_hierarchy.l1icaches.demandHits::total']['value']
l1i_misses = stats['board.cache_hierarchy.l1icaches.demandMisses::total']['value']
l1i_accesses = l1i_hits + l1i_misses

print(f"  Instruction Fetch Operations: {l1i_accesses:.0f}")
print(f"  Instruction Hits: {l1i_hits:.0f}")
print(f"  Instruction Misses: {l1i_misses:.0f}")
print(f"  Instruction Hit Rate: {l1i_hits/l1i_accesses*100:.2f}%")
print("")

print("MEMORY OPERATION SUMMARY:")
print("-" * 40)
total_memory_ops = l1d_reads + l1d_writes
instructions = stats['simInsts']['value']

print(f"Total Load Operations: {l1d_reads:.0f}")
print(f"Total Store Operations: {l1d_writes:.0f}")
print(f"Total Memory Operations: {total_memory_ops:.0f}")
print(f"Memory Operations per Instruction: {total_memory_ops/instructions:.2f}")
print(f"Load/Store Ratio: {l1d_reads/l1d_writes:.2f}")
print("")

print("PERFORMANCE METRICS:")
print("-" * 40)
# Use simulation ticks as a proxy for cycles since detailed CPU cycle stats might not be available
ticks = stats['simTicks']['value']
freq = stats['simFreq']['value']
cycles = ticks  # For TimingSimpleCPU, ticks roughly correspond to cycles
print(f"Total Simulation Ticks: {ticks:.0f}")
print(f"Instructions per Tick: {instructions/ticks:.6f}")
print(f"Ticks per Instruction: {ticks/instructions:.2f}")
print("")

print("DETAILED MEMORY ACCESS ANALYSIS:")
print("-" * 40)
total_demand_accesses = stats['board.cache_hierarchy.l1dcaches.demandAccesses::total']['value']
total_demand_hits = stats['board.cache_hierarchy.l1dcaches.demandHits::total']['value']
total_demand_misses = stats['board.cache_hierarchy.l1dcaches.demandMisses::total']['value']

print(f"Total L1D Demand Accesses: {total_demand_accesses:.0f}")
print(f"Total L1D Demand Hits: {total_demand_hits:.0f}")
print(f"Total L1D Demand Misses: {total_demand_misses:.0f}")
print(f"Overall L1D Hit Rate: {total_demand_hits/total_demand_accesses*100:.2f}%")
print(f"Data Cache Miss Rate: {total_demand_misses/total_demand_accesses*100:.2f}%")
