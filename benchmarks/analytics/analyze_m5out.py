#!/usr/bin/env python3
"""
gem5 m5out Directory Quick Analysis Tool
Analyzes stats.txt and x86_spill_stats.txt for comprehensive performance metrics
"""

import json
import os
import re
import sys
from collections import defaultdict


def parse_stats_txt(stats_file):
    """Parse stats.txt file for general simulation statistics"""
    stats = {}

    if not os.path.exists(stats_file):
        print(f"❌ Stats file not found: {stats_file}")
        return stats

    with open(stats_file) as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and headers
            if not line or line.startswith("-") or line.startswith("#"):
                continue

            # Parse key-value pairs
            if line and not line.startswith("system.work_item"):
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0]
                    value = parts[1]

                    # Store relevant statistics
                    if key == "simInsts":
                        stats["total_instructions"] = int(value)
                    elif key == "simOps":
                        stats["total_operations"] = int(value)
                    elif key == "simTicks":
                        stats["simulation_ticks"] = int(value)
                    elif key == "simSeconds":
                        stats["simulation_seconds"] = float(value)
                    elif key == "system.cpu.numCycles":
                        stats["cpu_cycles"] = int(value)
                    elif key == "system.cpu.cpi":
                        stats["cpi"] = float(value)
                    elif key == "system.cpu.ipc":
                        stats["ipc"] = float(value)
                    elif "dcache" in key and "overall_accesses" in key:
                        stats["dcache_accesses"] = int(value)
                    elif "dcache" in key and "overall_misses" in key:
                        stats["dcache_misses"] = int(value)
                    # Count load and store operations
                    elif key == "system.cpu.commitStats0.numLoadInsts":
                        stats["total_loads"] = int(value)
                    elif key == "system.cpu.commitStats0.numStoreInsts":
                        stats["total_stores"] = int(value)

    return stats


def parse_spill_stats(spill_file):
    """Parse x86_spill_stats.txt for spill detection statistics"""
    spill_stats = {
        "total_spills": 0,
        "unique_store_pcs": set(),
        "unique_load_pcs": set(),
        "unique_memory_addresses": set(),
        "store_counts": defaultdict(int),
        "load_counts": defaultdict(int),
        "memory_address_counts": defaultdict(int),
        "avg_tick_diff": 0,
        "min_tick_diff": 0,
        "max_tick_diff": 0,
        "sample_spills": [],
        "unique_store_count": 0,
        "unique_load_count": 0,
        "unique_memory_count": 0,
    }

    if not os.path.exists(spill_file):
        print(f"⚠️  Spill stats file not found: {spill_file}")
        return spill_stats

    # Check if file is empty
    if os.path.getsize(spill_file) == 0:
        print(f"⚠️  Spill stats file is empty: {spill_file}")
        return spill_stats

    total_tick_diff = 0
    min_tick = float("inf")

    with open(spill_file) as f:
        for line_num, line in enumerate(f):
            line = line.strip()

            # Skip header or empty lines
            if not line or not line.startswith("SPILL"):
                continue

            # Parse: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count
            parts = line.split(",")
            if len(parts) >= 9:
                try:
                    store_pc = parts[1]
                    load_pc = parts[2]
                    memory_addr = parts[3]
                    tick_diff = int(parts[6])

                    spill_stats["total_spills"] += 1
                    spill_stats["unique_store_pcs"].add(store_pc)
                    spill_stats["unique_load_pcs"].add(load_pc)
                    spill_stats["unique_memory_addresses"].add(memory_addr)

                    spill_stats["store_counts"][store_pc] += 1
                    spill_stats["load_counts"][load_pc] += 1
                    spill_stats["memory_address_counts"][memory_addr] += 1

                    total_tick_diff += tick_diff
                    min_tick = min(min_tick, tick_diff)
                    spill_stats["max_tick_diff"] = max(
                        spill_stats["max_tick_diff"], tick_diff
                    )

                    # Store first 10 spills as samples
                    if len(spill_stats["sample_spills"]) < 10:
                        spill_stats["sample_spills"].append(
                            {
                                "store_pc": store_pc,
                                "load_pc": load_pc,
                                "memory_addr": memory_addr,
                                "tick_diff": tick_diff,
                            }
                        )
                except (ValueError, IndexError) as e:
                    print(f"⚠️  Parse error at line {line_num + 1}: {e}")
                    continue

    # Calculate average tick difference
    if spill_stats["total_spills"] > 0:
        spill_stats["avg_tick_diff"] = (
            total_tick_diff / spill_stats["total_spills"]
        )
        spill_stats["min_tick_diff"] = min_tick
    else:
        spill_stats["min_tick_diff"] = 0

    # Convert sets to counts
    spill_stats["unique_store_count"] = len(spill_stats["unique_store_pcs"])
    spill_stats["unique_load_count"] = len(spill_stats["unique_load_pcs"])
    spill_stats["unique_memory_count"] = len(
        spill_stats["unique_memory_addresses"]
    )

    return spill_stats


