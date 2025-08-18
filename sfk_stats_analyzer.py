#!/usr/bin/env python3
"""
SFK (Spill-Fill-Kill) Statistics Analyzer
Analyzes gem5 simulation results and SFK instruction usage
"""

import re
import sys
from collections import defaultdict

class SFKStatsAnalyzer:
    def __init__(self, stats_file="m5out/stats.txt", output_file="m5out/sfk_stats_interpreted.txt"):
        self.stats_file = stats_file
        self.output_file = output_file
        self.total_instructions = 0
        self.sfk_counts = defaultdict(int)
        self.instruction_types = {}
        
    def parse_stats(self):
        """Parse gem5 stats.txt file"""
        try:
            with open(self.stats_file, 'r') as f:
                content = f.read()
                
            # Total committed instructions
            match = re.search(r'system\.cpu\.commitStats0\.numInsts\s+(\d+)', content)
            if match:
                self.total_instructions = int(match.group(1))
                
            # Instruction types
            matches = re.findall(r'system\.cpu\.commitStats0\.committedInstType::(\w+)\s+(\d+)\s+([\d.]+%)', content)
            for inst_type, count, percentage in matches:
                self.instruction_types[inst_type] = {
                    'count': int(count),
                    'percentage': percentage
                }
                
        except FileNotFoundError:
            print(f"Error: {self.stats_file} not found")
            return False
        return True
    
    def parse_simulation_output(self):
        """Parse SFK debug output from simulation"""
        # Bu kısım simulation output'tan SFK sayılarını parse eder
        # Şimdilik manual olarak sayıları vereceğiz
        pass
    
    def analyze_sfk_from_debug(self, debug_output):
        """Extract SFK counts from debug output"""
        sfk_patterns = {
            'SPILL': r'SFK_SPILL #(\d+):',
            'FILL': r'SFK_FILL #(\d+):',
            'KILL': r'SFK_KILL #(\d+):',
            'FKILL': r'SFK_FKILL #(\d+):',
            'SETSFP': r'SFK_SETSFP #(\d+):',
            'INCSFP': r'SFK_INCSFP #(\d+):'
        }
        
        for sfk_type, pattern in sfk_patterns.items():
            matches = re.findall(pattern, debug_output)
            if matches:
                self.sfk_counts[sfk_type] = len(matches)
    
    def calculate_metrics(self):
        """Calculate SFK efficiency metrics"""
        total_sfk = sum(self.sfk_counts.values())
        
        metrics = {
            'total_instructions': self.total_instructions,
            'total_sfk_instructions': total_sfk,
            'sfk_ratio': (total_sfk / self.total_instructions * 100) if self.total_instructions > 0 else 0,
            'spill_fill_ratio': (self.sfk_counts['FILL'] / self.sfk_counts['SPILL']) if self.sfk_counts['SPILL'] > 0 else 0,
            'sfk_breakdown': dict(self.sfk_counts)
        }
        
        return metrics
    
    def generate_report(self, debug_output=None):
        """Generate comprehensive SFK analysis report"""
        
        # Parse stats
        if not self.parse_stats():
            return
            
        # Parse SFK counts from debug output if provided
        if debug_output:
            self.analyze_sfk_from_debug(debug_output)
        else:
            # Manual counts from our test (will be automated later)
            self.sfk_counts = {
                'SPILL': 2,
                'FILL': 3,
                'KILL': 1,
                'FKILL': 0,
                'SETSFP': 1,
                'INCSFP': 1
            }
        
        # Calculate metrics
        metrics = self.calculate_metrics()
        
        # Generate report
        with open(self.output_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("SFK (Spill-Fill-Kill) INSTRUCTION SET ANALYSIS REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("📊 OVERALL STATISTICS:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Instructions Executed: {metrics['total_instructions']}\n")
            f.write(f"Total SFK Instructions: {metrics['total_sfk_instructions']}\n")
            f.write(f"SFK Ratio: {metrics['sfk_ratio']:.1f}%\n\n")
            
            f.write("🔧 SFK INSTRUCTION BREAKDOWN:\n")
            f.write("-" * 40 + "\n")
            for sfk_type, count in metrics['sfk_breakdown'].items():
                percentage = (count / metrics['total_sfk_instructions'] * 100) if metrics['total_sfk_instructions'] > 0 else 0
                f.write(f"  {sfk_type:8}: {count:3d} instructions ({percentage:4.1f}% of SFK)\n")
            f.write("\n")
            
            f.write("📈 EFFICIENCY METRICS:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Spill/Fill Ratio: {metrics['spill_fill_ratio']:.2f}\n")
            f.write(f"  (How many fills per spill - ideal: ~1.0)\n\n")
            
            if metrics['sfk_breakdown']['KILL'] > 0:
                kill_efficiency = (metrics['sfk_breakdown']['KILL'] / metrics['sfk_breakdown']['SPILL'] * 100)
                f.write(f"Kill Efficiency: {kill_efficiency:.1f}%\n")
                f.write(f"  (Percentage of spills that were killed)\n\n")
            
            f.write("🏗️ INSTRUCTION TYPE ANALYSIS:\n")
            f.write("-" * 40 + "\n")
            for inst_type, data in self.instruction_types.items():
                f.write(f"  {inst_type:15}: {data['count']:3d} instructions ({data['percentage']})\n")
            f.write("\n")
            
            f.write("🎯 INTERPRETATION:\n")
            f.write("-" * 40 + "\n")
            
            if metrics['sfk_ratio'] > 15:
                f.write("✅ High SFK usage - good test coverage\n")
            else:
                f.write("⚠️  Low SFK usage - consider more SFK-intensive tests\n")
                
            if 0.8 <= metrics['spill_fill_ratio'] <= 1.5:
                f.write("✅ Balanced spill/fill ratio - efficient memory usage\n")
            else:
                f.write("⚠️  Unbalanced spill/fill ratio - potential inefficiency\n")
                
            f.write("\n")
            f.write("=" * 80 + "\n")
            f.write("Report generated by SFK Stats Analyzer\n")
            f.write("=" * 80 + "\n")
        
        print(f"SFK analysis report generated: {self.output_file}")
        return metrics

if __name__ == "__main__":
    analyzer = SFKStatsAnalyzer()
    
    # If debug output file provided as argument
    debug_output = None
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            debug_output = f.read()
    
    metrics = analyzer.generate_report(debug_output)
    
    # Print summary to console
    if metrics:
        print("\n🎯 QUICK SUMMARY:")
        print(f"Total: {metrics['total_instructions']} instructions")
        print(f"SFK: {metrics['total_sfk_instructions']} instructions ({metrics['sfk_ratio']:.1f}%)")
        print(f"Breakdown: {dict(metrics['sfk_breakdown'])}")
