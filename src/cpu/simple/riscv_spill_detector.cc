/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * RISC-V-Specific Register Spill Detection System Implementation
 * 
 * =====================================================================
 * RISC-V ARCHITECTURE-SPECIFIC SPILL DETECTION IMPLEMENTATION:
 * =====================================================================
 * 
 * This implementation is specifically tailored for RISC-V architecture
 * characteristics:
 * 
 * 1. RISC-V Register Set: 32 general-purpose 64-bit registers
 *    - x0 (zero): Always zero, cannot be written
 *    - x1 (ra): Return address register
 *    - x2 (sp): Stack pointer
 *    - x3 (gp): Global pointer
 *    - x4 (tp): Thread pointer
 *    - x5-x7, x28-x31 (t0-t6): Temporary registers
 *    - x8-x9, x18-x27 (s0-s11): Saved registers
 *    - x10-x17 (a0-a7): Argument/return registers
 * 
 * 2. RISC-V Memory Addressing: Simple addressing mode
 *    - Base + Immediate: rs1 + immediate (12-bit signed)
 *    - No complex addressing modes like X86
 *    - Load/Store instructions: LW, SW, LD, SD
 * 
 * 3. RISC-V Calling Convention:
 *    - Argument registers: a0-a7 (x10-x17)
 *    - Return registers: a0-a1 (x10-x11)
 *    - Callee-saved: s0-s11 (x8-x9, x18-x27), sp (x2)
 *    - Caller-saved: t0-t6 (x5-x7, x28-x31), a0-a7 (x10-x17)
 * 
 * 4. RISC-V Instruction Characteristics:
 *    - Fixed 32-bit instruction length
 *    - RISC design with simple operations
 *    - Load-store architecture (no memory-memory ops)
 *    - Explicit register usage in all instructions
 * 
 * =====================================================================
 * RISC-V SPILL DETECTION DEVELOPMENT WORKFLOW:
 * =====================================================================
 * 
 * CURRENT PROJECT STATUS (September 2025):
 * ========================================
 * 
 * 1. Architecture-Specific Implementation Approach:
 *    - Created separate implementations: x86_spill_detector.cc, riscv_spill_detector.cc
 *    - Common interface: spill_detector.hh (architecture-agnostic)
 *    - Polymorphic design for fair cross-architecture comparison
 * 
 * 2. RISC-V-Specific Optimizations:
 *    - 32-register awareness vs X86's 16 registers
 *    - RISC load-store architecture considerations
 *    - Fixed 32-bit instruction patterns
 *    - Simple addressing mode analysis (base + immediate)
 * 
 * 3. Enhanced Detection Parameters:
 *    - MIN_SPILL_WINDOW: 1000 ticks (more sensitive than previous 100K)
 *    - MAX_SPILL_WINDOW: 500K ticks (optimized for RISC-V patterns)
 *    - Architecture-aware thresholds for realistic spill detection
 * 
 * 4. Fair Comparison Test Suite:
 *    - Unified test program: unified_spill_test.c
 *    - Architecture-agnostic C code with #ifdef for syscalls
 *    - Identical compilation: -O0 for both X86 and RISC-V
 *    - 25 variables, 150 iterations for register pressure
 * 
 * 5. RISC-V Build Process:
 *    $ scons build/RISCV/gem5.opt -j$(sysctl -n hw.ncpu)
 *    $ riscv64-elf-gcc -O0 -nostdlib -nostartfiles -static \
 *      -o unified_riscv_static unified_spill_test.c
 * 
 * 6. RISC-V Testing Workflow:
 *    $ ./build/RISCV/gem5.opt configs/deprecated/example/se.py \
 *      --cmd=fair_comparison_test/riscv_build/unified_riscv_static
 *    # Expected: Architecture-specific spill patterns
 * 
 * 7. Cross-Architecture Analysis:
 *    - Compare X86 vs RISC-V spill counts
 *    - Analyze instruction set efficiency
 *    - Evaluate register utilization patterns
 *    - Generate comparative reports
 * 
 * RISC-V INSTRUCTION SET COVERAGE:
 * ===============================
 * Load Instructions: LB, LH, LW, LD, LBU, LHU, LWU
 * Store Instructions: SB, SH, SW, SD
 * Addressing: rs1 + imm12 (simple base + offset)
 * Register Naming: x0-x31 (ABI names: zero, ra, sp, gp, tp, t0-t6, s0-s11, a0-a7)
 * 
 * IMPLEMENTATION FEATURES:
 * =======================
 * ✅ RISC-V instruction validation (size-based)
 * ✅ Architecture-specific logging messages
 * ✅ 32-register awareness in comments
 * ✅ RISC-V calling convention documentation
 * ✅ Load-store architecture considerations
 * ✅ Fixed 32-bit instruction handling
 * ✅ Enhanced CSV headers with RISC-V metadata
 * =====================================
 * FINAL EXECUTION RESULTS (ACHIEVED):
 * =====================================
 * TODO - Update after final test runs
 * ============================================================
 * 
 */