def print_analysis(stats, spill_stats, m5out_dir):
    """Print comprehensive analysis report"""

    print("=" * 80)
    print("📊 GEM5 M5OUT ANALYSIS REPORT")
    print("=" * 80)
    print(f"📁 Directory: {m5out_dir}")
    print()

    # General Simulation Statistics
    print("🎯 GENERAL SIMULATION STATISTICS")
    print("-" * 80)
    if stats:
        if "total_instructions" in stats:
            print(
                f"  Total Instructions:        {stats['total_instructions']:>15,}"
            )
        if "total_operations" in stats:
            print(
                f"  Total Operations:          {stats['total_operations']:>15,}"
            )
        if "total_loads" in stats:
            print(f"  Total Load Instructions:   {stats['total_loads']:>15,}")
        if "total_stores" in stats:
            print(f"  Total Store Instructions:  {stats['total_stores']:>15,}")
        if "cpu_cycles" in stats:
            print(f"  CPU Cycles:                {stats['cpu_cycles']:>15,}")
        if "simulation_ticks" in stats:
            print(
                f"  Simulation Ticks:          {stats['simulation_ticks']:>15,}"
            )
        if "simulation_seconds" in stats:
            print(
                f"  Simulation Time:           {stats['simulation_seconds']:>15.6f} seconds"
            )
        if "cpi" in stats:
            print(f"  CPI (Cycles per Inst):     {stats['cpi']:>15.4f}")
        if "ipc" in stats:
            print(f"  IPC (Inst per Cycle):      {stats['ipc']:>15.4f}")
        if "dcache_accesses" in stats:
            print(
                f"  DCache Accesses:           {stats['dcache_accesses']:>15,}"
            )
        if "dcache_misses" in stats:
            print(
                f"  DCache Misses:             {stats['dcache_misses']:>15,}"
            )
    else:
        print("  ❌ No general statistics found")
    print()

    # Calculate percentages
    total_insts = stats.get("total_instructions", 0)
    total_loads = stats.get("total_loads", 0)
    total_stores = stats.get("total_stores", 0)
    total_spills = spill_stats["total_spills"]

    print("📊 INSTRUCTION DISTRIBUTION")
    print("-" * 80)
    if total_insts > 0:
        load_pct = (total_loads / total_insts) * 100 if total_loads else 0
        store_pct = (total_stores / total_insts) * 100 if total_stores else 0
        spill_pct = (total_spills / total_insts) * 100 if total_spills else 0

        print(
            f"  Load Instructions:         {total_loads:>15,}  ({load_pct:>6.2f}%)"
        )
        print(
            f"  Store Instructions:        {total_stores:>15,}  ({store_pct:>6.2f}%)"
        )
        print(
            f"  Spill Events:              {total_spills:>15,}  ({spill_pct:>6.2f}%)"
        )
        print()

        # Additional ratios
        if total_loads > 0:
            spill_to_load = (total_spills / total_loads) * 100
            print(f"  Spills as % of Loads:      {spill_to_load:>22.2f}%")
        if total_stores > 0:
            spill_to_store = (total_spills / total_stores) * 100
            print(f"  Spills as % of Stores:     {spill_to_store:>22.2f}%")
    else:
        print("  ⚠️  No instruction data available")
    print()

    # Spill Detection Statistics
    print("🔍 REGISTER SPILL DETECTION STATISTICS")
    print("-" * 80)
    if spill_stats["total_spills"] > 0:
        print(
            f"  Total Spills Detected:     {spill_stats['total_spills']:>15,}"
        )
        print(
            f"  Unique Store PCs:          {spill_stats['unique_store_count']:>15,}"
        )
        print(
            f"  Unique Load PCs:           {spill_stats['unique_load_count']:>15,}"
        )
        print(
            f"  Unique Memory Addresses:   {spill_stats['unique_memory_count']:>15,}"
        )
        print()
        print(
            f"  Average Tick Difference:   {spill_stats['avg_tick_diff']:>15,.2f}"
        )
        print(
            f"  Min Tick Difference:       {spill_stats['min_tick_diff']:>15,}"
        )
        print(
            f"  Max Tick Difference:       {spill_stats['max_tick_diff']:>15,}"
        )
        print()

        # Top 5 hottest store locations
        print("  🔥 Top 5 Hottest Store PCs:")
        top_stores = sorted(
            spill_stats["store_counts"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        for i, (pc, count) in enumerate(top_stores, 1):
            print(f"     {i}. PC {pc}: {count:,} spills")
        print()

        # Top 5 hottest load locations
        print("  🔥 Top 5 Hottest Load PCs:")
        top_loads = sorted(
            spill_stats["load_counts"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        for i, (pc, count) in enumerate(top_loads, 1):
            print(f"     {i}. PC {pc}: {count:,} spills")
        print()

        # Top 5 most used memory addresses
        print("  🔥 Top 5 Most Used Memory Addresses:")
        top_addrs = sorted(
            spill_stats["memory_address_counts"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        for i, (addr, count) in enumerate(top_addrs, 1):
            print(f"     {i}. Addr {addr}: {count:,} spills")
        print()

        # Sample spills
        if spill_stats["sample_spills"]:
            print("  📋 Sample Spills (First 5):")
            for i, spill in enumerate(spill_stats["sample_spills"][:5], 1):
                print(
                    f"     {i}. Store PC: {spill['store_pc']}, Load PC: {spill['load_pc']}, "
                    f"Mem: {spill['memory_addr']}, ΔTicks: {spill['tick_diff']:,}"
                )
    else:
        print("  ⚠️  No spills detected")
    print()

    # ROI Status
    print("✅ ROI STATUS")
    print("-" * 80)
    roi_active = stats.get("total_instructions", 0) > 0
    print(f"  ROI Active: {'✅ YES' if roi_active else '❌ NO'}")
    if roi_active:
        print(f"  Instructions in ROI: {stats.get('total_instructions', 0):,}")
    print()

    print("=" * 80)
    print("✅ Analysis Complete")
    print("=" * 80)


def save_txt_report(stats, spill_stats, m5out_dir):
    """Save analysis results to TXT file"""
    output_file = os.path.join(m5out_dir, "analysis_report.txt")

    with open(output_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("📊 GEM5 M5OUT ANALYSIS REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"📁 Directory: {m5out_dir}\n")
        f.write("\n")

        # General Simulation Statistics
        f.write("🎯 GENERAL SIMULATION STATISTICS\n")
        f.write("-" * 80 + "\n")
        if stats:
            if "total_instructions" in stats:
                f.write(
                    f"  Total Instructions:        {stats['total_instructions']:>15,}\n"
                )
            if "total_operations" in stats:
                f.write(
                    f"  Total Operations:          {stats['total_operations']:>15,}\n"
                )
            if "total_loads" in stats:
                f.write(
                    f"  Total Load Instructions:   {stats['total_loads']:>15,}\n"
                )
            if "total_stores" in stats:
                f.write(
                    f"  Total Store Instructions:  {stats['total_stores']:>15,}\n"
                )
            if "cpu_cycles" in stats:
                f.write(
                    f"  CPU Cycles:                {stats['cpu_cycles']:>15,}\n"
                )
            if "simulation_ticks" in stats:
                f.write(
                    f"  Simulation Ticks:          {stats['simulation_ticks']:>15,}\n"
                )
            if "simulation_seconds" in stats:
                f.write(
                    f"  Simulation Time:           {stats['simulation_seconds']:>15.6f} seconds\n"
                )
            if "cpi" in stats:
                f.write(
                    f"  CPI (Cycles per Inst):     {stats['cpi']:>15.4f}\n"
                )
            if "ipc" in stats:
                f.write(
                    f"  IPC (Inst per Cycle):      {stats['ipc']:>15.4f}\n"
                )
            if "dcache_accesses" in stats:
                f.write(
                    f"  DCache Accesses:           {stats['dcache_accesses']:>15,}\n"
                )
            if "dcache_misses" in stats:
                f.write(
                    f"  DCache Misses:             {stats['dcache_misses']:>15,}\n"
                )
        else:
            f.write("  ❌ No general statistics found\n")
        f.write("\n")

        # Calculate percentages
        total_insts = stats.get("total_instructions", 0)
        total_loads = stats.get("total_loads", 0)
        total_stores = stats.get("total_stores", 0)
        total_spills = spill_stats["total_spills"]

        f.write("📊 INSTRUCTION DISTRIBUTION\n")
        f.write("-" * 80 + "\n")
        if total_insts > 0:
            load_pct = (total_loads / total_insts) * 100 if total_loads else 0
            store_pct = (
                (total_stores / total_insts) * 100 if total_stores else 0
            )
            spill_pct = (
                (total_spills / total_insts) * 100 if total_spills else 0
            )

            f.write(
                f"  Load Instructions:         {total_loads:>15,}  ({load_pct:>6.2f}%)\n"
            )
            f.write(
                f"  Store Instructions:        {total_stores:>15,}  ({store_pct:>6.2f}%)\n"
            )
            f.write(
                f"  Spill Events:              {total_spills:>15,}  ({spill_pct:>6.2f}%)\n"
            )
            f.write("\n")

            # Additional ratios
            if total_loads > 0:
                spill_to_load = (total_spills / total_loads) * 100
                f.write(
                    f"  Spills as % of Loads:      {spill_to_load:>22.2f}%\n"
                )
            if total_stores > 0:
                spill_to_store = (total_spills / total_stores) * 100
                f.write(
                    f"  Spills as % of Stores:     {spill_to_store:>22.2f}%\n"
                )
        else:
            f.write("  ⚠️  No instruction data available\n")
        f.write("\n")

        # Spill Detection Statistics
        f.write("🔍 REGISTER SPILL DETECTION STATISTICS\n")
        f.write("-" * 80 + "\n")
        if spill_stats["total_spills"] > 0:
            f.write(
                f"  Total Spills Detected:     {spill_stats['total_spills']:>15,}\n"
            )
            f.write(
                f"  Unique Store PCs:          {spill_stats['unique_store_count']:>15,}\n"
            )
            f.write(
                f"  Unique Load PCs:           {spill_stats['unique_load_count']:>15,}\n"
            )
            f.write(
                f"  Unique Memory Addresses:   {spill_stats['unique_memory_count']:>15,}\n"
            )
            f.write("\n")
            f.write(
                f"  Average Tick Difference:   {spill_stats['avg_tick_diff']:>15,.2f}\n"
            )
            f.write(
                f"  Min Tick Difference:       {spill_stats['min_tick_diff']:>15,}\n"
            )
            f.write(
                f"  Max Tick Difference:       {spill_stats['max_tick_diff']:>15,}\n"
            )
            f.write("\n")

            # Top 5 hottest store locations
            f.write("  🔥 Top 5 Hottest Store PCs:\n")
            top_stores = sorted(
                spill_stats["store_counts"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            for i, (pc, count) in enumerate(top_stores, 1):
                f.write(f"     {i}. PC {pc}: {count:,} spills\n")
            f.write("\n")

            # Top 5 hottest load locations
            f.write("  🔥 Top 5 Hottest Load PCs:\n")
            top_loads = sorted(
                spill_stats["load_counts"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            for i, (pc, count) in enumerate(top_loads, 1):
                f.write(f"     {i}. PC {pc}: {count:,} spills\n")
            f.write("\n")

            # Top 5 most used memory addresses
            f.write("  🔥 Top 5 Most Used Memory Addresses:\n")
            top_addrs = sorted(
                spill_stats["memory_address_counts"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            for i, (addr, count) in enumerate(top_addrs, 1):
                f.write(f"     {i}. Addr {addr}: {count:,} spills\n")
            f.write("\n")

            # Sample spills
            if spill_stats["sample_spills"]:
                f.write("  📋 Sample Spills (First 5):\n")
                for i, spill in enumerate(spill_stats["sample_spills"][:5], 1):
                    f.write(
                        f"     {i}. Store PC: {spill['store_pc']}, Load PC: {spill['load_pc']}, "
                        f"Mem: {spill['memory_addr']}, ΔTicks: {spill['tick_diff']:,}\n"
                    )
        else:
            f.write("  ⚠️  No spills detected\n")
        f.write("\n")

        # ROI Status
        f.write("✅ ROI STATUS\n")
        f.write("-" * 80 + "\n")
        roi_active = stats.get("total_instructions", 0) > 0
        f.write(f"  ROI Active: {'✅ YES' if roi_active else '❌ NO'}\n")
        if roi_active:
            f.write(
                f"  Instructions in ROI: {stats.get('total_instructions', 0):,}\n"
            )
        f.write("\n")

        f.write("=" * 80 + "\n")
        f.write("✅ Analysis Complete\n")
        f.write("=" * 80 + "\n")

    print(f"📄 TXT report saved to: {output_file}")


def main():
    # Determine m5out directory
    if len(sys.argv) > 1:
        m5out_dir = sys.argv[1]
    else:
        m5out_dir = "m5out"

    if not os.path.isdir(m5out_dir):
        print(f"❌ Error: Directory '{m5out_dir}' does not exist")
        print(f"Usage: {sys.argv[0]} [m5out_directory]")
        sys.exit(1)

    # File paths
    stats_file = os.path.join(m5out_dir, "stats.txt")
    spill_file = os.path.join(m5out_dir, "x86_spill_stats.txt")

    # Parse files
    print(f"🔄 Analyzing {m5out_dir}...")
    print()

    stats = parse_stats_txt(stats_file)
    spill_stats = parse_spill_stats(spill_file)

    # Print analysis
    print_analysis(stats, spill_stats, m5out_dir)

    # Save TXT report
    save_txt_report(stats, spill_stats, m5out_dir)


if __name__ == "__main__":
    main()
