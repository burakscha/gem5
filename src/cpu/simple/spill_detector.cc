/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * Register Spill Detection System Implementation
 * 
 * ========================================
 * SIMULATION COMMANDS - CURRENT WORKFLOW:
 * ========================================
 * 
 * 1. Build the gem5 simulator with spill detection:
 *    $ cd "/Users/catnys/Documents/Academia/Register Spilling/gem5"
 *    $ scons build/X86/gem5.opt -j8
 * 
 * 2. Run simulation with spill detection enabled:
 *    $ ./build/X86/gem5.opt configs/deprecated/example/se.py -c tests/test-progs/hello/bin/x86/linux/hello --cpu-type=TimingSimpleCPU
 * 
 * 3. View detailed spill report in terminal:
 *    - The report is automatically displayed during simulation execution
 *    - Shows comprehensive statistics every 5000 instructions
 *    - Final report displayed when simulation completes
 * 
 * 4. Generated output files (automatically created in m5out/):
 *    - cpp_spill_log.txt: Detailed CSV log of all detected spills
 *    - spill_advanced_statistics.txt: gem5-style statistics file with comprehensive metrics
 *    - stats.txt: Standard gem5 statistics file
 *    - config.ini: Simulation configuration
 * 
 * 5. View generated files:
 *    $ ls -la m5out/
 *    $ head -20 m5out/cpp_spill_log.txt
 *    $ cat m5out/spill_advanced_statistics.txt
 * 
 * TERMINAL OUTPUT EXAMPLE:
 * The spill report appears directly in the terminal during simulation like this:
 * 
 * ============================================================
 * 🔍 REGISTER SPILL DETECTION REPORT - 5000 Instructions
 * ============================================================
 * 📊 EXECUTION STATISTICS:
 *   Total instructions executed: 5000
 *   Total memory operations: 1034 (stores: 439, loads: 595)
 *   Total spills detected: 143
 * 
 * 🎯 SPILL RATES:
 *   Spill rate (memory ops basis): 13.843%
 *   Spill rate (instruction basis): 2.860%
 *   Memory intensity: 20.68%
 * 
 * ⚡ PERFORMANCE METRICS:
 *   Store/Load ratio: 0.738
 *   Average spill latency: 4,500,000 ticks
 *   Non-spill memory operations: 891 (86.157%)
 * 
 * 🔥 HOTSPOT ANALYSIS (Top 5):
 *   PC 0x409d12: 15 spill events
 *   PC 0x409d1a: 13 spill events
 *   [etc...]
 * 
 * 💾 MEMORY REGIONS:
 *   Unique spill memory addresses: 66
 * ============================================================
 * 
 */

#include "cpu/simple/spill_detector.hh"
#include "base/trace.hh"
#include "debug/SpillDetector.hh"
#include <iostream>
#include <iomanip>
#include <set>
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
    : total_instructions(0), total_stores(0), total_loads(0), total_spills_detected(0)
{
    // Reserve space for performance
    store_map.reserve(1000);
    detected_spills.reserve(100);
    
    // Write header to log file (only once at the beginning)
    writeLogHeader();
    
    std::cout << "🔍 C++ Spill Detector initialized (Approach B)" << std::endl;
}

SpillDetector::~SpillDetector()
{
    printSpillReport();
}

void
SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size)
{
    total_stores++;
    
    // Create store info and add to our C++ map
    // This is the core map functionality requested by the user
    StoreInfo store_info(address, pc, tick, size, total_instructions);
    store_map[address] = store_info;
    
    // Clean up old entries to prevent memory bloat
    if (store_map.size() > MAX_STORE_ENTRIES) {
        cleanupOldStores(tick);
    }
    
    // Debug output for first few stores (so that we could visualize initial behavior)
    if (total_stores <= 3) {  // Reduced debug output
        std::cout << "  📝 Store #" << total_stores 
                  << ": addr=0x" << std::hex << address 
                  << ", pc=0x" << pc
                  << ", tick=" << std::dec << tick << std::endl;
    }
}

void
SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size)
{
    total_loads++;
    
    // Check if we have a recent store to this address
    // This is where we use the C++ map to detect spill patterns
    auto store_it = store_map.find(address);
    
    if (store_it != store_map.end()) {
        const StoreInfo& store_info = store_it->second;
        
        // Check if this looks like a register spill
        if (isLikelySpill(store_info, pc, tick)) {
            // SPILL DETECTED! Store followed by load to same address
            total_spills_detected++;
            
            SpillEvent spill(store_info.pc, pc, address, store_info.tick, tick,
                           store_info.instruction_count, total_instructions);
            detected_spills.push_back(spill);
            
            // Print immediate notification only for first few spills
            if (total_spills_detected <= 5) {
                std::cout << "  🎯 SPILL #" << total_spills_detected 
                          << ": Store@0x" << std::hex << store_info.pc
                          << " → Load@0x" << pc
                          << " (addr=0x" << address
                          << ", Δ" << std::dec << spill.tick_diff << " ticks)" << std::endl;
            }
            
            // Log to file for detailed analysis
            writeSpillToLog(spill);
            
            // Remove the store entry since we've matched it
            // (Prevents double-counting same spill pattern)
            store_map.erase(store_it);
        }
    }
    
    // Debug output for first few loads
    if (total_loads <= 10) {
        std::cout << "  📖 Load #" << total_loads 
                  << ": addr=0x" << std::hex << address 
                  << ", pc=0x" << pc
                  << ", tick=" << std::dec << tick;
        if (store_it != store_map.end()) {
            std::cout << " [MATCH FOUND]";
        }
        std::cout << std::endl;
    }
}

