#!/bin/bash

# =============================================================================
# SPILL DETECTION ANALYZER
# =============================================================================
# This script analyzes the output of spill detection simulations and generates
# detailed reports and visualizations.
#
# Usage:
#   ./analyze_spill_results.sh [spill_stats_file]
#
# If no file is specified, it will look for m5out/x86_spill_stats.txt
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SPILL_FILE=${1:-"m5out/x86_spill_stats.txt"}
OUTPUT_DIR="spill_analysis_results"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "${CYAN}$1${NC}"
}

# =============================================================================
# VERIFICATION
# =============================================================================
log_info "Spill Detection Results Analyzer"
log_info "================================="

if [ ! -f "$SPILL_FILE" ]; then
    log_error "Spill file not found: $SPILL_FILE"
    log_info "Please run a simulation first or specify the correct file path"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# =============================================================================
# BASIC STATISTICS
# =============================================================================
log_header "📊 BASIC SPILL STATISTICS"
echo "=========================="

# Count total spills
TOTAL_SPILLS=$(grep "^SPILL" "$SPILL_FILE" | wc -l)
echo "Total spills detected: $TOTAL_SPILLS"

if [ $TOTAL_SPILLS -eq 0 ]; then
    log_warning "No spills detected in the file"
    exit 0
fi

# Unique counts
UNIQUE_STORE_PCS=$(grep "^SPILL" "$SPILL_FILE" | cut -d',' -f2 | sort -u | wc -l)
UNIQUE_LOAD_PCS=$(grep "^SPILL" "$SPILL_FILE" | cut -d',' -f3 | sort -u | wc -l)
UNIQUE_ADDRESSES=$(grep "^SPILL" "$SPILL_FILE" | cut -d',' -f4 | sort -u | wc -l)

echo "Unique store PCs: $UNIQUE_STORE_PCS"
echo "Unique load PCs: $UNIQUE_LOAD_PCS"
echo "Unique memory addresses: $UNIQUE_ADDRESSES"
echo ""

# =============================================================================
# TIMING ANALYSIS
# =============================================================================
log_header "⏱️  TIMING ANALYSIS"
echo "==================="

# Extract timing information
grep "^SPILL" "$SPILL_FILE" | cut -d',' -f7 | sort -n > "$OUTPUT_DIR/tick_diffs.tmp"

if [ -s "$OUTPUT_DIR/tick_diffs.tmp" ]; then
    MIN_LATENCY=$(head -1 "$OUTPUT_DIR/tick_diffs.tmp")
    MAX_LATENCY=$(tail -1 "$OUTPUT_DIR/tick_diffs.tmp")
    
    # Calculate average (simple method)
    TOTAL_LATENCY=$(awk '{sum += $1} END {print sum}' "$OUTPUT_DIR/tick_diffs.tmp")
    AVG_LATENCY=$((TOTAL_LATENCY / TOTAL_SPILLS))
    
    echo "Spill latency (ticks):"
    echo "  Minimum: $MIN_LATENCY"
    echo "  Maximum: $MAX_LATENCY"
    echo "  Average: $AVG_LATENCY"
    
    # Latency distribution
    echo ""
    echo "Latency distribution:"
    echo "  < 100 ticks: $(awk '$1 < 100' "$OUTPUT_DIR/tick_diffs.tmp" | wc -l)"
    echo "  100-1000 ticks: $(awk '$1 >= 100 && $1 < 1000' "$OUTPUT_DIR/tick_diffs.tmp" | wc -l)"
    echo "  1000-10000 ticks: $(awk '$1 >= 1000 && $1 < 10000' "$OUTPUT_DIR/tick_diffs.tmp" | wc -l)"
    echo "  > 10000 ticks: $(awk '$1 >= 10000' "$OUTPUT_DIR/tick_diffs.tmp" | wc -l)"
fi
echo ""

# =============================================================================
# HOTSPOT ANALYSIS
# =============================================================================
log_header "🔥 HOTSPOT ANALYSIS"
echo "==================="

# Store PC hotspots
echo "Top 10 Store PCs (most frequent spill sources):"
grep "^SPILL" "$SPILL_FILE" | cut -d',' -f2 | sort | uniq -c | sort -nr | head -10 | \
while read count pc; do
    printf "  0x%-12s: %3d spills\n" "$pc" "$count"
done > "$OUTPUT_DIR/store_hotspots.txt"
cat "$OUTPUT_DIR/store_hotspots.txt"

echo ""

# Load PC hotspots
echo "Top 10 Load PCs (most frequent spill destinations):"
grep "^SPILL" "$SPILL_FILE" | cut -d',' -f3 | sort | uniq -c | sort -nr | head -10 | \
while read count pc; do
    printf "  0x%-12s: %3d spills\n" "$pc" "$count"
done > "$OUTPUT_DIR/load_hotspots.txt"
cat "$OUTPUT_DIR/load_hotspots.txt"

echo ""

# Memory address hotspots
echo "Top 10 Memory Addresses (most frequently spilled locations):"
grep "^SPILL" "$SPILL_FILE" | cut -d',' -f4 | sort | uniq -c | sort -nr | head -10 | \
while read count addr; do
    printf "  0x%-12s: %3d spills\n" "$addr" "$count"
done > "$OUTPUT_DIR/memory_hotspots.txt"
cat "$OUTPUT_DIR/memory_hotspots.txt"

echo ""

# =============================================================================
# TEMPORAL ANALYSIS
# =============================================================================
log_header "⏰ TEMPORAL ANALYSIS"
echo "===================="

