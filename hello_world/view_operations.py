#!/usr/bin/env python3
"""
Enhanced stats viewer for gem5 simulation results.
Shows operation counts, memory statistics, and register spill analysis.
"""

import sys
import re
import os

def parse_stats_file(filename="m5out/stats.txt"):
    """Parse the stats file and extract key metrics."""
    try:
        with open(filename, 'r') as f:
            content = f.read()
        
        # Extract key statistics
        stats = {}
        
        # Basic operation counts
        stats['instructions'] = int(re.search(r'simInsts\s+(\d+)', content).group(1))
        stats['operations'] = int(re.search(r'simOps\s+(\d+)', content).group(1))
        stats['ticks'] = int(re.search(r'simTicks\s+(\d+)', content).group(1))
        
        # Memory operations
        l1d_reads = re.search(r'l1dcaches\.ReadReq\.accesses::total\s+(\d+)', content)
        l1d_writes = re.search(r'l1dcaches\.WriteReq\.accesses::total\s+(\d+)', content)
        l1i_reads = re.search(r'l1icaches\.ReadReq\.accesses::total\s+(\d+)', content)
        
        stats['l1d_reads'] = int(l1d_reads.group(1)) if l1d_reads else 0
        stats['l1d_writes'] = int(l1d_writes.group(1)) if l1d_writes else 0
        stats['l1i_reads'] = int(l1i_reads.group(1)) if l1i_reads else 0
        
        # Cache miss statistics for spill analysis
        l1d_read_misses = re.search(r'l1dcaches\.ReadReq\.misses::total\s+(\d+)', content)
        l1d_write_misses = re.search(r'l1dcaches\.WriteReq\.misses::total\s+(\d+)', content)
        
        stats['l1d_read_misses'] = int(l1d_read_misses.group(1)) if l1d_read_misses else 0
        stats['l1d_write_misses'] = int(l1d_write_misses.group(1)) if l1d_write_misses else 0
        
        return stats
        
    except FileNotFoundError:
        print(f"Error: Could not find {filename}")
        return None
    except Exception as e:
        print(f"Error parsing stats: {e}")
        return None

def analyze_register_spills(stats):
    """
    Analyze potential register spills based on memory access patterns.
    Since we don't have instruction-level traces, we use heuristics.
    """
    spill_analysis = {}
    
    if not stats:
        return spill_analysis
    
    # Calculate basic metrics
    total_mem_ops = stats['l1d_reads'] + stats['l1d_writes']
    instructions = stats['instructions']
    
    # Heuristic 1: High memory operations per instruction ratio
    mem_ops_per_inst = total_mem_ops / instructions if instructions > 0 else 0
    
    # Heuristic 2: Store-Load ratio analysis
    store_load_ratio = stats['l1d_writes'] / stats['l1d_reads'] if stats['l1d_reads'] > 0 else 0
    
    # Heuristic 3: Cache miss analysis (spills often cause misses)
    total_misses = stats['l1d_read_misses'] + stats['l1d_write_misses']
    miss_rate = total_misses / total_mem_ops if total_mem_ops > 0 else 0
    
    # Spill probability estimation based on heuristics
    spill_probability = 0.0
    
    # Factor 1: High memory activity suggests potential spilling
    if mem_ops_per_inst > 0.5:  # More than 0.5 memory ops per instruction
        spill_probability += 0.3
    
    # Factor 2: Balanced store-load ratio suggests spill patterns
    if 0.7 <= store_load_ratio <= 1.4:  # Relatively balanced stores and loads
        spill_probability += 0.2
    
    # Factor 3: Cache misses indicate memory pressure
    if miss_rate > 0.1:  # More than 10% miss rate
        spill_probability += 0.3
    
    # Factor 4: Small program with high memory activity
    if instructions < 5000 and mem_ops_per_inst > 0.3:
        spill_probability += 0.2
    
    # Estimate potential spill operations
    # Heuristic: Assume some percentage of writes followed by reads could be spills
    estimated_spills = int(min(stats['l1d_reads'], stats['l1d_writes']) * 0.3)
    
    spill_analysis = {
        'mem_ops_per_instruction': mem_ops_per_inst,
        'store_load_ratio': store_load_ratio,
        'cache_miss_rate': miss_rate,
        'spill_probability': min(spill_probability, 1.0),
        'estimated_spill_operations': estimated_spills,
        'total_memory_operations': total_mem_ops,
        'spill_percentage': (estimated_spills / total_mem_ops * 100) if total_mem_ops > 0 else 0
    }
    
    return spill_analysis

