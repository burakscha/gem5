#!/usr/bin/env python3
"""
Advanced gem5 Spill Detection Analysis Tool
================================================================================
Quick Start:
    1. Update DEFAULT_M5OUT_DIRECTORY variable (line ~39) if needed
    2. python3 advanced_spill_analysis.py [optional_m5out_directory]
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

# --- Static File Names (do not modify) ---
STATS_FILE_NAME = "stats.txt"  # gem5 general statistics file
CONFIG_FILE_NAME = "config.json"  # Simulation configuration file
OUTPUT_FILE_NAME = "analysis_report.txt"  # Analysis report output file

# --- Default m5out Directory ---
# This is used if no directory is provided on the command line
DEFAULT_M5OUT_DIRECTORY = "m5out"

# --- ISA-specific Spill File Mapping ---
# This mapping makes it easy to add support for other ISAs
ISA_SPILL_FILES = {
    "RISCV": "riscv_spill_stats.txt",
    "X86": "x86_spill_stats.txt",
    "ARM": "arm_spill_stats.txt",
    "UNKNOWN": "riscv_spill_stats.txt",  # Default fallback
}


# =============================================================================
# DATA PARSING FUNCTIONS
# =============================================================================

def read_data(stats_file, spill_file):
    """
    Central data reading function - extracts all necessary statistics from gem5
    output files.
    
    Args:
        stats_file (str): Full path to stats.txt file
        spill_file (str): Full path to spill_stats.txt file (x86/riscv)
    
    Returns:
        dict: Comprehensive data dictionary with all statistics
    """
    data = {
        "roi_instructions": 0,
        "roi_loads": 0,
        "roi_stores": 0,
        "roi_mem_reads": 0,
        "roi_mem_read_pct": 0.0,
        "roi_mem_writes": 0,
        "roi_mem_write_pct": 0.0,
        "roi_spills": 0,
        "spill_stats": {},
        "general_stats": {},
    }
    
    # Read stats.txt
    # Note: We assume stats_file exists because validate_paths() checked it.
    try:
        with open(stats_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(("-", "#")):
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                    
                key = parts[0]
                value = parts[1]
                
                try:
                    # ROI Instructions (from simInsts)
                    if key == "simInsts":
                        data["roi_instructions"] = int(value)
                        data["general_stats"]["total_instructions"] = int(value)
                    
                    # ROI Loads and Stores
                    # NOTE: These keys are hardcoded. If your CPU or stat path
                    # differs (e.g., multi-core), these keys must be updated.
                    elif key == "system.cpu.commitStats0.numLoadInsts":
                        data["roi_loads"] = int(value)
                        data["general_stats"]["total_loads"] = int(value)
                    
                    elif key == "system.cpu.commitStats0.numStoreInsts":
                        data["roi_stores"] = int(value)
                        data["general_stats"]["total_stores"] = int(value)
                    
                    # Memory Read/Write committed instructions
                    elif key == "system.cpu.commitStats0.committedInstType::MemRead":
                        data["roi_mem_reads"] = int(value)
                        if len(parts) >= 3:
                            pct_str = parts[2].strip('%')
                            data["roi_mem_read_pct"] = float(pct_str)
                    
                    elif key == "system.cpu.commitStats0.committedInstType::MemWrite":
                        data["roi_mem_writes"] = int(value)
                        if len(parts) >= 3:
                            pct_str = parts[2].strip('%')
                            data["roi_mem_write_pct"] = float(pct_str)
                    
                    # Other general stats
                    elif key == "simOps":
                        data["general_stats"]["total_operations"] = int(value)
                    elif key == "simTicks":
                        data["general_stats"]["simulation_ticks"] = int(value)
                    elif key == "simSeconds":
                        data["general_stats"]["simulation_seconds"] = float(value)
                    elif key == "system.cpu.numCycles":
                        data["general_stats"]["cpu_cycles"] = int(value)
                    elif key == "system.cpu.cpi":
                        data["general_stats"]["cpi"] = float(value)
                    elif key == "system.cpu.ipc":
                        data["general_stats"]["ipc"] = float(value)
                        
                except (ValueError, IndexError):
                    print(f"⚠️  Skipping malformed line in stats.txt: {line}")

    except IOError as e:
        print(f"❌ Error reading stats file: {e}")
        # We can continue, data will just be empty
    
    # Read spill file (this file is optional)
    if not os.path.exists(spill_file) or os.path.getsize(spill_file) == 0:
        print(f"ℹ️  Spill file not found or is empty: {spill_file}")
        return data  # Return data without spill stats

    try:
        spill_count = 0
        unique_store_pcs = set()
        unique_load_pcs = set()
        unique_mem_addrs = set()
        tick_diffs = []
        
        with open(spill_file) as f:
            for line in f:
                line = line.strip()
                if not line.startswith("SPILL"):
                    continue
                
                parts = line.split(",")
                if len(parts) >= 9:
                    try:
                        spill_count += 1
                        unique_store_pcs.add(parts[1])
                        unique_load_pcs.add(parts[2])
                        unique_mem_addrs.add(parts[3])
                        tick_diffs.append(int(parts[6]))
                    except (ValueError, IndexError):
                        print(f"⚠️  Skipping malformed line in spill file: {line}")
        
        data["roi_spills"] = spill_count
        data["spill_stats"] = {
            "total_spills": spill_count,
            "unique_store_pcs": len(unique_store_pcs),
            "unique_load_pcs": len(unique_load_pcs),
            "unique_memory_addresses": len(unique_mem_addrs),
            "avg_tick_diff": sum(tick_diffs) / len(tick_diffs) if tick_diffs else 0,
            "min_tick_diff": min(tick_diffs) if tick_diffs else 0,
            "max_tick_diff": max(tick_diffs) if tick_diffs else 0,
        }
    except IOError as e:
        print(f"❌ Error reading spill file: {e}")
    
    return data


def parse_config_json(config_file):
    """
    Parse config.json file to extract simulation configuration and detect ISA.

    Args:
        config_file (str): Full path to config.json file

    Returns:
        dict: Dictionary containing configuration information
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

    try:
        with open(config_file) as f:
            config = json.load(f)

        system = config.get("system", {})

        # Extract CPU type
        cpu = system.get("cpu", {})
        if isinstance(cpu, list):
            config_info["num_cores"] = len(cpu)
            config_info["cpu_type"] = cpu[0].get("type", "Unknown") if cpu else "Unknown"
        else:
            config_info["num_cores"] = 1
            config_info["cpu_type"] = cpu.get("type", "Unknown")

        # Extract ISA (X86, ARM, RISCV, etc.)
        workload = system.get("workload", {})
        workload_type = workload.get("type", "Unknown").upper()
        
        if "X86" in workload_type:
            config_info["isa"] = "X86"
        elif "ARM" in workload_type:
            config_info["isa"] = "ARM"
        elif "RISCV" in workload_type:
            config_info["isa"] = "RISCV"
        elif "MIPS" in workload_type:
            config_info["isa"] = "MIPS"
        elif "SPARC" in workload_type:
            config_info["isa"] = "SPARC"
        elif "POWER" in workload_type:
            config_info["isa"] = "POWER"
        else:
            config_info["isa"] = workload_type if workload_type else "Unknown"


        # Extract clock frequency (convert ticks to GHz)
        clk_domain = system.get("clk_domain", {})
        if "clock" in clk_domain and clk_domain["clock"]:
            clock_ticks = clk_domain["clock"][0]  # e.g., "1000" (for 1GHz) or "333" (for 3GHz)
            try:
                # Clock period is in Ticks. 1 Tick = 1ps.
                # Freq = 1 / Period.
                # e.g., 1000 ticks = 1000ps = 1ns. Freq = 1 / 1ns = 1 GHz
                # e.g., 333 ticks = 333ps = 0.333ns. Freq = 1 / 0.333ns = 3 GHz
                config_info["clock_freq_ghz"] = 1000.0 / float(clock_ticks)
            except (ValueError, TypeError):
                pass  # Keep default 0.0

        # Extract memory mode
        config_info["mem_mode"] = system.get("mem_mode", "Unknown")

        # Extract cache line size
        config_info["cache_line_size"] = system.get("cache_line_size", 0)

        # Extract memory size
        mem_ranges = system.get("mem_ranges", [])
        if mem_ranges:
            mem_range_str = mem_ranges[0]  # Format: "0:8589934592" (start:end)
            if ":" in mem_range_str:
                try:
                    _, end = mem_range_str.split(":")
                    mem_bytes = int(end) + 1 # size is end_addr + 1
                    config_info["memory_size_gb"] = mem_bytes / (1024**3)
                except (ValueError, IndexError):
                    pass # Keep default 0.0

    except FileNotFoundError:
        print(f"⚠️  Config file not found: {config_file}")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"⚠️  Error parsing config.json: {e}")

    return config_info


