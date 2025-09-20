/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * Register Spill Detection System Implementation
 * 
 * ===================================================================
 * COMPLETE DEVELOPMENT AND EXECUTION WORKFLOW - CHRONOLOGICAL ORDER:
 * ===================================================================
 * 
 * 1. Clean previous build outputs and prepare workspace:
 *    $ rm -rf build/X86/
 *    $ rm -rf m5out/*
 *    # Clear all previous compilation and simulation outputs
 * 
 * 2. Create and implement the SpillDetector header file:
 *    $ vim src/cpu/simple/spill_detector.hh
 *    # Define SpillDetector class with store-load tracking functionality
 *    # Include memory address mapping and spill detection algorithms
 * 
 * 3. Create and implement the SpillDetector source file:
 *    $ vim src/cpu/simple/spill_detector.cc
 *    # Implement real-time spill detection with std::unordered_map
 *    # Add silent operation mode for clean output
 *    # Remove advanced statistics generation for simplified workflow
 * 
 * 4. Integrate SpillDetector into TimingSimpleCPU:
 *    $ vim src/cpu/simple/timing.hh
 *    # Add #include "cpu/simple/spill_detector.hh"
 *    # Add SpillDetector* spillDetector member variable
 * 
 * 5. Modify TimingSimpleCPU implementation:
 *    $ vim src/cpu/simple/timing.cc
 *    # Initialize spillDetector in constructor
 *    # Add onStoreInstruction() calls for store operations
 *    # Add onLoadInstruction() calls for load operations
 *    # Clean up generateAdvancedStatisticsFile() method calls
 * 
 * 6. Update SConscript for build system:
 *    $ vim src/cpu/simple/SConscript
 *    # Add Source('spill_detector.cc') to include new source file
 * 
 * 7. Compile the gem5 simulator with spill detection (x86 step-by-step):
 *    # Build the simulator binary for x86
 *    $ scons build/X86/gem5.opt -j12
 *    # Note: consider using -j$(nproc) for parallel builds on multicore machines
 *
 * 8. Run simulation with register spill detection (x86 example):
 *    # Run the hello workload and generate m5out in the repository root
 *    $ ./build/X86/gem5.opt configs/deprecated/example/se.py --cpu-type=TimingSimpleCPU --caches --cmd=tests/test-progs/hello/bin/x86/linux/hello
 *    # After the run completes, create the fair comparison folder and move outputs
 *    $ mkdir -p fair_comparison/x86_build/m5out
 *    $ mv m5out/* fair_comparison/x86_build/m5out/
 *
 * 9. Verify spill detection output (x86 fair-comparison layout):
 *    $ ls -la fair_comparison/x86_build/m5out/
 *    $ head -20 fair_comparison/x86_build/m5out/x86_spill_stats.txt
 *    $ grep "^SPILL" fair_comparison/x86_build/m5out/x86_spill_stats.txt | wc -l
 * 
 * 9. Verify spill detection output:
 *    $ ls -la m5out/
 *    $ head -20 m5out/x86_spill_stats.txt
 *    $ grep "^SPILL" m5out/x86_spill_stats.txt | wc -l
 * 
 * ============================================================
 * 
 */

#include "cpu/simple/x86_spill_detector.hh"
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
 * When a spill is detected, it logs the event (e.g., to spill_log.txt).
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
    
    // Silent initialization - no console output
}

SpillDetector::~SpillDetector()
{
    // Silent cleanup - no console output
    // Only log file remains active
}

void
SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size, Addr current_rsp)
{
    total_stores++;
    
    // Create store info and add to our C++ map
    // This is the core map functionality requested by the user
    StoreInfo store_info(address, pc, tick, size, total_instructions, current_rsp);
    store_map[address] = store_info;
    
    // Clean up old entries to prevent memory bloat
    if (store_map.size() > MAX_STORE_ENTRIES) {
        cleanupOldStores(tick);
    }
    
    // Silent operation - no console output
}

