#!/usr/bin/env python3
"""
Register Spill Analysis Dashboard
=================================

This Python script creates a comprehensive visualization dashboard for register spill analysis
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
import tkinter as tk
from tkinter import ttk, scrolledtext
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import warnings
warnings.filterwarnings('ignore')

class SpillAnalysisDashboard:
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
    
    def create_dashboard(self):
        """
        Create the main GUI dashboard with visualizations and data tables
        """
        # Create main window
        self.root = tk.Tk()
        self.root.title("📊 Register Spill Analysis Dashboard - gem5 Simulation Results")
        self.root.geometry("1400x900")
        self.root.configure(bg='#f0f0f0')
        
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Overview & Pie Charts
        self.create_overview_tab(notebook)
        
        # Tab 2: Detailed Statistics
        self.create_stats_tab(notebook)
        
        # Tab 3: Spill Data Analysis
        self.create_spill_analysis_tab(notebook)
        
        # Tab 4: Raw Data Viewer
        self.create_raw_data_tab(notebook)
        
        print("\n🚀 Dashboard created successfully!")
        print("📱 GUI Interface launched - check the application window")
        
    def create_overview_tab(self, notebook):
        """
        Create overview tab with pie charts and summary metrics
        """
        overview_frame = ttk.Frame(notebook)
        notebook.add(overview_frame, text="📊 Overview")
        
        # Create matplotlib figure
        fig = Figure(figsize=(14, 8), facecolor='white')
        
        # Pie chart 1: Instructions breakdown
        ax1 = fig.add_subplot(2, 2, 1)
        instruction_labels = ['Spill Instructions', 'Regular Instructions']
        instruction_sizes = [
            self.summary_stats['total_spills'],
            self.summary_stats['total_instructions'] - self.summary_stats['total_spills']
        ]
        colors1 = ['#ff6b6b', '#4ecdc4']
        
        wedges1, texts1, autotexts1 = ax1.pie(instruction_sizes, labels=instruction_labels, 
                                              autopct='%1.1f%%', startangle=90, colors=colors1)
        ax1.set_title('🎯 Spill vs Regular Instructions\n(Total: {:,} instructions)'.format(
            self.summary_stats['total_instructions']), fontsize=12, fontweight='bold')
        
        # Pie chart 2: Memory operations breakdown  
        ax2 = fig.add_subplot(2, 2, 2)
        memory_labels = ['Spill Operations', 'Regular Memory Ops']
        memory_sizes = [
            self.summary_stats['total_spills'],
            self.summary_stats['non_spill_memory_ops']
        ]
        colors2 = ['#ff9ff3', '#54a0ff']
        
        wedges2, texts2, autotexts2 = ax2.pie(memory_sizes, labels=memory_labels,
                                              autopct='%1.1f%%', startangle=90, colors=colors2)
        ax2.set_title('💾 Spill vs Regular Memory Operations\n(Total: {:,} memory ops)'.format(
            self.summary_stats['total_memory_ops']), fontsize=12, fontweight='bold')
        
        # Bar chart: Load vs Store instructions
        ax3 = fig.add_subplot(2, 2, 3)
        load_store_labels = ['Load Instructions', 'Store Instructions']
        load_store_values = [
            self.summary_stats['load_instructions'],
            self.summary_stats['store_instructions']
        ]
        bars = ax3.bar(load_store_labels, load_store_values, color=['#2ecc71', '#e74c3c'])
        ax3.set_title('📥📤 Load vs Store Instructions', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Count')
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height):,}', ha='center', va='bottom')
        
        # Summary metrics table
        ax4 = fig.add_subplot(2, 2, 4)
        ax4.axis('off')
        
        summary_text = f"""