#include "cpu/simple/spill_detector.hh"
#include "base/trace.hh"
#include "debug/SpillDetector.hh"
#include <iostream>
#include <iomanip>
#include <set>
#include <cmath>
#include <map>
#include <string>
#include <map>
#include <algorithm>
#include <fstream>

/*
 * This file implements a simple register spill detection system.
 * It tracks memory accesses and identifies potential spill patterns
 * based on the observed load/store behavior.
 * 
 * This is where the real-time register spill detection happens.
 * It is part of the gem5 simulator’s core code (not the test program or Python).
 * It tracks every store and load instruction during simulation, using a C++ map to find store-load patterns that indicate register spills.
 * When a spill is detected, it logs the event (e.g., to cpp_spill_log.txt).
 * 
 * === Important Notes ===
 * 
 * ! The CPU model (timing.cc) calls the spill detector every time a store or load instruction is executed, for every instruction in your program.
 * 
 * ! The spill detector keeps track of which memory addresses were recently written to (store) and then checks if a later load accesses the same address.
 * 
 * ! If a store is followed by a load to the same address (within a certain window), it is counted as a potential register spill.
 * 
 * --------------------------
 * 
 * The load does not have to come immediately after the store. The spill detector keeps track of recent stores, and if a load to the same address happens later—even after several other instructions—it can still detect the spill.
 * 
 * This is why the detector uses a map (like a table) to remember all recent store addresses. When a load happens, it checks if there was a store to that address earlier (within a reasonable window). If so, it counts as a potential register spill, even if other instructions happened in between.
 */

namespace gem5
{

SpillDetector::SpillDetector()
    : total_instructions(0), total_stores(0), total_loads(0), total_spills_detected(0), total_spills_logged(0)
{
    // Reserve space for performance
    store_map.reserve(1000);
    detected_spills.reserve(100);
    
    // Write header to log file (only once at the beginning)
    writeLogHeader();
    
    // RISC-V Architecture-Specific Initialization
    std::cout << "[RISC-V SpillDetector] Initializing RISC-V-specific register spill detection..." << std::endl;
    std::cout << "[RISC-V SpillDetector] Architecture: RISC-V 64-bit with 32 general-purpose registers" << std::endl;
    std::cout << "[RISC-V SpillDetector] Instruction Set: RV64I base with fixed 32-bit instructions" << std::endl;
    std::cout << "[RISC-V SpillDetector] Memory Model: Load-store architecture with simple addressing" << std::endl;
    std::cout << "[RISC-V SpillDetector] Detection thresholds optimized for RISC-V register usage patterns" << std::endl;
}

SpillDetector::~SpillDetector()
{
    // Print final statistics when detector is destroyed  
    printSpillReport();
    
    // Clean shutdown
    std::cout << "[RISC-V Spill Detector] Detection complete - statistics logged" << std::endl;
}

void
SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size)
{
    total_stores++;
    
    // RISC-V-specific instruction validation
    // RISC-V store instructions: SB, SH, SW, SD (8, 16, 32, 64-bit)
    bool valid_riscv_store = false;
    std::string store_type = "UNKNOWN";
    
    switch(size) {
        case 1: store_type = "SB (Store Byte)"; valid_riscv_store = true; break;
        case 2: store_type = "SH (Store Halfword)"; valid_riscv_store = true; break;
        case 4: store_type = "SW (Store Word)"; valid_riscv_store = true; break;
        case 8: store_type = "SD (Store Doubleword)"; valid_riscv_store = true; break;
        default: 
            std::cout << "[RISC-V SpillDetector] WARNING: Invalid RISC-V store size: " << size 
                      << " bytes at PC=0x" << std::hex << pc << std::dec << std::endl;
    }
    
    if (valid_riscv_store && (total_stores % 1000 == 0)) {
        std::cout << "[RISC-V SpillDetector] Store #" << total_stores 
                  << " - Type: " << store_type 
                  << " | Address: 0x" << std::hex << address 
                  << " | PC: 0x" << pc << std::dec << std::endl;
    }
    
    // Create store info and add to our C++ map
    // This is the core map functionality requested by the user
    StoreInfo store_info(address, pc, tick, size, total_instructions);
    store_map[address] = store_info;
    
    // Clean up old entries to prevent memory bloat
    if (store_map.size() > MAX_STORE_ENTRIES) {
        cleanupOldStores(tick);
    }
}

