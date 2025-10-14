#!/usr/bin/env python3
"""
Basit gem5 simülasyon scripti - Spill Detection ile
Kullanım: build/X86/gem5.opt configs/tutorial/simple_spill_detection.py [binary_path]
"""

import sys

import m5
from m5.objects import *

# Binary path (komut satırından veya default)
if len(sys.argv) > 1:
    binary = sys.argv[1]
else:
    binary = "tests/test-progs/hello/bin/x86/linux/hello"

print(f"Simulating binary: {binary}")

# 1. Sistem oluştur
system = System()

# 2. Clock ve voltage ayarla
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "3GHz"
system.clk_domain.voltage_domain = VoltageDomain()

# 3. Memory ayarları
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("8GiB")]

# 4. CPU seç (TimingSimpleCPU - spill detection ile çalışır)
system.cpu = X86TimingSimpleCPU()

# 5. Memory bus oluştur
system.membus = SystemXBar()

# 6. CPU'yu bus'a bağla (cache yok, basit)
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports

# 7. Interrupt controller (X86 için gerekli)
system.cpu.createInterruptController()
system.cpu.interrupts[0].pio = system.membus.mem_side_ports
system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports

# 8. System port bağla
system.system_port = system.membus.cpu_side_ports

# 9. Memory controller
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# 10. Binary'yi yükle
system.workload = SEWorkload.init_compatible(binary)
process = Process()
process.cmd = [binary]
system.cpu.workload = process
system.cpu.createThreads()

# 11. Simülasyonu başlat
root = Root(full_system=False, system=system)
m5.instantiate()

print("=" * 60)
print("🚀 Simulation started with Spill Detection!")
print("=" * 60)

exit_event = m5.simulate()

print("=" * 60)
print(f"✅ Simulation finished!")
print(f"   Exit @ tick {m5.curTick()}")
print(f"   Reason: {exit_event.getCause()}")
print("=" * 60)
print("\n📊 Check results in m5out/ directory:")
print("   - stats.txt: General statistics")
print("   - x86_spill_stats.txt: Spill detection results")
