/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * Register Spill Detection System Implementation
 */

#include "cpu/simple/spill_detector.hh"
#include "base/trace.hh"
#include "debug/SpillDetector.hh"
#include <iostream>
#include <iomanip>
#include <set>

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
    if (total_stores <= 10) {
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
            
            // Print immediate notification
            std::cout << "  🎯 SPILL #" << total_spills_detected 
                      << ": Store@0x" << std::hex << store_info.pc
                      << " → Load@0x" << pc
                      << " (addr=0x" << address
                      << ", Δ" << std::dec << spill.tick_diff << " ticks)" << std::endl;
            
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
    
    // Progress reporting every 10,000 instructions
    if (total_instructions % 10000 == 0) {
        std::cout << "  📊 Instructions: " << total_instructions
                  << ", Spills: " << total_spills_detected
                  << ", Active stores tracked: " << store_map.size() << std::endl;
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
    // Too immediate suggests data forwarding, too long suggests unrelated
    if (time_diff < 10 || time_diff > 50000) {
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
SpillDetector::printSpillReport()
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
    
    std::cout << "\n🎯 SPILL DETECTION RESULTS:" << std::endl;
    std::cout << "  Detected Register Spills: " << total_spills_detected << std::endl;
    std::cout << "  Spill Rate: " << std::fixed << std::setprecision(4) 
              << getSpillRate() << "% of memory operations" << std::endl;
    
    if (!detected_spills.empty()) {
        std::cout << "\n📋 DETAILED SPILL EVENTS:" << std::endl;
        for (size_t i = 0; i < std::min(detected_spills.size(), size_t(10)); i++) {
            const auto& spill = detected_spills[i];
            std::cout << "  " << (i+1) << ". Store@0x" << std::hex << spill.store_pc
                      << " → Load@0x" << spill.load_pc
                      << " (addr=0x" << spill.address
                      << ", Δ" << std::dec << spill.tick_diff << " ticks)" << std::endl;
        }
        if (detected_spills.size() > 10) {
            std::cout << "     ... and " << (detected_spills.size() - 10) 
                      << " more spills" << std::endl;
        }
    }
    
    std::cout << "\n💡 ALGORITHM ANALYSIS:" << std::endl;
    std::cout << "  Method: Real-time C++ map-based store-load tracking" << std::endl;
    std::cout << "  Accuracy: Instruction-level precision" << std::endl;
    std::cout << "  Active store entries tracked: " << store_map.size() << std::endl;
    
    if (total_spills_detected > 0) {
        std::cout << "  ✅ Register spilling detected in program execution" << std::endl;
        std::cout << "  💾 Detailed log written to m5out/cpp_spill_log.txt" << std::endl;
    } else {
        std::cout << "  ✅ No register spilling patterns detected" << std::endl;
        std::cout << "  📝 Program shows efficient register usage" << std::endl;
    }
    ////////////////////////////////////////
    // File output as Comprehensive Report//
    ////////////////////////////////////////
    std::cout << "  📊 Writing comprehensive report to m5out/spill_report.txt..." << std::endl;
    
    std::ofstream report("m5out/spill_report.txt");
    if (!report.is_open()) {
        std::cout << "  ❌ ERROR: Failed to create report file" << std::endl;
        return;
    }
    
    // Calculate comprehensive metrics
    uint64_t total_memory_ops = total_stores + total_loads;
    uint64_t non_memory_instructions = total_instructions - total_memory_ops;
    double spill_vs_total_instructions = total_instructions > 0 ? (double(total_spills_detected) / total_instructions * 100.0) : 0.0;
    double spill_vs_memory_ops = total_memory_ops > 0 ? (double(total_spills_detected) / total_memory_ops * 100.0) : 0.0;
    double memory_intensity = total_instructions > 0 ? (double(total_memory_ops) / total_instructions * 100.0) : 0.0;
    
    // Count unique store/load PCs that caused spills
    std::set<Addr> spill_causing_store_pcs;
    std::set<Addr> spill_causing_load_pcs;
    for (const auto& spill : detected_spills) {
        spill_causing_store_pcs.insert(spill.store_pc);
        spill_causing_load_pcs.insert(spill.load_pc);
    }
    
    report << "=====================================\n";
    report << "  COMPREHENSIVE SPILL ANALYSIS REPORT\n";
    report << "=====================================\n";
    report << "Generated by gem5 SpillDetector\n";
    report << "Analysis Method: Real-time instruction-level C++ tracking\n\n";
    
    report << "INSTRUCTION EXECUTION SUMMARY\n";
    report << "-----------------------------\n";
    report << "Total Instructions Executed:     " << total_instructions << "\n";
    report << "  ├─ Store Instructions:         " << total_stores << " (" << (total_instructions > 0 ? double(total_stores)/total_instructions*100.0 : 0.0) << "%)\n";
    report << "  ├─ Load Instructions:          " << total_loads << " (" << (total_instructions > 0 ? double(total_loads)/total_instructions*100.0 : 0.0) << "%)\n";
    report << "  ├─ Total Memory Operations:    " << total_memory_ops << " (" << memory_intensity << "%)\n";
    report << "  └─ Non-Memory Instructions:    " << non_memory_instructions << " (" << (total_instructions > 0 ? double(non_memory_instructions)/total_instructions*100.0 : 0.0) << "%)\n\n";
    
    report << "REGISTER SPILL DETECTION RESULTS\n";
    report << "---------------------------------\n";
    report << "Total Register Spills Detected:  " << total_spills_detected << "\n";
    report << "Unique Store PCs causing spills:  " << spill_causing_store_pcs.size() << "\n";
    report << "Unique Load PCs causing spills:   " << spill_causing_load_pcs.size() << "\n\n";
    
    report << "SPILL RATIO ANALYSIS\n";
    report << "--------------------\n";
    report << "Spill Rate vs All Instructions:  " << std::fixed << std::setprecision(6) << spill_vs_total_instructions << "% (" << total_spills_detected << "/" << total_instructions << ")\n";
    report << "Spill Rate vs Memory Operations: " << spill_vs_memory_ops << "% (" << total_spills_detected << "/" << total_memory_ops << ")\n";
    report << "Memory Operation Intensity:      " << memory_intensity << "% of all instructions\n\n";
    
    report << "PERFORMANCE IMPACT ASSESSMENT\n";
    report << "------------------------------\n";
    if (spill_vs_total_instructions < 0.1) {
        report << "Assessment: EXCELLENT - Very low spill rate (<0.1%)\n";
        report << "Impact: Minimal performance degradation from register spilling\n";
    } else if (spill_vs_total_instructions < 1.0) {
        report << "Assessment: GOOD - Low spill rate (<1%)\n"; 
        report << "Impact: Minor performance impact from register spilling\n";
    } else if (spill_vs_total_instructions < 5.0) {
        report << "Assessment: MODERATE - Noticeable spill rate (1-5%)\n";
        report << "Impact: Moderate performance degradation from register pressure\n";
    } else {
        report << "Assessment: HIGH - Significant spill rate (>5%)\n";
        report << "Impact: Major performance impact, consider optimization\n";
    }
    report << "\n";
    
    report << "DETAILED SPILL EVENTS (First 20)\n";
    report << "---------------------------------\n";
    report << "Format: Store_PC -> Load_PC @ Memory_Address (Time_Diff ticks)\n";
    for (size_t i = 0; i < std::min(detected_spills.size(), size_t(20)); i++) {
        const auto& spill = detected_spills[i];
        report << std::setw(3) << (i+1) << ". 0x" << std::hex << spill.store_pc
               << " -> 0x" << spill.load_pc
               << " @ 0x" << spill.address
               << " (" << std::dec << spill.tick_diff << " ticks)\n";
    }
    if (detected_spills.size() > 20) {
        report << "... and " << (detected_spills.size() - 20) << " more spill events\n";
    }
    report << "\n";
    
    report << "METHODOLOGY NOTES\n";
    report << "-----------------\n";
    report << "- Spills detected by tracking store-load pairs to same memory addresses\n";
    report << "- Time window for spill detection: " << MAX_SPILL_WINDOW << " simulation ticks\n";
    report << "- Excludes same-instruction store-load patterns (likely not spills)\n";
    report << "- Real-time analysis using C++ unordered_map for O(1) address lookup\n";
    report << "- Note: 'Fills' (register reloads) are inherently detected as the load\n";
    report << "  portion of spill events. Each spill represents both spill and fill.\n\n";
    
    report << "DATA FILES\n";
    report << "----------\n";
    report << "- Detailed event log: m5out/cpp_spill_log.txt\n";
    report << "- Summary report: m5out/spill_report.txt (this file)\n";
    report << "=====================================\n";
    
    report.close();
    std::cout << "  ✅ Comprehensive report completed!" << std::endl;
}double
SpillDetector::getSpillRate() const
{
    uint64_t total_mem_ops = total_stores + total_loads;
    return total_mem_ops > 0 ? (double(total_spills_detected) / total_mem_ops * 100.0) : 0.0;
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

} // namespace gem5
