"""
This gem5 configuration script tests Approach B: C++ instruction-level spill detection.

This uses our register pressure test program with the integrated C++ spill detector
that tracks store-load patterns using std::unordered_map as requested.

Usage:
./build/X86/gem5.fast hello_world/sim_cpp.py
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

# This check ensures the gem5 binary is compiled to the X86 ISA target. 
requires(isa_required=ISA.X86)

print("🔧 Setting up C++ Approach B: Instruction-level spill detection")

# We use simple caches for this example
cache_hierarchy = PrivateL1CacheHierarchy(l1d_size="64kB", l1i_size="16kB")

# We use a single channel DDR3_1600 memory system
memory = SingleChannelDDR3_1600(size="32MiB")

# We use a simple Timing processor with one core.
processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=1)

# The gem5 library simple board
board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Use our register pressure test program
board.set_se_binary_workload(
    BinaryResource(local_path="/Users/catnys/Documents/Academia/Register Spilling/gem5/hello_world/spill_test_x86_static")
)

# Run the simulation with integrated C++ spill detector
simulator = Simulator(board=board)

print("🚀 Starting simulation with C++ spill detection (Approach B)")
print("📝 The C++ SpillDetector will track every store-load pattern in real-time")

simulator.run()

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)

print("💾 C++ spill detection results saved to m5out/cpp_spill_log.txt")
print("🎯 Approach B (C++ instruction-level analysis) completed!")