🔍 KEY PERFORMANCE METRICS

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
   • Total Memory Ops: {self.summary_stats['total_memory_ops']:,}
        """
        
        ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, fontsize=10,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
        
        fig.tight_layout()
        
        # Embed in tkinter
        canvas = FigureCanvasTkAgg(fig, overview_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def create_stats_tab(self, notebook):
        """
        Create detailed statistics tab with comprehensive data tables
        """
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="📈 Detailed Statistics")
        
        # Create text widget with scrollbar
        text_widget = scrolledtext.ScrolledText(stats_frame, wrap=tk.WORD, font=('Courier', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Comprehensive statistics report
        stats_content = f"""
{'='*80}
🎯 COMPREHENSIVE REGISTER SPILL ANALYSIS REPORT
{'='*80}

📂 DATA SOURCES:
   • gem5 Statistics: {self.stats_file}
   • Spill Detection Log: {self.spill_log_file}
   • Configuration: {self.config_file}

📊 CORE INSTRUCTION STATISTICS (from stats.txt):
{'─'*50}
   Line 10 | simInsts                     : {self.gem5_stats.get('simInsts', 'N/A'):>12} (Total instructions)
   Line 11 | simOps                       : {self.gem5_stats.get('simOps', 'N/A'):>12} (Total ops + micro ops)
   Line 15 | system.cpu.numCycles         : {self.gem5_stats.get('system.cpu.numCycles', 'N/A'):>12} (CPU cycles)
   Line 4  | simTicks                     : {self.gem5_stats.get('simTicks', 'N/A'):>12} (Simulation ticks)
   Line 29 | commitStats0.numLoadInsts    : {self.gem5_stats.get('system.cpu.commitStats0.numLoadInsts', 'N/A'):>12} (Load instructions)
   Line 30 | commitStats0.numStoreInsts   : {self.gem5_stats.get('system.cpu.commitStats0.numStoreInsts', 'N/A'):>12} (Store instructions)
   Line 128| executeStats0.numStoreInsts  : {self.gem5_stats.get('system.cpu.executeStats0.numStoreInsts', 'N/A'):>12} (Executed stores)

🎯 SPILL DETECTION RESULTS (from cpp_spill_log.txt):
{'─'*50}
   Total Spill Events Detected          : {self.summary_stats['total_spills']:>12,}
   Unique Memory Addresses Involved     : {self.spill_data['memory_address'].nunique() if self.spill_data is not None else 'N/A':>12}
   Unique Store PC Addresses            : {self.spill_data['store_pc'].nunique() if self.spill_data is not None else 'N/A':>12}
   Unique Load PC Addresses             : {self.spill_data['load_pc'].nunique() if self.spill_data is not None else 'N/A':>12}

⚡ PERFORMANCE ANALYSIS:
{'─'*50}
   CPI (Cycles Per Instruction)         : {self.summary_stats['cpi']:>12.3f}
   IPC (Instructions Per Cycle)         : {self.summary_stats['ipc']:>12.6f}
   Spill Rate (Memory Operations)       : {self.summary_stats['spill_rate_memory']:>12.2f}%
   Spill Rate (All Instructions)        : {self.summary_stats['spill_rate_instructions']:>12.2f}%
   Memory Intensity                     : {self.summary_stats['memory_intensity']:>12.2f}%
   Store/Load Ratio                     : {(self.summary_stats['store_instructions']/self.summary_stats['load_instructions']) if self.summary_stats['load_instructions'] > 0 else 0:>12.3f}

💾 MEMORY OPERATION BREAKDOWN:
{'─'*50}
   Total Memory Operations              : {self.summary_stats['total_memory_ops']:>12,}
   ├── Load Instructions                : {self.summary_stats['load_instructions']:>12,} ({(self.summary_stats['load_instructions']/self.summary_stats['total_memory_ops']*100) if self.summary_stats['total_memory_ops'] > 0 else 0:>6.2f}%)
   ├── Store Instructions               : {self.summary_stats['store_instructions']:>12,} ({(self.summary_stats['store_instructions']/self.summary_stats['total_memory_ops']*100) if self.summary_stats['total_memory_ops'] > 0 else 0:>6.2f}%)
   ├── Spill Operations                 : {self.summary_stats['total_spills']:>12,} ({self.summary_stats['spill_rate_memory']:>6.2f}%)
   └── Regular Memory Operations        : {self.summary_stats['non_spill_memory_ops']:>12,} ({(self.summary_stats['non_spill_memory_ops']/self.summary_stats['total_memory_ops']*100) if self.summary_stats['total_memory_ops'] > 0 else 0:>6.2f}%)