# Spill distribution over time
echo "Spill distribution over simulation time:"
grep "^SPILL" "$SPILL_FILE" | cut -d',' -f5 | sort -n > "$OUTPUT_DIR/spill_times.tmp"

FIRST_SPILL=$(head -1 "$OUTPUT_DIR/spill_times.tmp")
LAST_SPILL=$(tail -1 "$OUTPUT_DIR/spill_times.tmp")
SIMULATION_DURATION=$((LAST_SPILL - FIRST_SPILL))

echo "  First spill at tick: $FIRST_SPILL"
echo "  Last spill at tick: $LAST_SPILL"
echo "  Spill period duration: $SIMULATION_DURATION ticks"

if [ $SIMULATION_DURATION -gt 0 ]; then
    SPILL_RATE=$((TOTAL_SPILLS * 1000000 / SIMULATION_DURATION))
    echo "  Average spill rate: $SPILL_RATE spills per million ticks"
fi

echo ""

# =============================================================================
# INSTRUCTION ANALYSIS
# =============================================================================
log_header "📝 INSTRUCTION ANALYSIS"
echo "======================="

# Instruction counts
grep "^SPILL" "$SPILL_FILE" | cut -d',' -f8,9 > "$OUTPUT_DIR/instruction_counts.tmp"

if [ -s "$OUTPUT_DIR/instruction_counts.tmp" ]; then
    FIRST_STORE_INST=$(cut -d',' -f1 "$OUTPUT_DIR/instruction_counts.tmp" | sort -n | head -1)
    LAST_LOAD_INST=$(cut -d',' -f2 "$OUTPUT_DIR/instruction_counts.tmp" | sort -n | tail -1)
    TOTAL_INSTRUCTIONS=$((LAST_LOAD_INST - FIRST_STORE_INST))
    
    echo "Instruction range:"
    echo "  First store instruction: $FIRST_STORE_INST"
    echo "  Last load instruction: $LAST_LOAD_INST"
    echo "  Total instruction span: $TOTAL_INSTRUCTIONS"
    
    if [ $TOTAL_INSTRUCTIONS -gt 0 ]; then
        SPILL_DENSITY=$((TOTAL_SPILLS * 100 / TOTAL_INSTRUCTIONS))
        echo "  Spill density: $SPILL_DENSITY spills per 100 instructions"
    fi
fi

echo ""

# =============================================================================
# PATTERN ANALYSIS
# =============================================================================
log_header "🔍 PATTERN ANALYSIS"
echo "==================="

# Store-Load patterns
echo "Store-Load pair analysis:"
grep "^SPILL" "$SPILL_FILE" | awk -F',' '{print $2 "," $3}' | sort | uniq -c | sort -nr > "$OUTPUT_DIR/store_load_pairs.tmp"

UNIQUE_PATTERNS=$(wc -l < "$OUTPUT_DIR/store_load_pairs.tmp")
REPEATED_PATTERNS=$(awk '$1 > 1' "$OUTPUT_DIR/store_load_pairs.tmp" | wc -l)

echo "  Unique store-load patterns: $UNIQUE_PATTERNS"
echo "  Repeated patterns: $REPEATED_PATTERNS"

if [ $REPEATED_PATTERNS -gt 0 ]; then
    echo ""
    echo "Top 5 repeated store-load patterns:"
    head -5 "$OUTPUT_DIR/store_load_pairs.tmp" | while read count pattern; do
        store_pc=$(echo "$pattern" | cut -d',' -f1)
        load_pc=$(echo "$pattern" | cut -d',' -f2)
        printf "  0x%s -> 0x%s: %d times\n" "$store_pc" "$load_pc" "$count"
    done
fi

echo ""

# =============================================================================
# GENERATE SUMMARY REPORT
# =============================================================================
log_header "📄 GENERATING SUMMARY REPORT"
echo "============================="

REPORT_FILE="$OUTPUT_DIR/spill_analysis_summary.txt"

cat > "$REPORT_FILE" << EOF
SPILL DETECTION ANALYSIS SUMMARY
Generated: $(date)
Source file: $SPILL_FILE

BASIC STATISTICS:
- Total spills detected: $TOTAL_SPILLS
- Unique store PCs: $UNIQUE_STORE_PCS
- Unique load PCs: $UNIQUE_LOAD_PCS
- Unique memory addresses: $UNIQUE_ADDRESSES

TIMING ANALYSIS:
- Minimum latency: $MIN_LATENCY ticks
- Maximum latency: $MAX_LATENCY ticks
- Average latency: $AVG_LATENCY ticks

TEMPORAL ANALYSIS:
- First spill: $FIRST_SPILL ticks
- Last spill: $LAST_SPILL ticks
- Simulation duration: $SIMULATION_DURATION ticks
- Average spill rate: $SPILL_RATE spills per million ticks

PATTERN ANALYSIS:
- Unique store-load patterns: $UNIQUE_PATTERNS
- Repeated patterns: $REPEATED_PATTERNS

GENERATED FILES:
- Store hotspots: $OUTPUT_DIR/store_hotspots.txt
- Load hotspots: $OUTPUT_DIR/load_hotspots.txt
- Memory hotspots: $OUTPUT_DIR/memory_hotspots.txt
- Store-load patterns: $OUTPUT_DIR/store_load_pairs.tmp
- Summary report: $REPORT_FILE
EOF

log_success "Analysis complete!"
echo "📁 Results saved to: $OUTPUT_DIR/"
echo "📄 Summary report: $REPORT_FILE"

# Cleanup temporary files
rm -f "$OUTPUT_DIR"/*.tmp

log_info "Analysis finished successfully!"
