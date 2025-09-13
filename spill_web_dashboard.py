#!/usr/bin/env python3
"""
Register Spill Analysis Web Dashboard
=====================================

This Python script creates a comprehensive web-based visualization dashboard for register spill analysis
using data from gem5 simulation outputs. It combines statistics from multiple sources to provide
detailed insights into register spilling behavior.

Data Sources:
- m5out/stats.txt: gem5 simulation statistics 
- m5out/cpp_spill_log.txt: Custom spill detection log
- m5out/config.json: Simulation configuration (optional)

Author: Register Spilling Research Team
Date: September 12, 2025
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import numpy as np
import json
import re
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Set matplotlib to use non-interactive backend
plt.switch_backend('Agg')

class SpillAnalysisWebDashboard:
    def __init__(self, gem5_output_dir="m5out"):
        """
        Initialize the dashboard with gem5 output directory
        
        Args:
            gem5_output_dir (str): Path to gem5 output directory containing stats.txt, cpp_spill_log.txt etc.
        """
        self.gem5_dir = Path(gem5_output_dir)
        self.stats_file = self.gem5_dir / "stats.txt"
        self.spill_log_file = self.gem5_dir / "cpp_spill_log.txt" 
        self.config_file = self.gem5_dir / "config.json"
        
        # Data containers
        self.gem5_stats = {}
        self.spill_data = None
        self.summary_stats = {}
        
        # Output directory for generated plots
        self.output_dir = Path("dashboard_output")
        self.output_dir.mkdir(exist_ok=True)
        
        # Load all data
        self.load_gem5_stats()
        self.load_spill_data()
        self.calculate_summary_stats()
        
    def load_gem5_stats(self):
        """
        Load statistics from gem5 stats.txt file
        Data Source: m5out/stats.txt
        """
        print(f"📊 Loading gem5 statistics from: {self.stats_file}")
        
        if not self.stats_file.exists():
            print(f"❌ Error: {self.stats_file} not found!")
            return
            
        with open(self.stats_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('-'):
                    # Parse format: "stat_name    value    # description"
                    parts = line.split()
                    if len(parts) >= 2:
                        stat_name = parts[0]
                        try:
                            stat_value = float(parts[1])
                            self.gem5_stats[stat_name] = stat_value
                        except ValueError:
                            self.gem5_stats[stat_name] = parts[1]
        
        print(f"✅ Loaded {len(self.gem5_stats)} statistics from stats.txt")
        
        # Key statistics we need
        key_stats = [
            'simInsts',           # Line 10: Total instructions
            'simOps',             # Line 11: Total ops (including micro ops)  
            'simTicks',           # Line 4: Simulation ticks
            'system.cpu.numCycles',  # Line 15: CPU cycles
            'system.cpu.commitStats0.numLoadInsts',   # Line 29: Load instructions
            'system.cpu.commitStats0.numStoreInsts',  # Line 30: Store instructions
            'system.cpu.executeStats0.numStoreInsts', # Line 128: Executed stores
            'system.cpu.cpi',     # CPI metric
            'system.cpu.ipc'      # IPC metric
        ]
        
        print("\n📋 Key Statistics Extracted:")
        for stat in key_stats:
            if stat in self.gem5_stats:
                print(f"   {stat}: {self.gem5_stats[stat]}")
            else:
                print(f"   {stat}: NOT FOUND")
    
    def load_spill_data(self):
        """
        Load spill detection data from cpp_spill_log.txt
        Data Source: m5out/cpp_spill_log.txt
        """
        print(f"\n🎯 Loading spill data from: {self.spill_log_file}")
        
        if not self.spill_log_file.exists():
            print(f"❌ Error: {self.spill_log_file} not found!")
            return
            
        # Read CSV data, skipping header comments
        spill_rows = []
        with open(self.spill_log_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('SPILL,'):
                    # Parse: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count
                    parts = line.split(',')
                    if len(parts) >= 9:
                        spill_rows.append({
                            'store_pc': parts[1],
                            'load_pc': parts[2], 
                            'memory_address': parts[3],
                            'store_tick': int(parts[4]),
                            'load_tick': int(parts[5]),
                            'tick_diff': int(parts[6]),
                            'store_inst_count': int(parts[7]),
                            'load_inst_count': int(parts[8])
                        })
        
        self.spill_data = pd.DataFrame(spill_rows)
        print(f"✅ Loaded {len(self.spill_data)} spill events from cpp_spill_log.txt")
        
        if len(self.spill_data) > 0:
            print(f"   🔍 Unique memory addresses: {self.spill_data['memory_address'].nunique()}")
            print(f"   🔍 Unique store PCs: {self.spill_data['store_pc'].nunique()}")
            print(f"   🔍 Unique load PCs: {self.spill_data['load_pc'].nunique()}")
    
    def calculate_summary_stats(self):
        """
        Calculate derived statistics combining gem5 and spill data
        """
        print("\n📈 Calculating summary statistics...")
        
        # Basic counts
        total_instructions = self.gem5_stats.get('simInsts', 0)
        total_ops = self.gem5_stats.get('simOps', 0)
        load_instructions = self.gem5_stats.get('system.cpu.commitStats0.numLoadInsts', 0)
        store_instructions = self.gem5_stats.get('system.cpu.commitStats0.numStoreInsts', 0)
        total_memory_ops = load_instructions + store_instructions
        
        # Spill counts
        total_spills = len(self.spill_data) if self.spill_data is not None else 0
        
        # Calculate rates
        spill_rate_memory = (total_spills / total_memory_ops * 100) if total_memory_ops > 0 else 0
        spill_rate_instructions = (total_spills / total_instructions * 100) if total_instructions > 0 else 0
        memory_intensity = (total_memory_ops / total_instructions * 100) if total_instructions > 0 else 0
        
        self.summary_stats = {
            'total_instructions': int(total_instructions),
            'total_ops': int(total_ops),
            'total_memory_ops': int(total_memory_ops),
            'load_instructions': int(load_instructions),
            'store_instructions': int(store_instructions),
            'total_spills': total_spills,
            'non_spill_memory_ops': int(total_memory_ops - total_spills),
            'spill_rate_memory': spill_rate_memory,
            'spill_rate_instructions': spill_rate_instructions,
            'memory_intensity': memory_intensity,
            'cpu_cycles': int(self.gem5_stats.get('system.cpu.numCycles', 0)),
            'simulation_ticks': int(self.gem5_stats.get('simTicks', 0)),
            'cpi': self.gem5_stats.get('system.cpu.cpi', 0),
            'ipc': self.gem5_stats.get('system.cpu.ipc', 0)
        }
        
        print("✅ Summary statistics calculated:")
        for key, value in self.summary_stats.items():
            print(f"   {key}: {value}")
    
    def create_overview_plots(self):
        """
        Create overview plots with pie charts and summary metrics
        """
        print("\n📊 Creating overview plots...")
        
        # Create figure with subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('🎯 Register Spill Analysis Overview Dashboard', fontsize=20, fontweight='bold')
        
        # Pie chart 1: Instructions breakdown
        instruction_labels = ['Spill Instructions', 'Regular Instructions']
        instruction_sizes = [
            self.summary_stats['total_spills'],
            self.summary_stats['total_instructions'] - self.summary_stats['total_spills']
        ]
        colors1 = ['#ff6b6b', '#4ecdc4']
        
        wedges1, texts1, autotexts1 = ax1.pie(instruction_sizes, labels=instruction_labels, 
                                              autopct='%1.1f%%', startangle=90, colors=colors1)
        ax1.set_title('🎯 Spill vs Regular Instructions\n(Total: {:,} instructions)'.format(
            self.summary_stats['total_instructions']), fontsize=14, fontweight='bold')
        
        # Pie chart 2: Memory operations breakdown  
        memory_labels = ['Spill Operations', 'Regular Memory Ops']
        memory_sizes = [
            self.summary_stats['total_spills'],
            self.summary_stats['non_spill_memory_ops']
        ]
        colors2 = ['#ff9ff3', '#54a0ff']
        
        wedges2, texts2, autotexts2 = ax2.pie(memory_sizes, labels=memory_labels,
                                              autopct='%1.1f%%', startangle=90, colors=colors2)
        ax2.set_title('💾 Spill vs Regular Memory Operations\n(Total: {:,} memory ops)'.format(
            self.summary_stats['total_memory_ops']), fontsize=14, fontweight='bold')
        
        # Bar chart: Load vs Store instructions
        load_store_labels = ['Load Instructions', 'Store Instructions']
        load_store_values = [
            self.summary_stats['load_instructions'],
            self.summary_stats['store_instructions']
        ]
        bars = ax3.bar(load_store_labels, load_store_values, color=['#2ecc71', '#e74c3c'])
        ax3.set_title('📥📤 Load vs Store Instructions', fontsize=14, fontweight='bold')
        ax3.set_ylabel('Count')
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height):,}', ha='center', va='bottom')
        
        # Summary metrics text
        ax4.axis('off')
        summary_text = f"""🔍 KEY PERFORMANCE METRICS