void
SpillDetector::onInstructionExecute(Addr pc, Tick tick)
{
    total_instructions++;
    
    // Progress reporting every 5,000 instructions with detailed report
    if (total_instructions % 5000 == 0) {
        std::cout << "  📊 Instructions: " << total_instructions
                  << ", Spills: " << total_spills_detected
                  << ", Active stores tracked: " << store_map.size() << std::endl;
        
        // Show full detailed report at 5000 instructions
        if (total_instructions == 5000) {
            printSpillReport();
        }
    }
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
    
    // Heuristic 1: Time window check
    // Spills typically happen within a reasonable time window
    if (time_diff <= 0 || time_diff > MAX_SPILL_WINDOW) {
        return false;
    }
    
    // Heuristic 2: Instruction proximity
    // If store and load are the same instruction, it's likely not a spill
    // Yani, eğer store ve load işlemleri aynı instruction (aynı PC adresi) tarafından yapıldıysa, 
    //bu bir spill olarak sayılmaz ve fonksiyon false döner.
    /*
    
    Eğer aynı instruction hem store hem de load yapıyorsa (örneğin bir döngüde aynı komut sürekli çalışıyorsa), 
    bu genellikle bir register spill değildir; çünkü bu durumda veri belleğe yazılıp hemen tekrar okunmuyor olabilir, sadece döngüsel bir erişim olabilir.
    
    Aynı instruction (aynı PC) hem store hem load yaparsa → spill değildir.
    Farklı instruction'lar (farklı PC) aynı adrese önce store sonra load yaparsa → spill olarak tespit edilir.

    
    */
    if (store_info.pc == load_pc) {
        return false;
    }
    
    // Heuristic 3: Reasonable time difference
    // Too immediate suggests data forwarding, but be more permissive for longer times
    // Allow longer time windows to catch more spills
    if (time_diff < 10 || time_diff > 10000000) {  // Increased from 50000 to 10M ticks
        return false;
    }
    
    return true;
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
    std::ofstream log_file("m5out/cpp_spill_log.txt", std::ios::trunc);
    if (log_file.is_open()) {
        log_file << "# C++ Register Spill Detection Log\n";
        log_file << "# Generated by gem5 SpillDetector\n";
        log_file << "# =================================\n";
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
    static std::ofstream log_file("m5out/cpp_spill_log.txt", std::ios::app);
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
    std::cout << "  Total Spills Detected: " << detected_spills.size() << std::endl;
    
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
}

void
SpillDetector::writeAdvancedStatistics() const
{
    std::ofstream stats_file("m5out/spill_advanced_statistics.txt");
    if (!stats_file.is_open()) {
        std::cerr << "❌ Error: Could not open spill_advanced_statistics.txt for writing" << std::endl;
        return;
    }
    
    // Write gem5-style header
    stats_file << "---------- Begin Simulation Statistics ----------\n";
    stats_file << "\n# Register Spill Detection Advanced Statistics\n";
    stats_file << "# Generated by gem5 SpillDetector\n";
    stats_file << "# Analysis of register spill behavior during simulation\n\n";
    
    // Basic execution metrics
    stats_file << "spillDetector.total_instructions " << total_instructions << " # Total instructions executed\n";
    stats_file << "spillDetector.total_memory_operations " << (total_stores + total_loads) << " # Total memory operations (stores + loads)\n";
    stats_file << "spillDetector.total_stores " << total_stores << " # Total store instructions\n";
    stats_file << "spillDetector.total_loads " << total_loads << " # Total load instructions\n";
    stats_file << "spillDetector.total_spills_detected " << total_spills_detected << " # Total register spills detected\n\n";
    
    // Calculate rates and percentages
    uint64_t total_memory_operations = total_stores + total_loads;
    double spill_rate_memory = total_memory_operations > 0 ? 
        (static_cast<double>(total_spills_detected) / total_memory_operations) * 100.0 : 0.0;
    double spill_rate_instructions = total_instructions > 0 ? 
        (static_cast<double>(total_spills_detected) / total_instructions) * 100.0 : 0.0;
    double memory_intensity = total_instructions > 0 ? 
        (static_cast<double>(total_stores + total_loads) / total_instructions) * 100.0 : 0.0;
    double store_load_ratio = total_loads > 0 ? 
        static_cast<double>(total_stores) / total_loads : 0.0;
    
    stats_file << "spillDetector.spill_rate_memory_ops " << std::fixed << std::setprecision(4) << spill_rate_memory << " # Percentage of memory operations that are spills\n";
    stats_file << "spillDetector.spill_rate_instructions " << std::fixed << std::setprecision(4) << spill_rate_instructions << " # Percentage of instructions that trigger spills\n";
    stats_file << "spillDetector.memory_intensity " << std::fixed << std::setprecision(4) << memory_intensity << " # Percentage of instructions that are memory operations\n";
    stats_file << "spillDetector.store_load_ratio " << std::fixed << std::setprecision(4) << store_load_ratio << " # Ratio of stores to loads\n\n";
    
    // Performance impact analysis
    if (total_memory_operations > 0) {
        stats_file << "# Performance Impact Analysis\n";
        stats_file << "spillDetector.non_spill_memory_ops " << (total_memory_operations - total_spills_detected) << " # Memory operations that are not spills\n";
        stats_file << "spillDetector.spill_overhead_percentage " << std::fixed << std::setprecision(2) << spill_rate_memory << " # Estimated overhead due to spills\n\n";
    }
    
    // Temporal analysis
    if (!detected_spills.empty()) {
        std::vector<Tick> tick_differences;
        for (const auto& spill : detected_spills) {
            tick_differences.push_back(spill.tick_diff);
        }
        
        std::sort(tick_differences.begin(), tick_differences.end());
        
        Tick min_latency = tick_differences.front();
        Tick max_latency = tick_differences.back();
        Tick median_latency = tick_differences[tick_differences.size() / 2];
        Tick total_latency = 0;
        for (Tick diff : tick_differences) {
            total_latency += diff;
        }
        Tick avg_latency = total_latency / tick_differences.size();
        
        stats_file << "# Temporal Analysis\n";
        stats_file << "spillDetector.min_spill_latency " << min_latency << " # Minimum ticks between store and load in spills\n";
        stats_file << "spillDetector.max_spill_latency " << max_latency << " # Maximum ticks between store and load in spills\n";
        stats_file << "spillDetector.avg_spill_latency " << avg_latency << " # Average ticks between store and load in spills\n";
        stats_file << "spillDetector.median_spill_latency " << median_latency << " # Median ticks between store and load in spills\n\n";
    }
    
    // Hotspot analysis
    std::map<Addr, int> pc_frequency;
    std::map<Addr, int> address_frequency;
    
    for (const auto& spill : detected_spills) {
        pc_frequency[spill.store_pc]++;
        pc_frequency[spill.load_pc]++;
        address_frequency[spill.address]++;
    }
    
    if (!pc_frequency.empty()) {
        stats_file << "# Hotspot Analysis\n";
        
        // Find top spill-causing PCs
        std::vector<std::pair<int, Addr>> sorted_pcs;
        for (const auto& pc_count : pc_frequency) {
            sorted_pcs.push_back({pc_count.second, pc_count.first});
        }
        std::sort(sorted_pcs.rbegin(), sorted_pcs.rend());
        
        stats_file << "spillDetector.unique_pc_addresses " << pc_frequency.size() << " # Number of unique PC addresses involved in spills\n";
        stats_file << "spillDetector.unique_memory_addresses " << address_frequency.size() << " # Number of unique memory addresses involved in spills\n";
        
        // Top 5 hotspot PCs
        int top_count = std::min(5, static_cast<int>(sorted_pcs.size()));
        for (int i = 0; i < top_count; i++) {
            stats_file << "spillDetector.hotspot_pc_" << (i+1) << " 0x" << std::hex << sorted_pcs[i].second 
                      << " # PC with " << std::dec << sorted_pcs[i].first << " spill events\n";
        }
        stats_file << "\n";
    }
    
    // Memory address distribution
    if (!address_frequency.empty()) {
        std::vector<std::pair<int, Addr>> sorted_addresses;
        for (const auto& addr_count : address_frequency) {
            sorted_addresses.push_back({addr_count.second, addr_count.first});
        }
        std::sort(sorted_addresses.rbegin(), sorted_addresses.rend());
        
        stats_file << "# Memory Address Analysis\n";
        int top_addr_count = std::min(5, static_cast<int>(sorted_addresses.size()));
        for (int i = 0; i < top_addr_count; i++) {
            stats_file << "spillDetector.hotspot_address_" << (i+1) << " 0x" << std::hex << sorted_addresses[i].second 
                      << " # Memory address with " << std::dec << sorted_addresses[i].first << " spill events\n";
        }
        stats_file << "\n";
    }
    
    // Detection efficiency
    stats_file << "# Detection System Metrics\n";
    stats_file << "spillDetector.active_store_map_size " << store_map.size() << " # Current number of tracked store operations\n";
    stats_file << "spillDetector.detection_window_ticks " << MAX_SPILL_WINDOW << " # Maximum time window for spill detection\n";
    stats_file << "spillDetector.max_store_entries " << MAX_STORE_ENTRIES << " # Maximum store entries tracked simultaneously\n\n";
    
    stats_file << "---------- End Simulation Statistics ----------\n";
    stats_file.close();
    
    std::cout << "📊 Advanced statistics written to m5out/spill_advanced_statistics.txt" << std::endl;
}

void
SpillDetector::generateAdvancedStatisticsFile() const
{
    writeAdvancedStatistics();
}

} // namespace gem5
