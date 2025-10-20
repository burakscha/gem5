/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * Generic Register Spill Detection System Implementation
 *
 * ===================================================================
 * UNIFIED DEVELOPMENT AND EXECUTION WORKFLOW:
 * ===================================================================
 *
 * 1. Clean previous build outputs:
 * $ rm -rf build/
 * $ rm -rf m5out/*
 *
 * 2. Create the unified SpillDetector header file:
 * $ vim src/cpu/simple/spill_detector.hh
 * # Define the SpillDetector class with the generic 'current_stack_ptr' parameter
 *
 * 3. Create the unified SpillDetector source file (THIS FILE):
 * $ vim src/cpu/simple/spill_detector.cc
 * # Manage ISA-specific log file names using '#if defined(TARGET_ISA_...)'
 *
 * 4. Integrate SpillDetector into TimingSimpleCPU:
 * $ vim src/cpu/simple/timing.hh
 * # Add #include "cpu/simple/spill_detector.hh"
 * # Add SpillDetector* spillDetector member variable
 *
 * 5. Update the TimingSimpleCPU implementation:
 * $ vim src/cpu/simple/timing.cc
 * # Initialize spillDetector in the constructor
 * # Add onStore/onLoadInstruction calls in Store/Load operations
 * # (Pass the 'rsp' value for X86 or 'sp' for RISC-V to the 'current_stack_ptr' parameter)
 *
 * 6. Update the SConscript build system:
 * $ vim src/cpu/simple/SConscript
 * # Add Source('spill_detector.cc') (and remove the old 'x86_' or 'riscv_' files)
 *
 * 7. Compile the gem5 simulator for both architectures:
 * $ scons build/X86/gem5.opt -j12
 * $ scons build/RISCV/gem5.opt -j12
 *
 * 8. Run the simulation (both architectures now use the same compiled code):
 * $ ./build/X86/gem5.opt ... --cmd=.../hello.x86
 * $ ./build/RISCV/gem5.opt ... --cmd=.../hello.riscv
 *
 * 9. Verify the output (the correct log file will be created automatically):
 * $ ls -la m5out/
 * # (If X86 was run, x86_spill_stats.txt will appear; if RISC-V, riscv_spill_stats.txt will appear)
 *
 * ============================================================
 *
 */

#include "cpu/simple/spill_detector.hh" // Birleştirilmiş başlık dosyası
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
 * This code is part of the gem5 simulator's core and tracks
 * every store and load instruction during simulation. It uses a C++ map
 * to find store-load patterns that indicate register spills.
 */

// ========================================================================
// DEFINE ISA-SPECIFIC LOG FILE NAMES
// The gem5 build system provides USE_*_ISA macros (not TARGET_ISA_* anymore).
// See RELEASE-NOTES.md for details on this change.
// ========================================================================

#if defined(USE_X86_ISA)
    #define SPILL_LOG_FILENAME "m5out/x86_spill_stats.txt"
    #define ISA_NAME_STR "X86"
#elif defined(USE_RISCV_ISA)
    #define SPILL_LOG_FILENAME "m5out/riscv_spill_stats.txt"
    #define ISA_NAME_STR "RISC-V"
#elif defined(USE_ARM_ISA)
    #define SPILL_LOG_FILENAME "m5out/arm_spill_stats.txt"
    #define ISA_NAME_STR "ARM"
#elif defined(USE_SPARC_ISA)
    #define SPILL_LOG_FILENAME "m5out/sparc_spill_stats.txt"
    #define ISA_NAME_STR "SPARC"
#elif defined(USE_POWER_ISA)
    #define SPILL_LOG_FILENAME "m5out/power_spill_stats.txt"
    #define ISA_NAME_STR "POWER"
#elif defined(USE_MIPS_ISA)
    #define SPILL_LOG_FILENAME "m5out/mips_spill_stats.txt"
    #define ISA_NAME_STR "MIPS"
#else
    // Fallback for other architectures
    #define SPILL_LOG_FILENAME "m5out/generic_spill_stats.txt"
    #define ISA_NAME_STR "Generic"
#endif
// ========================================================================


