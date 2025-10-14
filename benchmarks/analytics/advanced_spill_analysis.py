#!/usr/bin/env python3
"""
Advanced gem5 Spill Detection Analysis Tool
================================================================================
Quick Start:
    1. Update M5OUT_DIRECTORY variable (line ~36)
    2. python3 advanced_spill_analysis.py
    3. Review analysis_report.txt file
================================================================================
"""

import json
import os
import sys
from collections import defaultdict

# =============================================================================
# CONFIGURATION - Static parameters for analysis
# =============================================================================
# M5OUT directory - Simulation output directory to be analyzed
# Change this parameter to analyze different simulations
M5OUT_DIRECTORY = "results5out/m5out_verify_x86/"

# File names - gem5 standard output files (do not modify)
STATS_FILE_NAME = "stats.txt"  # gem5 general statistics file
SPILL_FILE_NAME = "x86_spill_stats.txt"  # Spill detection output file
CONFIG_FILE_NAME = "config.json"  # Simulation configuration file
OUTPUT_FILE_NAME = "analysis_report.txt"  # Analysis report output file


def parse_stats_txt(stats_file):
    """
    Parse stats.txt file to extract general simulation statistics.

    Args:
        stats_file (str): Full path to stats.txt file

    Returns:
        dict: Dictionary containing statistic values
            - total_instructions: Total instruction count
            - total_operations: Total operation count
            - simulation_ticks: Simulation tick count
            - cpu_cycles: CPU cycle count
            - cpi: Cycles per instruction
            - ipc: Instructions per cycle
            - total_loads: Load instruction count
            - total_stores: Store instruction count
    """
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
                    elif key == "system.cpu.commitStats0.numLoadInsts":
                        stats["total_loads"] = int(value)
                    elif key == "system.cpu.commitStats0.numStoreInsts":
                        stats["total_stores"] = int(value)

    return stats


def parse_config_json(config_file):
    """
    Parse config.json file to extract simulation configuration.

    Args:
        config_file (str): Full path to config.json file

    Returns:
        dict: Dictionary containing configuration information
            - cpu_type: CPU type (TimingSimpleCPU, O3CPU, etc.)
            - isa: ISA architecture (X86, ARM, RISCV, MIPS, SPARC, POWER)
            - clock_freq_ghz: Clock frequency (GHz)
            - mem_mode: Memory mode (timing, atomic)
            - cache_line_size: Cache line size (bytes)
            - num_cores: CPU core count
            - memory_size_gb: Total memory size (GB)
    """
    config_info = {
        "cpu_type": "Unknown",
        "isa": "Unknown",
        "clock_freq_ghz": 0.0,
        "mem_mode": "Unknown",
        "cache_line_size": 0,
        "num_cores": 1,
        "memory_size_gb": 0.0,
    }

    if not os.path.exists(config_file):
        print(f"⚠️  Config file not found: {config_file}")
        return config_info

    try:
        with open(config_file) as f:
            config = json.load(f)

        # Extract CPU type
        if "system" in config and "cpu" in config["system"]:
            cpu = config["system"]["cpu"]
            config_info["cpu_type"] = cpu.get("type", "Unknown")

        # Extract ISA (X86, ARM, RISCV, etc.)
        if "system" in config and "workload" in config["system"]:
            workload = config["system"]["workload"]
            workload_type = workload.get("type", "Unknown")
            # Extract ISA from workload type (e.g., "X86EmuLinux" -> "X86")
            if "X86" in workload_type:
                config_info["isa"] = "X86"
            elif "ARM" in workload_type or "Arm" in workload_type:
                config_info["isa"] = "ARM"
            elif "RISCV" in workload_type or "Riscv" in workload_type:
                config_info["isa"] = "RISCV"
            elif "MIPS" in workload_type:
                config_info["isa"] = "MIPS"
            elif "SPARC" in workload_type:
                config_info["isa"] = "SPARC"
            elif "POWER" in workload_type:
                config_info["isa"] = "POWER"
            else:
                config_info["isa"] = workload_type

        # Extract clock frequency (convert ticks to GHz)
        if (
            "system" in config
            and "clk_domain" in config["system"]
            and "clock" in config["system"]["clk_domain"]
        ):
            clock_ticks = config["system"]["clk_domain"]["clock"][0]
            # Clock period in ticks -> Frequency in GHz
            # 333 ticks = 3 GHz, 1000 ticks = 1 GHz
            config_info["clock_freq_ghz"] = 1000.0 / clock_ticks

        # Extract memory mode
        if "system" in config:
            config_info["mem_mode"] = config["system"].get(
                "mem_mode", "Unknown"
            )

        # Extract cache line size
        if "system" in config:
            config_info["cache_line_size"] = config["system"].get(
                "cache_line_size", 0
            )

        # Extract memory size
        if "system" in config and "mem_ranges" in config["system"]:
            mem_ranges = config["system"]["mem_ranges"]
            if mem_ranges:
                # Format: "0:8589934592" (start:end in bytes)
                mem_range_str = mem_ranges[0]
                if ":" in mem_range_str:
                    _, end = mem_range_str.split(":")
                    mem_bytes = int(end)
                    config_info["memory_size_gb"] = mem_bytes / (1024**3)

        # Try to detect number of cores (check if cpu is a list or single)
        if "system" in config and "cpu" in config["system"]:
            cpu = config["system"]["cpu"]
            if isinstance(cpu, list):
                config_info["num_cores"] = len(cpu)
            else:
                config_info["num_cores"] = 1

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"⚠️  Error parsing config.json: {e}")

    return config_info


