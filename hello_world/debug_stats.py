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
from gem5.resources.resource import BinaryResource

# Create a Resource from our binary path
binary_path = "/Users/catnys/Documents/Academia/Register Spilling/gem5/tests/test-progs/hello/bin/x86/linux/hello"
binary_resource = BinaryResource(local_path=binary_path)
board.set_se_binary_workload(binary_resource)

# Create the simulator
simulator = Simulator(board=board)

# Run the simulation
print("Starting simulation...")
simulator.run()

print("============================================================")
print("DEBUGGING: AVAILABLE STATISTICS")
print("============================================================")

# Let's see what stats are actually available
stats = simulator.get_stats()
print(f"Total number of stats: {len(stats)}")
print("\nFirst 20 stat names:")
stat_names = list(stats.keys())
for i, name in enumerate(stat_names[:20]):
    print(f"{i+1:2d}: {name}")

print("\nSearching for L1D cache related stats:")
l1d_stats = [name for name in stat_names if 'l1dcaches' in name]
for stat in l1d_stats[:10]:  # Show first 10
    print(f"  {stat}")

print("\nSearching for ReadReq stats:")
read_stats = [name for name in stat_names if 'ReadReq' in name and 'l1dcaches' in name]
for stat in read_stats[:5]:  # Show first 5
    print(f"  {stat}")

print("\nSearching for WriteReq stats:")
write_stats = [name for name in stat_names if 'WriteReq' in name and 'l1dcaches' in name]
for stat in write_stats[:5]:  # Show first 5
    print(f"  {stat}")
