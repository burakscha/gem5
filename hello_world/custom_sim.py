"""
This gem5 configuration script creates a simple board to run our own
compiled X86 "hello world" binary.

This uses our custom cross-compiled binary instead of gem5's test programs.

Usage
-----

```
scons build/X86/gem5.opt
./build/X86/gem5.fast hello_world/custom_sim.py
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

# Here we set the workload to our own compiled X86 binary
board.set_se_binary_workload(
    BinaryResource(local_path="/Users/catnys/Documents/Academia/Register Spilling/gem5/hello_world/hello_world_x86_static")
)

# Lastly we run the simulation.
simulator = Simulator(board=board)
simulator.run()

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)