void
SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size)
{
    total_loads++;
    
    // Check if we have a recent store to this address
    // This is where we use the C++ map to detect spill patterns
    auto store_it = store_map.find(address); // 🔍 SEARCHING: Does store contained by this address?

    if (store_it != store_map.end()) {  // ✅ FOUND!
        const StoreInfo& store_info = store_it->second;
        
        // Check if this looks like a register spill
        if (isLikelySpill(store_info, pc, tick)) {
            // 🎯 RISC-V SPILL DETECTED!! Store followed by load to same address
            total_spills_detected++;
            
            SpillEvent spill(store_info.pc, pc, address, store_info.tick, tick,
                           store_info.instruction_count, total_instructions);
            detected_spills.push_back(spill);
            
            // RISC-V-specific spill logging
            std::cout << "[RISC-V SpillDetector] SPILL #" << total_spills_detected 
                      << " | Size: " << size << " bytes"
                      << " | Address: 0x" << std::hex << address 
                      << " | Store PC: 0x" << store_info.pc 
                      << " | Load PC: 0x" << pc << std::dec
                      << " | Ticks: " << (tick - store_info.tick) << std::endl;
            
            // Log to file for detailed analysis
            writeSpillToLog(spill);
            
            // Remove the store entry since we've matched it
            // (Prevents double-counting same spill pattern)
            store_map.erase(store_it);
        }
    }
}

void
SpillDetector::onInstructionExecute(Addr pc, Tick tick)
{
    total_instructions++;
    // No progress reporting - clean execution until final report
}


/*
* Store ve load işlemleri arasında geçen zaman (tick farkı) makul bir aralıkta mı? (Çok kısa veya çok uzun olmamalı.)
* Store ve load aynı instruction (aynı PC) tarafından mı yapıldı? Eğer öyleyse bu bir spill değildir.
* Zaman aralığı sıfır veya negatifse, ya da çok büyükse spill değildir.
*/
bool
SpillDetector::isLikelySpill(const StoreInfo& store_info, Addr load_pc, Tick load_tick)
{
    Tick time_diff = load_tick - store_info.tick;
    
    // Basic sanity check: Load must come after store
    if (time_diff <= 0) { // ❌ Load store'dan önce gelmiş || LOAD -❌-> STORE
        return false;
    }
    
    // Different instructions check: If store and load are the same instruction, it's not a spill
    if (store_info.pc == load_pc) {
        return false;
    }
    
    // Multi-factor loop vs spill detection algorithm
    // Same sophisticated detection logic as X86
    
    // Factor 1: PC distance analysis for RISC-V (fixed 4-byte instructions)
    // RISC-V loops typically have very tight instruction distances (4-8 bytes)
    Addr pc_distance = (load_pc > store_info.pc) ? 
                       (load_pc - store_info.pc) : 
                       (store_info.pc - load_pc);
    bool likely_loop_pc = (pc_distance <= 8); // RISC-V loop threshold (2 instructions)
    
    // Factor 2: Timing consistency - loops have very consistent timing
    // Check if this store-load pair has been seen with similar timing before
    std::string pc_pair = std::to_string(store_info.pc) + "->" + std::to_string(load_pc);
    auto timing_it = pc_timing_patterns.find(pc_pair);
    bool likely_loop_timing = false;
    
    if (timing_it != pc_timing_patterns.end()) {
        // Calculate coefficient of variation for timing
        double avg_time = timing_it->second.total_time / timing_it->second.count;
        double variance = (timing_it->second.sum_squares / timing_it->second.count) - (avg_time * avg_time);
        double cv = (avg_time > 0) ? (sqrt(variance) / avg_time) : 0.0;
        
        // Loops have very consistent timing (CV < 5%)
        likely_loop_timing = (cv < 0.05 && timing_it->second.count > 10);
    }
    
    // Update timing statistics
    if (timing_it == pc_timing_patterns.end()) {
        pc_timing_patterns[pc_pair] = {time_diff, time_diff * time_diff, 1};
    } else {
        timing_it->second.total_time += time_diff;
        timing_it->second.sum_squares += (time_diff * time_diff);
        timing_it->second.count++;
    }
    
    // Factor 3: Repetition count - loops execute hundreds/thousands of times
    auto rep_it = pc_repetition_count.find(pc_pair);
    bool likely_loop_repetition = false;
    
    if (rep_it == pc_repetition_count.end()) {
        pc_repetition_count[pc_pair] = 1;
    } else {
        rep_it->second++;
        likely_loop_repetition = (rep_it->second > 500); // High repetition = likely loop
    }
    
    // Factor 4: Frequency analysis - loops execute very frequently
    // Spills are typically less frequent than loop counters
    bool likely_loop_frequency = (time_diff < 500); // Very frequent = likely loop
    
    // Final decision: If multiple factors indicate loop behavior, it's not a spill
    bool likely_loop = (likely_loop_pc && likely_loop_timing) || 
                       (likely_loop_pc && likely_loop_repetition) ||
                       (likely_loop_timing && likely_loop_frequency);
    
    return !likely_loop; // If it's likely a loop, it's NOT a spill
}