namespace gem5
{

SpillDetector::SpillDetector()
    : total_instructions(0), total_stores(0), total_loads(0), total_spills_detected(0), total_spills_logged(0),
static_store_count(0), static_load_count(0), dynamic_store_count(0), dynamic_load_count(0)
{
    // Performans için yer ayır
    store_map.reserve(1000);
    detected_spills.reserve(100);

    // Write header to log file (only once at the beginning)
    writeLogHeader();

    // Silent initialization - no console output
}

SpillDetector::~SpillDetector()
{
    // Silent cleanup - no console output
}

void
SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size, Addr current_stack_ptr)
{
    total_stores++;
    dynamic_store_count++;

    // Create store info and add to our C++ map
    // Uses the generic 'current_stack_ptr' parameter
    StoreInfo store_info(address, pc, tick, size, total_instructions, current_stack_ptr);
    store_map[address] = store_info;

    // Cleanup old entries to prevent memory bloat
    if (store_map.size() > MAX_STORE_ENTRIES) {
        cleanupOldStores(tick);
    }
}

void
SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size, Addr current_stack_ptr)
{
    total_loads++;
    dynamic_load_count++;

    // Cleanup old stores
    cleanupOldStores(tick);

    // Check if there was a recent store to this address
    auto store_it = store_map.find(address);
    if (store_it != store_map.end()) {
        const StoreInfo& store_info = store_it->second;

        // isLikelySpill method for actual spill detection
        if (isLikelySpill(store_info, pc, address, tick)) {
            total_spills_detected++;
            SpillEvent spill(store_info.pc, pc, address, store_info.tick, tick,
                             store_info.instruction_count, total_instructions);
            detected_spills.push_back(spill);
            writeSpillToLog(spill);
        }
        // Bir load tarafından tüketilen store'u map'ten kaldır
        store_map.erase(store_it);
    }
}

void
SpillDetector::onInstructionExecute(Addr pc, Tick tick)
{
    // This function is identical for both architectures
    total_instructions++;
    // No progress report - silent operation until final report
}

bool
SpillDetector::isLikelySpill(const StoreInfo& store_info, Addr load_pc, Addr address, Tick load_tick)
{
    // This function is identical for both architectures
    // Simple spill detection: If a load follows a store to the same address, it's a spill

    // 1. Check if the store occurred before the load (temporal order)
    if (load_tick <= store_info.tick) {
        return false;  // Load happened before store, this is not a spill
    }

    return true;
}


void
SpillDetector::cleanupOldStores(Tick current_tick)
{
    // This function is identical for both architectures
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
    // Write log file header (create new file, overwrite if exists)
    // SPILL_LOG_FILENAME macro uses the ISA-specific file name determined at compile time
    std::ofstream log_file(SPILL_LOG_FILENAME, std::ios::trunc);
    if (log_file.is_open()) {
        // ISA_NAME_STR macro adds the correct architecture name (X86, RISC-V, etc.) to the log header
        log_file << "# C++ Register Spill Detection Log - " << ISA_NAME_STR << "\n";
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
    // Append detailed log entry
    // SPILL_LOG_FILENAME macro ensures appending to the correct ISA-specific file
    static std::ofstream log_file(SPILL_LOG_FILENAME, std::ios::app);
    if (log_file.is_open()) {
        log_file << "SPILL,"
                 << std::hex << spill.store_pc << ","
                 << std::hex << spill.load_pc << ","
                 << std::hex << spill.address << ","
                 << std::dec << spill.store_tick << ","
                 << spill.load_tick << ","
                 << spill.tick_diff << ","
                 << spill.store_inst_count << ","
                 << spill.load_inst_count
                 << std::endl;

        total_spills_logged++; // Increment counter when a log entry is actually written
    }
}

void
SpillDetector::printSpillReport() const
{
    // This function is identical for both architectures
    // Silent operation - no console output
    // All spill detection results are saved to SPILL_LOG_FILENAME
}

void
SpillDetector::reset()
{
    // This function is identical for both architectures
    store_map.clear();
    detected_spills.clear();
    total_instructions = 0;
    total_stores = 0;
    total_loads = 0;
    total_spills_detected = 0;
    total_spills_logged = 0;
}

} // namespace gem5
