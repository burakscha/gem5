#!/usr/bin/env python3

import m5
from m5.objects import *
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.memory import SingleChannelDDR3_1600
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import PrivateL1CacheHierarchy
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator
from gem5.isas import ISA

# Create the cache hierarchy with private L1 caches
cache_hierarchy = PrivateL1CacheHierarchy(
    l1d_size="64kB",
    l1i_size="16kB"
)

# Create the memory system
memory = SingleChannelDDR3_1600(size="32MiB")

# Create the processor
processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    isa=ISA.X86,
    num_cores=1
)

# Create the board
board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Set the workload using BinaryResource
binary_path = "/Users/catnys/Documents/Academia/Register Spilling/gem5/tests/test-progs/hello/bin/x86/linux/hello"
binary_resource = BinaryResource(local_path=binary_path)
board.set_se_binary_workload(binary_resource)

# Create the simulator
simulator = Simulator(board=board)

# Run the simulation
print("Starting simulation...")
simulator.run()

print("============================================================")
print("SIMULATION RESULTS - Reading from stats.txt")
print("============================================================")
print("Simulation completed!")
print("Exit reason: exiting with last active thread context")
print("")

# Read the stats directly from the stats.txt file
import re

stats_file = "m5out/stats.txt"
try:
    with open(stats_file, 'r') as f:
        content = f.read()
    
    # Extract key statistics using regex
    def extract_stat(pattern, content):
        match = re.search(pattern, content)
        return float(match.group(1)) if match else 0.0
    
    # Basic simulation stats
    sim_insts = extract_stat(r'simInsts\s+(\d+)', content)
    sim_ops = extract_stat(r'simOps\s+(\d+)', content)
    sim_ticks = extract_stat(r'simTicks\s+(\d+)', content)
    
    # L1D Cache stats
    l1d_read_accesses = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.ReadReq\.accesses::total\s+(\d+)', content)
    l1d_write_accesses = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.WriteReq\.accesses::total\s+(\d+)', content)
    l1d_read_hits = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.ReadReq\.hits::total\s+(\d+)', content)
    l1d_write_hits = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.WriteReq\.hits::total\s+(\d+)', content)
    l1d_read_misses = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.ReadReq\.misses::total\s+(\d+)', content)
    l1d_write_misses = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.WriteReq\.misses::total\s+(\d+)', content)
    l1d_demand_accesses = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.demandAccesses::total\s+(\d+)', content)
    l1d_demand_hits = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.demandHits::total\s+(\d+)', content)
    l1d_demand_misses = extract_stat(r'board\.cache_hierarchy\.l1dcaches\.demandMisses::total\s+(\d+)', content)
    
    # L1I Cache stats
    l1i_demand_hits = extract_stat(r'board\.cache_hierarchy\.l1icaches\.demandHits::total\s+(\d+)', content)
    l1i_demand_misses = extract_stat(r'board\.cache_hierarchy\.l1icaches\.demandMisses::total\s+(\d+)', content)
    l1i_demand_accesses = l1i_demand_hits + l1i_demand_misses
    
    print("INSTRUCTION AND OPERATION COUNTS:")
    print("-" * 40)
    print(f"Total Instructions Executed: {sim_insts:.0f}")
    print(f"Total Operations (including micro-ops): {sim_ops:.0f}")
    print("")

    print("CACHE STATISTICS:")
    print("-" * 40)

    # L1 Data Cache Statistics
    print("L1 Data Cache:")
    print(f"  Read Operations: {l1d_read_accesses:.0f}")
    print(f"  Write Operations: {l1d_write_accesses:.0f}")
    print(f"  Total Memory Operations: {l1d_read_accesses + l1d_write_accesses:.0f}")
    print(f"  Read Hits: {l1d_read_hits:.0f}")
    print(f"  Write Hits: {l1d_write_hits:.0f}")
    print(f"  Read Misses: {l1d_read_misses:.0f}")
    print(f"  Write Misses: {l1d_write_misses:.0f}")
    
    if l1d_read_accesses > 0:
        print(f"  Read Hit Rate: {l1d_read_hits/l1d_read_accesses*100:.2f}%")
    if l1d_write_accesses > 0:
        print(f"  Write Hit Rate: {l1d_write_hits/l1d_write_accesses*100:.2f}%")
    print("")

    # L1 Instruction Cache Statistics
    print("L1 Instruction Cache:")
    print(f"  Instruction Fetch Operations: {l1i_demand_accesses:.0f}")
    print(f"  Instruction Hits: {l1i_demand_hits:.0f}")
    print(f"  Instruction Misses: {l1i_demand_misses:.0f}")
    if l1i_demand_accesses > 0:
        print(f"  Instruction Hit Rate: {l1i_demand_hits/l1i_demand_accesses*100:.2f}%")
    print("")

    print("MEMORY OPERATION SUMMARY:")
    print("-" * 40)
    total_memory_ops = l1d_read_accesses + l1d_write_accesses
    
    print(f"Total Load Operations: {l1d_read_accesses:.0f}")
    print(f"Total Store Operations: {l1d_write_accesses:.0f}")
    print(f"Total Memory Operations: {total_memory_ops:.0f}")
    
    if sim_insts > 0:
        print(f"Memory Operations per Instruction: {total_memory_ops/sim_insts:.2f}")
    if l1d_write_accesses > 0:
        print(f"Load/Store Ratio: {l1d_read_accesses/l1d_write_accesses:.2f}")
    print("")

    print("PERFORMANCE METRICS:")
    print("-" * 40)
    print(f"Total Simulation Ticks: {sim_ticks:.0f}")
    
    if sim_insts > 0 and sim_ticks > 0:
        print(f"Instructions per Tick: {sim_insts/sim_ticks:.6f}")
        print(f"Ticks per Instruction: {sim_ticks/sim_insts:.2f}")
    print("")

    print("DETAILED MEMORY ACCESS ANALYSIS:")
    print("-" * 40)
    print(f"Total L1D Demand Accesses: {l1d_demand_accesses:.0f}")
    print(f"Total L1D Demand Hits: {l1d_demand_hits:.0f}")
    print(f"Total L1D Demand Misses: {l1d_demand_misses:.0f}")
    
    if l1d_demand_accesses > 0:
        print(f"Overall L1D Hit Rate: {l1d_demand_hits/l1d_demand_accesses*100:.2f}%")
        print(f"Data Cache Miss Rate: {l1d_demand_misses/l1d_demand_accesses*100:.2f}%")

except FileNotFoundError:
    print(f"Could not find stats file: {stats_file}")
except Exception as e:
    print(f"Error reading stats: {e}")