void
SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size, Addr current_rsp)
{
    const double SPILL_SCORE_THRESHOLD = 3.0; // Threshold for confirming a spill
    double spill_score = 0.0; // Calculate for potential spill score
    total_loads++;
    
    // Check if we have a recent store to this address
    // This is where we use the C++ map to detect spill patterns
    auto store_it = store_map.find(address); // 🔍 SEARCHING: Does store contained by this address?

    if (store_it != store_map.end()) {  // ✅ FOUND!
        const StoreInfo& store_info = store_it->second;

            spill_score = calculateSpillScore(store_info, pc, tick, current_rsp);

            if (spill_score >= SPILL_SCORE_THRESHOLD) {
                // 🎯 SPILL DETECTED!! Store followed by load to same address
                total_spills_detected++;

                SpillEvent spill(store_info.pc, pc, address, store_info.tick, tick,
                            store_info.instruction_count, total_instructions, spill_score);
                
                
                detected_spills.push_back(spill);
                
                
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
double
SpillDetector::calculateSpillScore(const StoreInfo& store_info, Addr load_pc, Tick load_tick, Addr current_rsp)
{
    // Configuration Parameters
    const Tick TIME_WINDOW_MAX = 20000; // Maximum time window to consider for spill detection
    const uint64_t STACK_PROXIMITY_BYTES = 1024; // Proximity to stack pointer (RSP) to consider
    double spill_score = 0.0; // Calculate for potential spill score
    Tick time_diff = load_tick - store_info.tick; // Time difference between store and load
    uint64_t inst_diff = total_instructions - store_info.instruction_count; // Instruction difference between store and load

    
    // Basic sanity check: Load must come after store
    // Different instructions check: If store and load are the same instruction, it's not a spill
    if (time_diff <= 0 || store_info.pc == load_pc) { // ❌ Load store'dan önce gelmiş || LOAD -❌-> STORE
        return 0.0;
    }

    if (inst_diff <= 0) {
        return 0.0; // Geçersiz durum, puanı 0
    }


    /*
    * Calculate spill score based on multiple heuristics:
    * A. Time Proximity: Closer in time = higher score
    * B. Dynamic Stack Check: Address near current RSP = higher score
    * C. Data Size: 8-byte stores (x86-64) = higher score
    * D. Instruction Distance: Very close store/load = lower score (less likely spill
    */

    // (Kural A: Zaman Yakınlığı) A. Time Proximity
    // Ne kadar yakınsa o kadar yüksek puan. How close in time = higher score
    if (time_diff < 500) spill_score += 1.5;
    else if (time_diff < 5000) spill_score += 1.0;
    else if (time_diff < TIME_WINDOW_MAX) spill_score += 0.5;
    else return 0.0; // Timeout

    // (Kural B: Dinamik Stack Kontrolü) B. Dynamic Stack Check
    // Adres, anlık stack pointer'ına (RSP) ne kadar yakın?
    if (store_info.rsp_at_store != 0 && 
        store_info.address >= store_info.rsp_at_store - STACK_PROXIMITY_BYTES && 
        store_info.address < store_info.rsp_at_store) {
        spill_score += 2.0;
    }

    // (Kural C: Veri Boyutu) C. Data Size
    // In a 64-bit architecture, an 8-byte store is a strong signal.
    if (store_info.size == 8) {
        spill_score += 1.0;
    }

    // (Kural D: Komut Mesafesi) D. Instruction Distance
    // Çok yakın store/load çiftleri genelde spill değildir. | Very close store/load pairs are often not spills.
    if (inst_diff < 5) {
        spill_score -= 1.0; // Penalty
    } else {
        spill_score += 0.5;
    }

    return spill_score;    
}


void
SpillDetector::cleanupOldStores(Tick current_tick)
{
    for (auto it = store_map.begin(); it != store_map.end(); ) {
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
    std::ofstream log_file("m5out/x86_spill_stats.txt", std::ios::trunc);
    if (log_file.is_open()) {
        log_file << "# C++ Register Spill Detection Log\n";
        log_file << "# Generated by gem5 SpillDetector\n";
        log_file << "# =================================\n";
        log_file << "#\n";
        log_file << "# Format: SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count,spill_score\n";
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
        log_file << "#   spill_score    : Calculated spill confidence score (higher is more likely)\n";
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
    static std::ofstream log_file("m5out/x86_spill_stats.txt", std::ios::app);
    if (log_file.is_open()) {
        log_file << "SPILL," 
                 << std::hex << spill.store_pc << ","
                 << std::hex << spill.load_pc << ","
                 << std::hex << spill.address << ","
                 << std::dec << spill.store_tick << ","
                 << spill.load_tick << ","
                 << spill.tick_diff << ","
                 << spill.store_inst_count << ","
                 << spill.load_inst_count << ","
                 << std::fixed << std::setprecision(2) << spill.spill_score
                 << std::endl;

        total_spills_logged++; // Increment counter when actually written to log
    }
}

void 
SpillDetector::printSpillReport() const
{
    // Silent operation - no console output
    // All spill detection results are logged to m5out/x86_spill_stats.txt
    // This method remains for compatibility but produces no output
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