void
SpillDetector::cleanupOldStores(Tick current_tick)
{
    auto it = store_map.begin();
    while (it != store_map.end()) {
        if (current_tick - it->second.tick > MAX_SPILL_WINDOW) {
            it = store_map.erase(it);
        } else {
            ++it;
        }
    }
}

void
SpillDetector::writeLogHeader()
{
    // Write header to log file (create new file, overwrite if exists)
    std::ofstream log_file("m5out/spill_stats.txt", std::ios::trunc);
    if (log_file.is_open()) {
        log_file << "# RISC-V Register Spill Detection Log\n";
        log_file << "# Generated by gem5 RISC-V SpillDetector\n";
        log_file << "# ====================================\n";
        log_file << "#\n";
        log_file << "# Architecture: RISC-V 64-bit (RV64I)\n";
        log_file << "# Register Set: 32 general-purpose registers (x0-x31)\n";
        log_file << "# Instruction Set: Fixed 32-bit instructions\n";
        log_file << "# Memory Model: Load-store architecture\n";
        log_file << "# Load Instructions: LB, LH, LW, LD, LBU, LHU, LWU\n";
        log_file << "# Store Instructions: SB, SH, SW, SD\n";
        log_file << "#\n";
        log_file << "# Format: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count\n";
        log_file << "#\n";
        log_file << "# Field Descriptions:\n";
        log_file << "#   store_pc        : Program Counter (hexadecimal) of the store instruction that spilled data to memory\n";
        log_file << "#   load_pc         : Program Counter (hexadecimal) of the load instruction that retrieved the spilled data\n";
        log_file << "#   memory_address  : Memory address (hexadecimal) where the spill occurred\n";
        log_file << "#   store_tick      : Simulation time (decimal) when the store operation happened\n";
        log_file << "#   load_tick       : Simulation time (decimal) when the load operation happened\n";
        log_file << "#   tick_diff       : Time difference (decimal) between store and load operations\n";
        log_file << "#   store_inst_count: Global instruction counter when store occurred\n";
        log_file << "#   load_inst_count : Global instruction counter when load occurred\n";
        log_file << "#\n";
        log_file << "# Each line represents one detected register spill event\n";
        log_file << "# =================================\n";
        log_file << "\n";
        log_file.close();
    }
}

void
SpillDetector::writeSpillToLog(const SpillEvent& spill)
{
    // Append to detailed log file
    static std::ofstream log_file("m5out/spill_stats.txt", std::ios::app);
    if (log_file.is_open()) {
        log_file << "SPILL," 
                 << std::hex << spill.store_pc << ","
                 << std::hex << spill.load_pc << ","
                 << std::hex << spill.address << ","
                 << std::dec << spill.store_tick << ","
                 << spill.load_tick << ","
                 << spill.tick_diff << ","
                 << spill.store_inst_count << ","
                 << spill.load_inst_count << std::endl;
        
        total_spills_logged++; // Increment counter when actually written to log
    }
}