📊 Execution Statistics:
   • Total Instructions: {self.summary_stats['total_instructions']:,}
   • Total Operations: {self.summary_stats['total_ops']:,}
   • CPU Cycles: {self.summary_stats['cpu_cycles']:,}
   • Simulation Ticks: {self.summary_stats['simulation_ticks']:,}

🎯 Spill Analysis:
   • Total Spills Detected: {self.summary_stats['total_spills']:,}
   • Spill Rate (Memory): {self.summary_stats['spill_rate_memory']:.2f}%
   • Spill Rate (Instructions): {self.summary_stats['spill_rate_instructions']:.2f}%

⚡ Performance Metrics:
   • CPI (Cycles/Instruction): {self.summary_stats['cpi']:.3f}
   • IPC (Instructions/Cycle): {self.summary_stats['ipc']:.6f}
   • Memory Intensity: {self.summary_stats['memory_intensity']:.2f}%

💾 Memory Operations:
   • Load Instructions: {self.summary_stats['load_instructions']:,}
   • Store Instructions: {self.summary_stats['store_instructions']:,}
   • Total Memory Ops: {self.summary_stats['total_memory_ops']:,}"""
        
        ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, fontsize=11,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
        
        plt.tight_layout()
        output_file = self.output_dir / "overview_dashboard.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"✅ Overview dashboard saved to: {output_file}")
        
    def create_spill_analysis_plots(self):
        """
        Create spill-specific analysis plots
        """
        if self.spill_data is None or len(self.spill_data) == 0:
            print("❌ No spill data available for analysis plots")
            return
            
        print("\n🎯 Creating spill analysis plots...")
        
        # Create figure for spill analysis
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('🎯 Detailed Spill Analysis Dashboard', fontsize=20, fontweight='bold')
        
        # 1. Spill latency histogram
        ax1.hist(self.spill_data['tick_diff'], bins=30, color='skyblue', alpha=0.7, edgecolor='black')
        ax1.set_title('⏰ Spill Latency Distribution', fontweight='bold', fontsize=14)
        ax1.set_xlabel('Latency (ticks)')
        ax1.set_ylabel('Frequency')
        ax1.grid(True, alpha=0.3)
        
        # Add statistics text
        latency_stats = f"Mean: {self.spill_data['tick_diff'].mean():,.0f}\nMedian: {self.spill_data['tick_diff'].median():,.0f}\nStd: {self.spill_data['tick_diff'].std():,.0f}"
        ax1.text(0.7, 0.95, latency_stats, transform=ax1.transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
        
        # 2. Top spill hotspots
        top_store_pcs = self.spill_data['store_pc'].value_counts().head(8)
        bars = ax2.bar(range(len(top_store_pcs)), top_store_pcs.values, color='coral')
        ax2.set_title('🔥 Top Spill Hotspots (Store PCs)', fontweight='bold', fontsize=14)
        ax2.set_xlabel('Store PC (Top 8)')
        ax2.set_ylabel('Spill Count')
        ax2.set_xticks(range(len(top_store_pcs)))
        ax2.set_xticklabels([f'{pc[:8]}...' for pc in top_store_pcs.index], rotation=45)
        
        # Add value labels on bars
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom')
        
        # 3. Memory address distribution
        mem_addr_counts = self.spill_data['memory_address'].value_counts().head(10)
        ax3.bar(range(len(mem_addr_counts)), mem_addr_counts.values, color='lightgreen')
        ax3.set_title('💾 Top Spill Memory Addresses', fontweight='bold', fontsize=14)
        ax3.set_xlabel('Memory Address (Top 10)')
        ax3.set_ylabel('Spill Count')
        ax3.set_xticks(range(len(mem_addr_counts)))
        ax3.set_xticklabels([f'{addr[:8]}...' for addr in mem_addr_counts.index], rotation=45)
        
        # 4. Spill timeline
        # Sample data for timeline (every 20th spill to avoid overcrowding)
        sample_spills = self.spill_data.iloc[::max(1, len(self.spill_data)//100)]
        scatter = ax4.scatter(sample_spills['load_tick'], sample_spills['tick_diff'], 
                   alpha=0.6, s=30, c=sample_spills['tick_diff'], cmap='viridis')
        ax4.set_title('📈 Spill Timeline Analysis', fontweight='bold', fontsize=14)
        ax4.set_xlabel('Simulation Time (ticks)')
        ax4.set_ylabel('Spill Latency (ticks)')
        ax4.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax4, label='Latency (ticks)')
        
        plt.tight_layout()
        output_file = self.output_dir / "spill_analysis_dashboard.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"✅ Spill analysis dashboard saved to: {output_file}")
    
    def generate_detailed_report(self):
        """
        Generate comprehensive text report
        """
        print("\n📄 Generating detailed report...")
        
        report_content = f"""
{'='*100}
🎯 COMPREHENSIVE REGISTER SPILL ANALYSIS REPORT
{'='*100}