def parse_spill_stats(spill_file):
    """
    Parse spill_stats.txt file to extract register spill statistics.

    Args:
        spill_file (str): Full path to x86_spill_stats.txt file

    Returns:
        dict: Dictionary containing spill statistics
            - total_spills: Total detected spill count
            - unique_store_pcs: Unique store PCs (set)
            - unique_load_pcs: Unique load PCs (set)
            - unique_memory_addresses: Unique memory addresses (set)
            - store_counts: Store counts per PC (dict)
            - load_counts: Load counts per PC (dict)
            - memory_address_counts: Spill counts per address (dict)
            - avg_tick_diff: Average tick difference
            - min_tick_diff: Minimum tick difference
            - max_tick_diff: Maximum tick difference
            - sample_spills: First 5 spill samples (list)
    """
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

                    # Store first 5 spills as samples
                    if len(spill_stats["sample_spills"]) < 5:
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

    return spill_stats


def calculate_advanced_metrics(stats, spill_stats):
    """
    Calculate advanced spill analysis metrics.

    Args:
        stats (dict): General simulation statistics
        spill_stats (dict): Spill detection statistics

    Returns:
        dict: Advanced metrics
            - spill_density: Spills per 1000 instructions
            - memory_pressure: Unique addresses / total spills
            - code_locality: Spills / unique store PCs
            - reload_efficiency: Average tick difference (cache perf)
            - register_pressure: Spills per second
            - spill_to_load_ratio: Spills / loads (%)
            - spill_to_store_ratio: Spills / stores (%)
            - hotspot_concentration: Top 5 PCs' share (%)
    """
    metrics = {}

    total_insts = stats.get("total_instructions", 0)
    total_loads = stats.get("total_loads", 0)
    total_stores = stats.get("total_stores", 0)
    total_spills = spill_stats["total_spills"]
    sim_seconds = stats.get("simulation_seconds", 0)
    unique_store_pcs = len(spill_stats["unique_store_pcs"])
    unique_mem_addrs = len(spill_stats["unique_memory_addresses"])

    # 1. Spill Density: Spills per 1000 instructions
    if total_insts > 0:
        metrics["spill_density"] = (total_spills / total_insts) * 1000
    else:
        metrics["spill_density"] = 0

    # 2. Memory Pressure: Unique memory addresses used per spill
    if total_spills > 0:
        metrics["memory_pressure"] = unique_mem_addrs / total_spills
    else:
        metrics["memory_pressure"] = 0

    # 3. Code Locality: Average spills per unique store PC
    if unique_store_pcs > 0:
        metrics["code_locality"] = total_spills / unique_store_pcs
    else:
        metrics["code_locality"] = 0

    # 4. Reload Efficiency: Average tick difference (cache efficiency indicator)
    metrics["reload_efficiency"] = spill_stats["avg_tick_diff"]

    # 5. Register Pressure Indicator: Spills per second
    if sim_seconds > 0:
        metrics["register_pressure"] = total_spills / sim_seconds
    else:
        metrics["register_pressure"] = 0

    # 6. Spill-to-Load Ratio
    if total_loads > 0:
        metrics["spill_to_load_ratio"] = (total_spills / total_loads) * 100
    else:
        metrics["spill_to_load_ratio"] = 0

    # 7. Spill-to-Store Ratio
    if total_stores > 0:
        metrics["spill_to_store_ratio"] = (total_spills / total_stores) * 100
    else:
        metrics["spill_to_store_ratio"] = 0

    # 8. Hot Spot Concentration: % of spills from top 5 store PCs
    if total_spills > 0:
        top_5_stores = sorted(
            spill_stats["store_counts"].values(), reverse=True
        )[:5]
        top_5_count = sum(top_5_stores)
        metrics["hotspot_concentration"] = (top_5_count / total_spills) * 100
    else:
        metrics["hotspot_concentration"] = 0

    return metrics


