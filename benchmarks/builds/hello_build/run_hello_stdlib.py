from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.no_cache import NoCache
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.resources.resource import CustomResource
from gem5.simulate.simulator import Simulator

# 1) İşlemci + cache + bellek
processor = SimpleProcessor(cpu_type=CPUTypes.ATOMIC, isa=ISA.X86, num_cores=1)
cache_hierarchy = NoCache()
memory = SingleChannelDDR3_1600("8GiB")

# 2) Board (clk_freq belirtmek zorunlu)
board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# 3) SE workload olarak kendi x86 ikilini ver
workload = CustomResource("benchmarks/builds/hello_build/hello_folks_x86")
board.set_se_binary_workload(workload)

# 4) Çalıştır
Simulator(board=board).run()