📂 DATA SOURCES:
   • gem5 Statistics: {self.stats_file}
   • Spill Detection Log: {self.spill_log_file}
   • Configuration: {self.config_file}

📊 CORE INSTRUCTION STATISTICS (from stats.txt):
{'─'*70}
   Line 10 | simInsts                     : {self.gem5_stats.get('simInsts', 'N/A'):>12} (Total instructions)
   Line 11 | simOps                       : {self.gem5_stats.get('simOps', 'N/A'):>12} (Total ops + micro ops)
   Line 15 | system.cpu.numCycles         : {self.gem5_stats.get('system.cpu.numCycles', 'N/A'):>12} (CPU cycles)
   Line 4  | simTicks                     : {self.gem5_stats.get('simTicks', 'N/A'):>12} (Simulation ticks)
   Line 29 | commitStats0.numLoadInsts    : {self.gem5_stats.get('system.cpu.commitStats0.numLoadInsts', 'N/A'):>12} (Load instructions)
   Line 30 | commitStats0.numStoreInsts   : {self.gem5_stats.get('system.cpu.commitStats0.numStoreInsts', 'N/A'):>12} (Store instructions)
   Line 128| executeStats0.numStoreInsts  : {self.gem5_stats.get('system.cpu.executeStats0.numStoreInsts', 'N/A'):>12} (Executed stores)