# =============================================================================
# REPORT GENERATION FUNCTIONS
# =============================================================================

def generate_report(m5out_dir, config_info, data):
    """
    Generate comprehensive analysis report.

    Args:
        m5out_dir (str): m5out directory path
        config_info (dict): Simulation configuration information
        data (dict): Comprehensive data from read_data()

    Returns:
        str: Formatted report text
    """
    report_lines = []

    # Simulation Configuration Section
    report_lines.append(
        generate_header_and_config_section(
            data.get("general_stats", {}), m5out_dir, config_info
        )
    )
    
    # General Simulation Statistics
    report_lines.append(
        generate_general_simulation_statistics(data.get("general_stats", {}))
    )

    # ROI Statistics Section (includes spill detection)
    report_lines.append(generate_roi_report_section(data))

    report_lines.append("=" * 80)
    report_lines.append("Analysis Complete")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def generate_header_and_config_section(stats, m5out_dir, config_info):
    """
    Generate report header and general statistics section.
    (Renamed from generate_stats_section for clarity)
    
    Args:
        stats (dict): General simulation statistics
        m5out_dir (str): Path to the m5out directory
        config_info (dict): Parsed configuration data
    """
    lines = []
    m5out_abs = os.path.abspath(m5out_dir)

    # Add analysis command at the top
    lines.append("# " + "=" * 78)
    lines.append("# 🔄 Re-run Analysis Command:")
    # Use sys.argv[0] to get the script name dynamically
    lines.append(f"#    python3 {sys.argv[0]} {m5out_dir}")
    lines.append("# " + "=" * 78)
    lines.append("")

    lines.append("=" * 80)
    lines.append("📊 ADVANCED GEM5 SPILL ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"📁 Directory: {m5out_abs}")
    lines.append("")

    # Simulation Configuration
    lines.append("⚙️  SIMULATION CONFIGURATION")
    lines.append("-" * 80)
    lines.append(
        f"  ISA Architecture:                  {config_info['isa']:>15}"
    )
    lines.append(
        f"  CPU Type:                          {config_info['cpu_type']:>15}"
    )
    lines.append(
        f"  Number of Cores:                   {config_info['num_cores']:>15}"
    )
    lines.append(
        f"  Clock Frequency:                   {config_info['clock_freq_ghz']:>15.2f} GHz"
    )
    lines.append(
        f"  Memory Mode:                       {config_info['mem_mode']:>15}"
    )
    lines.append(
        f"  Memory Size:                       {config_info['memory_size_gb']:>15.2f} GB"
    )
    lines.append(
        f"  Cache Line Size:                   {config_info['cache_line_size']:>15} bytes"
    )
    lines.append("")
    return "\n".join(lines)


def generate_general_simulation_statistics(stats):
    """
    Generate general simulation statistics section for the analysis report.

    Args:
        stats (dict): General simulation statistics from stats.txt
    """
    lines = []

    # General Simulation Statistics
    lines.append("🎯 GENERAL SIMULATION STATISTICS (Full Run)")
    lines.append("-" * 80)
    if not stats or "cpu_cycles" not in stats:
        lines.append("  ❌ No general statistics found")
    else:
        if "cpu_cycles" in stats:
            lines.append(
                f"  CPU Cycles:                        {stats['cpu_cycles']:>15,}"
            )
        if "simulation_ticks" in stats:
            lines.append(
                f"  Simulation Ticks:                  {stats['simulation_ticks']:>15,}"
            )
        if "simulation_seconds" in stats:
            lines.append(
                f"  Simulation Time:                   {stats['simulation_seconds']:>15.6f} seconds"
            )
        if "cpi" in stats:
            lines.append(
                f"  CPI (Cycles per Inst):             {stats['cpi']:>15.4f}"
            )
        if "ipc" in stats:
            lines.append(
                f"  IPC (Inst per Cycle):              {stats['ipc']:>15.4f}"
            )
    lines.append("")
    return "\n".join(lines)


def generate_roi_report_section(data):
    """
    Generate ROI-only statistics section for the analysis report.
    
    This section focuses exclusively on the Region of Interest (ROI)
    marked by m5_work_begin() and m5_work_end() in the simulated code.

    Args:
        data (dict): Comprehensive data from read_data() function

    Returns:
        str: Formatted ROI report section
    """
    lines = []
    lines.append("=" * 80)
    lines.append("🚧 ROI-ONLY STATISTICS (Region of Interest)")
    lines.append("=" * 80)
    lines.append("")
    
    # Extract data
    roi_insts = data.get("roi_instructions", 0)
    roi_loads = data.get("roi_loads", 0)
    roi_stores = data.get("roi_stores", 0)
    roi_mem_reads = data.get("roi_mem_reads", 0)
    roi_mem_read_pct = data.get("roi_mem_read_pct", 0.0)
    roi_mem_writes = data.get("roi_mem_writes", 0)
    roi_mem_write_pct = data.get("roi_mem_write_pct", 0.0)
    roi_spills = data.get("roi_spills", 0)
    spill_stats = data.get("spill_stats", {})
    
    if roi_insts == 0:
        lines.append("  ⚠️  No ROI statistics found")
        lines.append("  💡  Make sure your code uses m5_work_begin() and m5_work_end()")
        lines.append("  💡  (or that simInsts is present in stats.txt)")
        lines.append("")
        return "\n".join(lines)
    
    # === INSTRUCTION COUNTS ===
    lines.append("📊 ROI INSTRUCTION COUNTS")
    lines.append("-" * 80)
    lines.append(f"  Total ROI Instructions:            {roi_insts:>15,}")
    lines.append(f"  Load Instructions (numLoadInsts):  {roi_loads:>15,}")
    lines.append(f"  Store Instructions (numStoreInsts):{roi_stores:>15,}")
    lines.append("")
    
    # === MEMORY OPERATIONS (from committedInstType) ===
    lines.append("💾 COMMITTED MEMORY OPERATIONS")
    lines.append("-" * 80)
    lines.append(f"  MemRead (committed):               {roi_mem_reads:>15,}   ({roi_mem_read_pct:>6.2f}%)")
    lines.append(f"  MemWrite (committed):              {roi_mem_writes:>15,}   ({roi_mem_write_pct:>6.2f}%)")
    lines.append("")
    
    # === SPILL DETECTION STATISTICS ===
    lines.append("🔍 REGISTER SPILL DETECTION")
    lines.append("-" * 80)
    lines.append(f"  Total Spills Detected:             {roi_spills:>15,}")
    
    if roi_spills > 0 and spill_stats:
        lines.append(f"  Unique Store PCs:                  {spill_stats.get('unique_store_pcs', 0):>15,}")
        lines.append(f"  Unique Load PCs:                   {spill_stats.get('unique_load_pcs', 0):>15,}")
        lines.append(f"  Unique Memory Addresses:           {spill_stats.get('unique_memory_addresses', 0):>15,}")
        lines.append("")
        lines.append(f"  Average Tick Difference:           {spill_stats.get('avg_tick_diff', 0):>15,.2f}")
        lines.append(f"  Min Tick Difference:               {spill_stats.get('min_tick_diff', 0):>15,}")
        lines.append(f"  Max Tick Difference:               {spill_stats.get('max_tick_diff', 0):>15,}")
    elif roi_spills == 0:
        lines.append("  ✅ No spills detected in ROI")
    else:
        lines.append("  ⚠️  Spill file was missing or empty; spill stats unavailable.")
    lines.append("")
    
    # === PERCENTAGES & RATIOS ===
    lines.append("📈 ROI ANALYSIS RATIOS")
    lines.append("-" * 80)
    
    # Percentage of instructions
    load_pct = (roi_loads / roi_insts) * 100 if roi_insts else 0
    store_pct = (roi_stores / roi_insts) * 100 if roi_insts else 0
    spill_pct = (roi_spills / roi_insts) * 100 if roi_insts else 0
    
    lines.append(f"  Loads as % of ROI Instructions:    {load_pct:>15.2f}%")
    lines.append(f"  Stores as % of ROI Instructions:   {store_pct:>15.2f}%")
    lines.append(f"  Spills as % of ROI Instructions:   {spill_pct:>15.2f}%")
    lines.append("")
    
    # Spill-to-load/store ratios
    spill_to_load_str = (
        f"{(roi_spills / roi_loads) * 100:>15.2f}%" if roi_loads else f"{'N/A':>15}"
    )
    lines.append(f"  Spills as % of ROI Loads:          {spill_to_load_str}")
    
    spill_to_store_str = (
        f"{(roi_spills / roi_stores) * 100:>15.2f}%" if roi_stores else f"{'N/A':>15}"
    )
    lines.append(f"  Spills as % of ROI Stores:         {spill_to_store_str}")
    
    lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# MAIN EXECUTION & HELPER FUNCTIONS
# =============================================================================

def parse_arguments():
    """
    Parses command-line arguments.
    Returns the m5out directory to analyze.
    """
    if len(sys.argv) >= 2:
        m5out_dir = sys.argv[1]
        print(f"📌 Using command line argument: {m5out_dir}")
    else:
        m5out_dir = DEFAULT_M5OUT_DIRECTORY
        print(f"📌 Using default directory: {m5out_dir}")
        print(
            f"💡 Tip: You can override by running: python3 {sys.argv[0]} <m5out_directory>"
        )
    print()
    return m5out_dir


def validate_paths(m5out_dir, config_file, stats_file):
    """
    Validates that the m5out directory and required files exist.
    Exits script if required paths are missing.
    """
    if not os.path.isdir(m5out_dir):
        print(f"❌ Error: Directory not found: {m5out_dir}")
        print(
            f"💡 Please update DEFAULT_M5OUT_DIRECTORY or provide a valid path"
        )
        sys.exit(1)

    if not os.path.exists(config_file):
        print(f"❌ Error: Config file not found: {config_file}")
        print("💡 Make sure you are pointing to a valid m5out directory.")
        sys.exit(1)

    if not os.path.exists(stats_file):
        print(f"❌ Error: Stats file not found: {stats_file}")
        print("💡 Make sure you are pointing to a valid m5out directory.")
        sys.exit(1)
    
    print("✅ Directory and required files found.")


def get_spill_file_name(isa):
    """
    Returns the correct spill stats filename based on the detected ISA.
    Uses the ISA_SPILL_FILES dictionary.
    
    Args:
        isa (str): The ISA string (e.g., "RISCV", "X86")
        
    Returns:
        str: The corresponding spill file name.
    """
    isa_upper = isa.upper()
    spill_file_name = ISA_SPILL_FILES.get(isa_upper, ISA_SPILL_FILES["UNKNOWN"])
    
    if isa_upper not in ISA_SPILL_FILES:
        print(
            f"⚠️  Unknown ISA '{isa}'. Defaulting to spill file: {spill_file_name}"
        )
    
    return spill_file_name


def print_analysis_header(m5out_dir, config_file, stats_file, spill_file):
    """
    Prints the initial status messages about files being analyzed.
    """
    print()
    print(f"🔍 Analyzing m5out directory: {m5out_dir}")
    print(f"📄 Reading config from: {config_file}")
    print(f"📄 Reading stats from: {stats_file}")
    print(f"📄 Reading spill data from: {spill_file}")
    print()


def save_and_print_report(report_content, m5out_dir, output_file_name):
    """
    Prints the report to the console and saves it to a file.
    
    Args:
        report_content (str): The full text of the report
        m5out_dir (str): The directory to save the report in
        output_file_name (str): The name of the output file
    """
    output_file = os.path.join(m5out_dir, output_file_name)
    
    # Print to console
    print(report_content)
    
    # Save to file
    try:
        with open(output_file, "w") as f:
            f.write(report_content)
        print()
        print(f"✅ Report saved to: {output_file}")
    except IOError as e:
        print()
        print(f"❌ Error: Could not write report to file: {e}")


def main():
    """
    Main entry point - processes command line arguments and executes analysis.
    """
    # 1. Get m5out directory from command line or default
    m5out_dir = parse_arguments()
    
    # 2. Define and validate required file paths
    config_file = os.path.join(m5out_dir, CONFIG_FILE_NAME)
    stats_file = os.path.join(m5out_dir, STATS_FILE_NAME)
    validate_paths(m5out_dir, config_file, stats_file)

    # 3. Parse config to get simulation info and DETECT ISA
    print("⚙️  Parsing configuration and detecting ISA...")
    config_info = parse_config_json(config_file)
    isa = config_info.get("isa", "UNKNOWN")
    print(f"🧩 Detected ISA: {isa}")
    
    # 4. Determine spill file path based on detected ISA
    spill_file_name = get_spill_file_name(isa)
    spill_file = os.path.join(m5out_dir, spill_file_name)

    # 5. Print header
    print_analysis_header(m5out_dir, config_file, stats_file, spill_file)
    
    # 6. Read and process data
    print("📊 Reading all data from gem5 output files...")
    data = read_data(stats_file, spill_file)
    print(
        f"✅ Data loaded: {data.get('roi_instructions', 0):,} instructions, "
        f"{data.get('roi_spills', 0):,} spills detected"
    )
    print()

    # 7. Generate report
    print("Generating report...")
    report = generate_report(m5out_dir, config_info, data)

    # 8. Save and print report
    save_and_print_report(report, m5out_dir, OUTPUT_FILE_NAME)


if __name__ == "__main__":
    main()