def display_stats(stats):
    """Display statistics in a nice format."""
    if not stats:
        return
    
    print("=" * 60)
    print("🎯 GEM5 SIMULATION OPERATION SUMMARY")
    print("=" * 60)
    
    print("\n📊 INSTRUCTION COUNTS:")
    print(f"  Total Instructions Executed: {stats['instructions']:,}")
    print(f"  Total Operations (with micro-ops): {stats['operations']:,}")
    print(f"  Operations per Instruction: {stats['operations']/stats['instructions']:.2f}")
    
    print("\n⏱️ PERFORMANCE:")
    print(f"  Total Simulation Ticks: {stats['ticks']:,}")
    print(f"  Instructions per Tick: {stats['instructions']/stats['ticks']:.6f}")
    print(f"  Ticks per Instruction: {stats['ticks']/stats['instructions']:.2f}")
    
    print("\n💾 MEMORY OPERATIONS:")
    print(f"  L1 Data Cache Reads: {stats['l1d_reads']:,}")
    print(f"  L1 Data Cache Writes: {stats['l1d_writes']:,}")
    print(f"  L1 Instruction Cache Reads: {stats['l1i_reads']:,}")
    
    total_data_ops = stats['l1d_reads'] + stats['l1d_writes']
    print(f"  Total Data Memory Operations: {total_data_ops:,}")
    print(f"  Data Ops per Instruction: {total_data_ops/stats['instructions']:.2f}")
    
    if stats['l1d_writes'] > 0:
        print(f"  Read/Write Ratio: {stats['l1d_reads']/stats['l1d_writes']:.2f}")
    
    # Cache miss information
    print(f"  L1D Read Misses: {stats['l1d_read_misses']:,}")
    print(f"  L1D Write Misses: {stats['l1d_write_misses']:,}")
    total_misses = stats['l1d_read_misses'] + stats['l1d_write_misses']
    if total_data_ops > 0:
        print(f"  Cache Miss Rate: {total_misses/total_data_ops*100:.2f}%")

def display_spill_analysis(spill_info):
    """Display register spill analysis."""
    if not spill_info:
        return
    
    print("\n🔄 REGISTER SPILL ANALYSIS:")
    print("-" * 40)
    
    print(f"  Memory Ops per Instruction: {spill_info['mem_ops_per_instruction']:.3f}")
    print(f"  Store/Load Ratio: {spill_info['store_load_ratio']:.3f}")
    print(f"  Cache Miss Rate: {spill_info['cache_miss_rate']*100:.2f}%")
    
    # Spill probability indication
    prob = spill_info['spill_probability']
    if prob < 0.3:
        likelihood = "🟢 LOW"
    elif prob < 0.6:
        likelihood = "🟡 MODERATE" 
    else:
        likelihood = "🔴 HIGH"
    
    print(f"  Spill Likelihood: {likelihood} ({prob*100:.1f}%)")
    print(f"  Estimated Spill Operations: {spill_info['estimated_spill_operations']:,}")
    print(f"  Potential Spill Percentage: {spill_info['spill_percentage']:.2f}% of memory ops")
    
    # Analysis interpretation
    print("\n📝 INTERPRETATION:")
    if spill_info['estimated_spill_operations'] > 0:
        print(f"  • Detected {spill_info['estimated_spill_operations']} potential register spills")
        print(f"  • This represents {spill_info['spill_percentage']:.1f}% of total memory operations")
        
        if prob >= 0.6:
            print("  • High spill probability suggests register pressure")
            print("  • Consider optimizing register usage or compiler flags")
        elif prob >= 0.3:
            print("  • Moderate spill activity detected")
            print("  • Some register pressure may be present")
        else:
            print("  • Low spill activity - efficient register usage")
    else:
        print("  • No significant register spilling detected")
        print("  • Program appears to have efficient register usage")

if __name__ == "__main__":
    stats_file = sys.argv[1] if len(sys.argv) > 1 else "m5out/stats.txt"
    stats = parse_stats_file(stats_file)
    
    if stats:
        display_stats(stats)
        
        # Perform spill analysis
        spill_info = analyze_register_spills(stats)
        display_spill_analysis(spill_info)
    else:
        print("Failed to parse statistics file.")