🎯 SPILL DETECTION RESULTS (from cpp_spill_log.txt):
{'─'*70}
   Total Spill Events Detected          : {self.summary_stats['total_spills']:>12,}
   Unique Memory Addresses Involved     : {self.spill_data['memory_address'].nunique() if self.spill_data is not None else 'N/A':>12}
   Unique Store PC Addresses            : {self.spill_data['store_pc'].nunique() if self.spill_data is not None else 'N/A':>12}
   Unique Load PC Addresses             : {self.spill_data['load_pc'].nunique() if self.spill_data is not None else 'N/A':>12}

⚡ PERFORMANCE ANALYSIS:
{'─'*70}
   CPI (Cycles Per Instruction)         : {self.summary_stats['cpi']:>12.3f}
   IPC (Instructions Per Cycle)         : {self.summary_stats['ipc']:>12.6f}
   Spill Rate (Memory Operations)       : {self.summary_stats['spill_rate_memory']:>12.2f}%
   Spill Rate (All Instructions)        : {self.summary_stats['spill_rate_instructions']:>12.2f}%
   Memory Intensity                     : {self.summary_stats['memory_intensity']:>12.2f}%
   Store/Load Ratio                     : {(self.summary_stats['store_instructions']/self.summary_stats['load_instructions']) if self.summary_stats['load_instructions'] > 0 else 0:>12.3f}