def generate_report(m5out_dir, stats, spill_stats, metrics, config_info):
    """
    Generate comprehensive analysis report.

    Args:
        m5out_dir (str): m5out directory path
        stats (dict): General simulation statistics
        spill_stats (dict): Spill detection statistics
        metrics (dict): Advanced metrics
        config_info (dict): Simulation configuration information

    Returns:
        str: Formatted report text

    Report Contents:
        - Re-run command (header)
        - Simulation configuration (ISA, CPU, clock, memory)
        - General statistics (instructions, cycles, CPI/IPC)
        - Spill detection statistics
        - Advanced metrics and evaluations
        - Optimization recommendations
    """

    report_lines = []

    # Add analysis command at the top
    report_lines.append("# " + "=" * 78)
    report_lines.append("# 🔄 Re-run Analysis Command:")
    report_lines.append(
        f"#    python3 benchmarks/analytics/advanced_spill_analysis.py {m5out_dir}"
    )
    report_lines.append("# " + "=" * 78)
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("📊 ADVANCED GEM5 SPILL ANALYSIS REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"📁 Directory: {m5out_dir}")
    report_lines.append("")

    # Simulation Configuration
    report_lines.append("⚙️  SIMULATION CONFIGURATION")
    report_lines.append("-" * 80)
    report_lines.append(
        f"  ISA Architecture:                  {config_info['isa']:>15}"
    )
    report_lines.append(
        f"  CPU Type:                          {config_info['cpu_type']:>15}"
    )
    report_lines.append(
        f"  Number of Cores:                   {config_info['num_cores']:>15}"
    )
    report_lines.append(
        f"  Clock Frequency:                   {config_info['clock_freq_ghz']:>15.2f} GHz"
    )
    report_lines.append(
        f"  Memory Mode:                       {config_info['mem_mode']:>15}"
    )
    report_lines.append(
        f"  Memory Size:                       {config_info['memory_size_gb']:>15.2f} GB"
    )
    report_lines.append(
        f"  Cache Line Size:                   {config_info['cache_line_size']:>15} bytes"
    )
    report_lines.append("")

    # General Simulation Statistics
    report_lines.append("🎯 GENERAL SIMULATION STATISTICS")
    report_lines.append("-" * 80)
    if stats:
        if "total_instructions" in stats:
            report_lines.append(
                f"  Total Instructions:                {stats['total_instructions']:>15,}"
            )
        if "total_operations" in stats:
            report_lines.append(
                f"  Total Operations:                  {stats['total_operations']:>15,}"
            )
        if "total_loads" in stats:
            report_lines.append(
                f"  Total Load Instructions:           {stats['total_loads']:>15,}"
            )
        if "total_stores" in stats:
            report_lines.append(
                f"  Total Store Instructions:          {stats['total_stores']:>15,}"
            )
        if "cpu_cycles" in stats:
            report_lines.append(
                f"  CPU Cycles:                        {stats['cpu_cycles']:>15,}"
            )
        if "simulation_ticks" in stats:
            report_lines.append(
                f"  Simulation Ticks:                  {stats['simulation_ticks']:>15,}"
            )
        if "simulation_seconds" in stats:
            report_lines.append(
                f"  Simulation Time:                   {stats['simulation_seconds']:>15.6f} seconds"
            )
        if "cpi" in stats:
            report_lines.append(
                f"  CPI (Cycles per Inst):             {stats['cpi']:>15.4f}"
            )
        if "ipc" in stats:
            report_lines.append(
                f"  IPC (Inst per Cycle):              {stats['ipc']:>15.4f}"
            )
    else:
        report_lines.append("  ❌ No general statistics found")
    report_lines.append("")

    # Basic Spill Statistics
    total_spills = spill_stats["total_spills"]
    report_lines.append("📊 INSTRUCTION DISTRIBUTION")
    report_lines.append("-" * 80)
    if stats.get("total_instructions", 0) > 0:
        total_insts = stats["total_instructions"]
        total_loads = stats.get("total_loads", 0)
        total_stores = stats.get("total_stores", 0)

        load_pct = (total_loads / total_insts) * 100 if total_loads else 0
        store_pct = (total_stores / total_insts) * 100 if total_stores else 0
        spill_pct = (total_spills / total_insts) * 100 if total_spills else 0

        report_lines.append(
            f"  Load Instructions:                 {total_loads:>15,}  ({load_pct:>6.2f}%)"
        )
        report_lines.append(
            f"  Store Instructions:                {total_stores:>15,}  ({store_pct:>6.2f}%)"
        )
        report_lines.append(
            f"  Spill Events:                      {total_spills:>15,}  ({spill_pct:>6.2f}%)"
        )
        report_lines.append("")

        # Additional ratios
        if total_loads > 0:
            spill_to_load = (total_spills / total_loads) * 100
            report_lines.append(
                f"  Spills as % of Loads:              {spill_to_load:>22.2f}%"
            )
        if total_stores > 0:
            spill_to_store = (total_spills / total_stores) * 100
            report_lines.append(
                f"  Spills as % of Stores:             {spill_to_store:>22.2f}%"
            )
    report_lines.append("")

    # Spill Detection Statistics
    report_lines.append("🔍 REGISTER SPILL DETECTION STATISTICS")
    report_lines.append("-" * 80)
    if spill_stats["total_spills"] > 0:
        report_lines.append(
            f"  Total Spills Detected:             {spill_stats['total_spills']:>15,}"
        )
        report_lines.append(
            f"  Unique Store PCs:                  {len(spill_stats['unique_store_pcs']):>15,}"
        )
        report_lines.append(
            f"  Unique Load PCs:                   {len(spill_stats['unique_load_pcs']):>15,}"
        )
        report_lines.append(
            f"  Unique Memory Addresses:           {len(spill_stats['unique_memory_addresses']):>15,}"
        )
        report_lines.append("")
        report_lines.append(
            f"  Average Tick Difference:           {spill_stats['avg_tick_diff']:>15,.2f}"
        )
        report_lines.append(
            f"  Min Tick Difference:               {spill_stats['min_tick_diff']:>15,}"
        )
        report_lines.append(
            f"  Max Tick Difference:               {spill_stats['max_tick_diff']:>15,}"
        )
        report_lines.append("")

    else:
        report_lines.append("  ⚠️  No spills detected")
    report_lines.append("")

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("Analysis Complete")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def main():
    """
    Main entry point - processes command line arguments and executes analysis.

    Usage:
        python3 advanced_spill_analysis.py [m5out_directory]

    If m5out_directory is not provided, uses M5OUT_DIRECTORY constant from file header.

    Workflow:
        1. Get command line argument or use static parameter
        2. Check directory existence
        3. Construct file paths (using static file names)
        4. Parse config, stats and spill files
        5. Calculate advanced metrics
        6. Generate and save report
        7. Print to terminal
    """
    # Use command line argument if provided, otherwise use static parameter
    if len(sys.argv) >= 2:
        m5out_dir = sys.argv[1]
        print(f"📌 Using command line argument: {m5out_dir}")
    else:
        m5out_dir = M5OUT_DIRECTORY
        print(f"📌 Using default M5OUT_DIRECTORY: {m5out_dir}")
        print(
            f"💡 Tip: You can override by running: python3 {sys.argv[0]} <m5out_directory>"
        )
        print()

    # Check if directory exists
    if not os.path.isdir(m5out_dir):
        print(f"❌ Error: Directory not found: {m5out_dir}")
        print(
            f"\n💡 Please update M5OUT_DIRECTORY in the script or provide a valid path"
        )
        sys.exit(1)

    # File paths - use static file names
    stats_file = os.path.join(m5out_dir, STATS_FILE_NAME)
    spill_file = os.path.join(m5out_dir, SPILL_FILE_NAME)
    config_file = os.path.join(m5out_dir, CONFIG_FILE_NAME)
    output_file = os.path.join(m5out_dir, OUTPUT_FILE_NAME)

    print(f"🔍 Analyzing m5out directory: {m5out_dir}")
    print(f"📄 Reading config from: {config_file}")
    print(f"📄 Reading stats from: {stats_file}")
    print(f"📄 Reading spill data from: {spill_file}")
    print()

    # Parse files - extract config, stats and spill data in order
    config_info = parse_config_json(config_file)
    stats = parse_stats_txt(stats_file)
    spill_stats = parse_spill_stats(spill_file)

    # Calculate advanced metrics
    metrics = calculate_advanced_metrics(stats, spill_stats)

    # Generate report
    report = generate_report(
        m5out_dir, stats, spill_stats, metrics, config_info
    )

    # Print to console
    print(report)

    # Save to file
    with open(output_file, "w") as f:
        f.write(report)

    print()
    print(f"✅ Report saved to: {output_file}")


if __name__ == "__main__":
    main()