🔍 DETAILED gem5 STATISTICS:
{'─'*50}
"""
        
        # Add all gem5 statistics
        for stat_name, stat_value in sorted(self.gem5_stats.items()):
            if isinstance(stat_value, (int, float)):
                stats_content += f"   {stat_name:<40} : {stat_value:>15}\n"
            else:
                stats_content += f"   {stat_name:<40} : {str(stat_value):>15}\n"
        
        if self.spill_data is not None and len(self.spill_data) > 0:
            stats_content += f"""
🎯 SPILL TIMING ANALYSIS:
{'─'*50}
   Average Spill Latency                : {self.spill_data['tick_diff'].mean():>12,.0f} ticks
   Min Spill Latency                    : {self.spill_data['tick_diff'].min():>12,} ticks
   Max Spill Latency                    : {self.spill_data['tick_diff'].max():>12,} ticks
   Median Spill Latency                 : {self.spill_data['tick_diff'].median():>12,.0f} ticks
   Std Dev Spill Latency                : {self.spill_data['tick_diff'].std():>12,.0f} ticks

🔥 SPILL HOTSPOTS (Top Program Counters):
{'─'*50}
"""
            # Top spill PCs
            store_pc_counts = self.spill_data['store_pc'].value_counts().head(10)
            for i, (pc, count) in enumerate(store_pc_counts.items(), 1):
                stats_content += f"   #{i:>2} | Store PC {pc}: {count:>6} spill events\n"
        
        stats_content += f"""
{'='*80}
📊 ANALYSIS COMPLETE - Dashboard Generated at {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*80}
"""
        
        text_widget.insert(tk.END, stats_content)
        text_widget.config(state=tk.DISABLED)  # Make read-only
    
    def create_spill_analysis_tab(self, notebook):
        """
        Create spill-specific analysis tab with advanced visualizations
        """
        spill_frame = ttk.Frame(notebook)
        notebook.add(spill_frame, text="🎯 Spill Analysis")
        
        if self.spill_data is None or len(self.spill_data) == 0:
            # No spill data available
            label = tk.Label(spill_frame, text="❌ No spill data available for analysis", 
                           font=('Arial', 16), fg='red')
            label.pack(expand=True)
            return
        
        # Create matplotlib figure for spill analysis
        fig = Figure(figsize=(14, 10), facecolor='white')
        
        # 1. Spill latency histogram
        ax1 = fig.add_subplot(2, 2, 1)
        ax1.hist(self.spill_data['tick_diff'], bins=30, color='skyblue', alpha=0.7, edgecolor='black')
        ax1.set_title('⏰ Spill Latency Distribution', fontweight='bold')
        ax1.set_xlabel('Latency (ticks)')
        ax1.set_ylabel('Frequency')
        ax1.grid(True, alpha=0.3)
        
        # 2. Top spill hotspots
        ax2 = fig.add_subplot(2, 2, 2)
        top_store_pcs = self.spill_data['store_pc'].value_counts().head(8)
        bars = ax2.bar(range(len(top_store_pcs)), top_store_pcs.values, color='coral')
        ax2.set_title('🔥 Top Spill Hotspots (Store PCs)', fontweight='bold')
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
        ax3 = fig.add_subplot(2, 2, 3)
        mem_addr_counts = self.spill_data['memory_address'].value_counts().head(10)
        ax3.bar(range(len(mem_addr_counts)), mem_addr_counts.values, color='lightgreen')
        ax3.set_title('💾 Top Spill Memory Addresses', fontweight='bold')
        ax3.set_xlabel('Memory Address (Top 10)')
        ax3.set_ylabel('Spill Count')
        ax3.set_xticks(range(len(mem_addr_counts)))
        ax3.set_xticklabels([f'{addr[:8]}...' for addr in mem_addr_counts.index], rotation=45)
        
        # 4. Spill timeline
        ax4 = fig.add_subplot(2, 2, 4)
        # Sample data for timeline (every 100th spill to avoid overcrowding)
        sample_spills = self.spill_data.iloc[::max(1, len(self.spill_data)//100)]
        ax4.scatter(sample_spills['load_tick'], sample_spills['tick_diff'], 
                   alpha=0.6, s=30, color='purple')
        ax4.set_title('📈 Spill Timeline Analysis', fontweight='bold')
        ax4.set_xlabel('Simulation Time (ticks)')
        ax4.set_ylabel('Spill Latency (ticks)')
        ax4.grid(True, alpha=0.3)
        
        fig.tight_layout()
        
        # Embed in tkinter
        canvas = FigureCanvasTkAgg(fig, spill_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def create_raw_data_tab(self, notebook):
        """
        Create raw data viewer tab
        """
        raw_frame = ttk.Frame(notebook)
        notebook.add(raw_frame, text="📄 Raw Data")
        
        # Create notebook for raw data subtabs
        raw_notebook = ttk.Notebook(raw_frame)
        raw_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Spill data table
        if self.spill_data is not None and len(self.spill_data) > 0:
            spill_table_frame = ttk.Frame(raw_notebook)
            raw_notebook.add(spill_table_frame, text="🎯 Spill Events")
            
            spill_text = scrolledtext.ScrolledText(spill_table_frame, wrap=tk.NONE, font=('Courier', 9))
            spill_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Format spill data as table
            spill_content = "SPILL EVENT DATA (from cpp_spill_log.txt)\n"
            spill_content += "="*120 + "\n"
            spill_content += f"{'Index':<6} {'Store PC':<12} {'Load PC':<12} {'Memory Addr':<14} {'Store Tick':<12} {'Load Tick':<12} {'Latency':<10} {'Store Inst':<10} {'Load Inst':<10}\n"
            spill_content += "-"*120 + "\n"
            
            for idx, row in self.spill_data.head(500).iterrows():  # Show first 500 entries
                spill_content += f"{idx:<6} {row['store_pc']:<12} {row['load_pc']:<12} {row['memory_address']:<14} {row['store_tick']:<12} {row['load_tick']:<12} {row['tick_diff']:<10} {row['store_inst_count']:<10} {row['load_inst_count']:<10}\n"
            
            if len(self.spill_data) > 500:
                spill_content += f"\n... and {len(self.spill_data) - 500} more entries\n"
            
            spill_text.insert(tk.END, spill_content)
            spill_text.config(state=tk.DISABLED)
        
        # gem5 stats table
        stats_table_frame = ttk.Frame(raw_notebook)
        raw_notebook.add(stats_table_frame, text="📊 gem5 Stats")
        
        stats_text = scrolledtext.ScrolledText(stats_table_frame, wrap=tk.NONE, font=('Courier', 9))
        stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        stats_content = f"GEM5 STATISTICS (from {self.stats_file})\n"
        stats_content += "="*80 + "\n"
        stats_content += f"{'Statistic Name':<50} {'Value':<20} {'Type':<10}\n"
        stats_content += "-"*80 + "\n"
        
        for stat_name, stat_value in sorted(self.gem5_stats.items()):
            value_type = type(stat_value).__name__
            stats_content += f"{stat_name:<50} {str(stat_value):<20} {value_type:<10}\n"
        
        stats_text.insert(tk.END, stats_content)
        stats_text.config(state=tk.DISABLED)
    
    def run(self):
        """
        Launch the dashboard GUI
        """
        self.create_dashboard()
        self.root.mainloop()

def main():
    """
    Main function to create and run the spill analysis dashboard
    """
    print("🚀 Starting Register Spill Analysis Dashboard...")
    print("📂 Looking for gem5 output files in 'm5out' directory...")
    
    # Create dashboard instance
    dashboard = SpillAnalysisDashboard("m5out")
    
    # Launch GUI
    dashboard.run()

if __name__ == "__main__":
    main()