💾 MEMORY OPERATION BREAKDOWN:
{'─'*70}
   Total Memory Operations              : {self.summary_stats['total_memory_ops']:>12,}
   ├── Load Instructions                : {self.summary_stats['load_instructions']:>12,} ({(self.summary_stats['load_instructions']/self.summary_stats['total_memory_ops']*100) if self.summary_stats['total_memory_ops'] > 0 else 0:>6.2f}%)
   ├── Store Instructions               : {self.summary_stats['store_instructions']:>12,} ({(self.summary_stats['store_instructions']/self.summary_stats['total_memory_ops']*100) if self.summary_stats['total_memory_ops'] > 0 else 0:>6.2f}%)
   ├── Spill Operations                 : {self.summary_stats['total_spills']:>12,} ({self.summary_stats['spill_rate_memory']:>6.2f}%)
   └── Regular Memory Operations        : {self.summary_stats['non_spill_memory_ops']:>12,} ({(self.summary_stats['non_spill_memory_ops']/self.summary_stats['total_memory_ops']*100) if self.summary_stats['total_memory_ops'] > 0 else 0:>6.2f}%)

🔍 DETAILED gem5 STATISTICS:
{'─'*70}
"""
        
        # Add all gem5 statistics
        for stat_name, stat_value in sorted(self.gem5_stats.items()):
            if isinstance(stat_value, (int, float)):
                report_content += f"   {stat_name:<50} : {stat_value:>15}\n"
            else:
                report_content += f"   {stat_name:<50} : {str(stat_value):>15}\n"
        
        if self.spill_data is not None and len(self.spill_data) > 0:
            report_content += f"""
🎯 SPILL TIMING ANALYSIS:
{'─'*70}
   Average Spill Latency                : {self.spill_data['tick_diff'].mean():>12,.0f} ticks
   Min Spill Latency                    : {self.spill_data['tick_diff'].min():>12,} ticks
   Max Spill Latency                    : {self.spill_data['tick_diff'].max():>12,} ticks
   Median Spill Latency                 : {self.spill_data['tick_diff'].median():>12,.0f} ticks
   Std Dev Spill Latency                : {self.spill_data['tick_diff'].std():>12,.0f} ticks

🔥 SPILL HOTSPOTS (Top Program Counters):
{'─'*70}
"""
            # Top spill PCs
            store_pc_counts = self.spill_data['store_pc'].value_counts().head(15)
            for i, (pc, count) in enumerate(store_pc_counts.items(), 1):
                report_content += f"   #{i:>2} | Store PC {pc}: {count:>6} spill events\n"
                
            report_content += f"""
