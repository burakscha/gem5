"""Runs a RISC-V binary through the gem5 standard library (the new config
API) instead of configs/deprecated/example/se.py.

usage: gem5.opt stdlib_se.py <binary> <exit_on_work_items: 1 | 0>

exit_on_work_items=1 is the stdlib default: every m5_work_begin/end returns
control to Python, whose default handlers reset the statistics at work begin
and dump them at work end. Prints the ROI lengths stdlib measured as
"ROI_TICKS [...]" for run_tests.py to compare against stats.txt.
"""

import sys

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator

binary, exit_on_work_items = sys.argv[1], sys.argv[2] == "1"

board = SimpleBoard(
    clk_freq="3GHz",
    processor=SimpleProcessor(
        cpu_type=CPUTypes.TIMING, num_cores=1, isa=ISA.RISCV
    ),
    memory=SingleChannelDDR3_1600(size="512MiB"),
    cache_hierarchy=PrivateL1PrivateL2CacheHierarchy(
        l1d_size="64KiB", l1i_size="32KiB", l2_size="2MiB"
    ),
)
board.set_se_binary_workload(
    binary=BinaryResource(local_path=binary),
    exit_on_work_items=exit_on_work_items,
)
simulator = Simulator(board=board)
simulator.run()
print("ROI_TICKS", simulator.get_roi_ticks())
