#!/usr/bin/env python3
"""
Run pure assembly spill test for X86 or RISC-V.

Usage examples:
    build/RISCV/gem5.opt benchmarks/builds/test/verify/run_spill_test.py
"""

import os

import m5
from m5.objects import *

# ============================================================
# Detect ISA from gem5 binary path
# ============================================================
gem5_bin = os.path.basename(
    os.path.dirname(os.path.dirname(m5.options.outdir))
)
isa = "RISCV"
print(f"🧩 Detected ISA: {isa}")

# ============================================================
# Binary selection
# ============================================================
if isa == "RISCV":
    binary = "benchmarks/builds/test/verify/riscv/pure_asm_spill.elf"


print(f"Running pure assembly spill test: {binary}")

# ============================================================
# Create system
# ============================================================
system = System()
system.clk_domain = SrcClockDomain(
    clock="3GHz", voltage_domain=VoltageDomain()
)
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("512MB")]

# ---------------- CPU by ISA ----------------
system.cpu = RiscvTimingSimpleCPU()
system.cpu.createInterruptController()
# ---------------- Memory bus ----------------
system.membus = SystemXBar()
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports


# ---------------- Memory controller ----------------
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# ---------------- System port ----------------
system.system_port = system.membus.cpu_side_ports

# ============================================================
# Workload setup
# ============================================================
system.workload = SEWorkload.init_compatible(binary)
process = Process()
process.cmd = [binary]
system.cpu.workload = process
system.cpu.createThreads()

# ============================================================
# Instantiate & simulate
# ============================================================
root = Root(full_system=False, system=system)
m5.instantiate()

print("=" * 70)
print(f"🧪 Assembly Spill Verification Test ({isa})")
print("=" * 70)
print("Expected spills: 9 (1 + 3 + 5)")
print("=" * 70)

exit_event = m5.simulate()

print("=" * 70)
print(f"✅ Simulation finished @ tick {m5.curTick()}")
print(f"   Reason: {exit_event.getCause()}")
print("=" * 70)
print("\n📊 Check results:")
print("   m5out/stats.txt -> should reflect your spill detection counters")
print("=" * 70)