void 
SpillDetector::printSpillReport() const
{
    // Console output
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << "🔍 C++ REGISTER SPILL DETECTION REPORT" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    
    std::cout << "\n📊 EXECUTION STATISTICS:" << std::endl;
    std::cout << "  Total Instructions: " << total_instructions << std::endl;
    std::cout << "  Store Instructions: " << total_stores << std::endl;
    std::cout << "  Load Instructions: " << total_loads << std::endl;
    std::cout << "  Total Memory Operations: " << (total_stores + total_loads) << std::endl;
    std::cout << "  Total Spills Detected: " << detected_spills.size() << " (vector) | " << total_spills_logged << " (logged to file)" << std::endl;
    
    std::cout << "\n📈 A. TEMEL ORANLAR:" << std::endl;
    
    uint64_t total_memory_ops = total_stores + total_loads;
    
    // Spill Rate (Memory Op bazında)
    if (total_memory_ops > 0) {
        double spill_rate_memory = (double(detected_spills.size()) / total_memory_ops) * 100.0;
        std::cout << "  ✅ Spill Rate (Memory Op bazında): " << std::fixed << std::setprecision(3) 
                  << spill_rate_memory << "%" << std::endl;
    }
    
    // Spill Rate (Instruction bazında)
    if (total_instructions > 0) {
        double spill_rate_instructions = (double(detected_spills.size()) / total_instructions) * 100.0;
        std::cout << "  ✅ Spill Rate (Instruction bazında): " << std::fixed << std::setprecision(3) 
                  << spill_rate_instructions << "%" << std::endl;
    }
    
    // Memory Intensity
    if (total_instructions > 0) {
        double memory_intensity = (double(total_memory_ops) / total_instructions) * 100.0;
        std::cout << "  ✅ Memory Intensity: " << std::fixed << std::setprecision(2) 
                  << memory_intensity << "% of instructions" << std::endl;
    }
    
    // Store/Load Ratio
    if (total_loads > 0) {
        double store_load_ratio = double(total_stores) / total_loads;
        std::cout << "  ✅ Store/Load Ratio: " << std::fixed << std::setprecision(3) 
                  << store_load_ratio << std::endl;
    }
    
    std::cout << "\n🚀 B. PERFORMANCE IMPACT:" << std::endl;
    
    // Average Spill Latency
    if (!detected_spills.empty()) {
        Tick total_latency = 0;
        for (const auto& spill : detected_spills) {
            total_latency += spill.tick_diff;
        }
        double avg_latency = double(total_latency) / detected_spills.size();
        std::cout << "  ✅ Average Spill Latency: " << std::fixed << std::setprecision(1) 
                  << avg_latency << " ticks" << std::endl;
    }
    
    // Spill Frequency (spills per instruction)
    if (total_instructions > 0) {
        double spill_frequency = double(detected_spills.size()) / total_instructions;
        std::cout << "  ✅ Spill Frequency: " << std::scientific << std::setprecision(3)
                  << spill_frequency << " spills/instruction" << std::endl;
    }
    
    // Memory Pressure (active pending stores)
    std::cout << "  ✅ Memory Pressure: " << store_map.size() 
              << " active pending stores" << std::endl;
    
    std::cout << "\n🔥 HOTSPOT ANALYSIS:" << std::endl;
    
    // Find most frequent store PCs
    std::map<Addr, uint64_t> store_pc_count;
    for (const auto& spill : detected_spills) {
        store_pc_count[spill.store_pc]++;
    }
    
    if (store_pc_count.empty()) {
        std::cout << "  No store hotspots detected." << std::endl;
    } else {
        // Convert to vector for sorting
        std::vector<std::pair<Addr, uint64_t>> sorted_stores;
        for (const auto& entry : store_pc_count) {
            sorted_stores.push_back({entry.first, entry.second});
        }
        
        // Sort by frequency (descending)
        std::sort(sorted_stores.begin(), sorted_stores.end(),
                  [](const auto& a, const auto& b) { return a.second > b.second; });
        
        std::cout << "  Top Spill-causing Store PCs:" << std::endl;
        for (size_t i = 0; i < std::min(sorted_stores.size(), size_t(5)); i++) {
            std::cout << "    " << (i+1) << ". PC 0x" << std::hex << sorted_stores[i].first 
                      << ": " << std::dec << sorted_stores[i].second << " spills" << std::endl;
        }
    }
    
    // Memory regions
    std::set<Addr> memory_regions;
    for (const auto& spill : detected_spills) {
        memory_regions.insert(spill.address);
    }
    
    std::cout << "\n💾 MEMORY REGIONS:" << std::endl;
    std::cout << "  Unique spill memory addresses: " << memory_regions.size() << std::endl;
    
    std::cout << std::string(60, '=') << std::endl;
}

void
SpillDetector::reset()
{
    store_map.clear();
    detected_spills.clear();
    total_instructions = 0;
    total_stores = 0;
    total_loads = 0;
    total_spills_detected = 0;
    total_spills_logged = 0;
}

} // namespace gem5