💾 TOP SPILL MEMORY ADDRESSES:
{'─'*70}
"""
            # Top memory addresses
            mem_addr_counts = self.spill_data['memory_address'].value_counts().head(15)
            for i, (addr, count) in enumerate(mem_addr_counts.items(), 1):
                report_content += f"   #{i:>2} | Memory Address {addr}: {count:>6} spill events\n"
        
        report_content += f"""
{'='*100}
📊 ANALYSIS COMPLETE - Report Generated at {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
📁 Output Files Generated in: {self.output_dir}/
   - overview_dashboard.png: Main overview charts
   - spill_analysis_dashboard.png: Detailed spill analysis
   - detailed_report.txt: This comprehensive report
{'='*100}
"""
        
        # Save report to file
        report_file = self.output_dir / "detailed_report.txt"
        with open(report_file, 'w') as f:
            f.write(report_content)
        
        print(f"✅ Detailed report saved to: {report_file}")
        return report_content
    
    def create_data_summary_csv(self):
        """
        Create CSV summary of key metrics
        """
        print("\n📊 Creating data summary CSV...")
        
        # Create summary dataframe
        summary_data = []
        
        # Add gem5 stats
        for stat_name, stat_value in self.gem5_stats.items():
            summary_data.append({
                'Category': 'gem5_stats',
                'Metric': stat_name,
                'Value': stat_value,
                'Source': 'stats.txt',
                'Description': 'gem5 simulation statistic'
            })
        
        # Add derived metrics
        derived_metrics = [
            ('total_instructions', 'Total executed instructions'),
            ('total_ops', 'Total operations including micro-ops'),
            ('total_memory_ops', 'Total memory operations (loads + stores)'),
            ('total_spills', 'Total spill events detected'),
            ('spill_rate_memory', 'Spill rate as percentage of memory operations'),
            ('spill_rate_instructions', 'Spill rate as percentage of all instructions'),
            ('memory_intensity', 'Memory operations as percentage of all instructions')
        ]
        
        for metric, description in derived_metrics:
            summary_data.append({
                'Category': 'derived_metrics',
                'Metric': metric,
                'Value': self.summary_stats[metric],
                'Source': 'calculated',
                'Description': description
            })
        
        # Add spill statistics if available
        if self.spill_data is not None and len(self.spill_data) > 0:
            spill_metrics = [
                ('unique_memory_addresses', self.spill_data['memory_address'].nunique(), 'Unique memory addresses involved in spills'),
                ('unique_store_pcs', self.spill_data['store_pc'].nunique(), 'Unique store PC addresses'),
                ('unique_load_pcs', self.spill_data['load_pc'].nunique(), 'Unique load PC addresses'),
                ('avg_spill_latency', self.spill_data['tick_diff'].mean(), 'Average spill latency in ticks'),
                ('min_spill_latency', self.spill_data['tick_diff'].min(), 'Minimum spill latency in ticks'),
                ('max_spill_latency', self.spill_data['tick_diff'].max(), 'Maximum spill latency in ticks'),
                ('median_spill_latency', self.spill_data['tick_diff'].median(), 'Median spill latency in ticks')
            ]
            
            for metric, value, description in spill_metrics:
                summary_data.append({
                    'Category': 'spill_analysis',
                    'Metric': metric,
                    'Value': value,
                    'Source': 'cpp_spill_log.txt',
                    'Description': description
                })
        
        # Create DataFrame and save
        summary_df = pd.DataFrame(summary_data)
        csv_file = self.output_dir / "metrics_summary.csv"
        summary_df.to_csv(csv_file, index=False)
        print(f"✅ Metrics summary CSV saved to: {csv_file}")
    
    def run_analysis(self):
        """
        Run complete analysis and generate all outputs
        """
        print("🚀 Starting comprehensive register spill analysis...")
        print("="*80)
        
        # Generate visualizations
        self.create_overview_plots()
        self.create_spill_analysis_plots()
        
        # Generate reports
        report_content = self.generate_detailed_report()
        self.create_data_summary_csv()
        
        print("\n" + "="*80)
        print("🎉 ANALYSIS COMPLETE!")
        print("="*80)
        print(f"📁 All outputs saved to: {self.output_dir}/")
        print("\n📋 Generated Files:")
        for file in self.output_dir.iterdir():
            if file.is_file():
                print(f"   ✅ {file.name}")
        
        print(f"\n📊 QUICK SUMMARY:")
        print(f"   🎯 Total Spills Detected: {self.summary_stats['total_spills']:,}")
        print(f"   📈 Total Instructions: {self.summary_stats['total_instructions']:,}")
        print(f"   💾 Total Memory Operations: {self.summary_stats['total_memory_ops']:,}")
        print(f"   ⚡ Spill Rate (Memory): {self.summary_stats['spill_rate_memory']:.2f}%")
        print(f"   🔥 CPI: {self.summary_stats['cpi']:.3f}")
        
        return report_content

def main():
    """
    Main function to create and run the spill analysis dashboard
    """
    print("🚀 Starting Register Spill Analysis Web Dashboard...")
    print("📂 Looking for gem5 output files in 'm5out' directory...")
    
    # Create dashboard instance
    dashboard = SpillAnalysisWebDashboard("m5out")
    
    # Run complete analysis
    dashboard.run_analysis()

if __name__ == "__main__":
    main()
