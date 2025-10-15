/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * Register Spill Detection System Implementation for RISC-V
 *
 * ===================================================================
 * COMPLETE DEVELOPMENT AND EXECUTION WORKFLOW - CHRONOLOGICAL ORDER:
 * ===================================================================
 *
 * 1. Clean previous build outputs and prepare workspace:
 *    $ rm -rf build/RISCV/
 *    $ rm -rf m5out/*
 *    # Clear all previous compilation and simulation outputs
 *
 * 2. Create and implement the SpillDetector header file:
 *    $ vim src/cpu/simple/riscv_spill_detector.hh
 *    # Define SpillDetector class with store-load tracking functionality
 *    # Include memory address mapping and spill detection algorithms
 *
 * 3. Create and implement the SpillDetector source file:
 *    $ vim src/cpu/simple/riscv_spill_detector.cc
 *    # Implement real-time spill detection with std::unordered_map
 *    # Add silent operation mode for clean output
 *    # Remove advanced statistics generation for simplified workflow
 *
 * 4. Integrate SpillDetector into TimingSimpleCPU:
 *    $ vim src/cpu/simple/timing.hh
 *    # Add #include "cpu/simple/riscv_spill_detector.hh"
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
 *    # Add Source('riscv_spill_detector.cc') to include new source file
 *
 * 7. Compile the gem5 simulator with spill detection (RISC-V step-by-step):
 *    # Build the simulator binary for RISC-V
 *    $ scons build/RISCV/gem5.opt -j12
 *    # Note: consider using -j$(nproc) for parallel builds on multicore machines
 *
 * 8. Run simulation with register spill detection (RISC-V example):
 *    # Run the hello workload and generate m5out in the repository root
 *    $ ./build/RISCV/gem5.opt configs/deprecated/example/se.py --cpu-type=TimingSimpleCPU --caches --cmd=tests/test-progs/hello/bin/riscv/linux/hello
 *    # After the run completes, create the benchmarks folder and move outputs
 *    $ mkdir -p benchmarks/builds/riscv_build/m5out
 *    $ mv m5out/* benchmarks/builds/riscv_build/m5out/
 *
 * 9. Verify spill detection output (RISC-V benchmarks layout):
 *    $ ls -la benchmarks/builds/riscv_build/m5out/
 *    $ head -20 benchmarks/builds/riscv_build/m5out/riscv_spill_stats.txt
 *    $ grep "^SPILL" benchmarks/builds/riscv_build/m5out/riscv_spill_stats.txt | wc -l
 *
 * ============================================================
 *
 */

#include "cpu/simple/riscv_spill_detector.hh"

#include <algorithm>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>

#include "base/trace.hh"
#include "debug/SpillDetector.hh"

/*
 * This file implements a simple register spill detection system for RISC-V.
 * It tracks memory accesses and identifies potential spill patterns
 * based on the observed load/store behavior.
 *
 * This is where the real-time register spill detection happens.
 * It is part of the gem5 simulator's core code (not the test program or Python).
 * It tracks every store and load instruction during simulation, using a C++ map to find store-load patterns that indicate register spills.
 * When a spill is detected, it logs the event (e.g., to riscv_spill_stats.txt).
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
    : total_instructions(0), total_stores(0), total_loads(0), total_spills_detected(0), total_spills_logged(0),
static_store_count(0), static_load_count(0), dynamic_store_count(0), dynamic_load_count(0), roi_active(false)
{
    // Reserve space for performance
    store_map.reserve(1000);
    detected_spills.reserve(100);

    // Write header to log file (only once at the beginning)
    writeLogHeader();

    // Silent initialization - no console output
    // ROI starts as inactive, will be activated by m5_work_begin
}

SpillDetector::~SpillDetector()
{
    // Silent cleanup - no console output
    // Only log file remains active
}

void
SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size, Addr current_sp)
{
    // Only track stores inside ROI
    if (!roi_active) {
        return;
    }

    total_stores++;
    dynamic_store_count++;

    // Create store info and add to our C++ map
    // This is the core map functionality requested by the user
    StoreInfo store_info(address, pc, tick, size, total_instructions, current_sp);
    store_map[address] = store_info;

    // Clean up old entries to prevent memory bloat
    if (store_map.size() > MAX_STORE_ENTRIES) {
        cleanupOldStores(tick);
    }

    // Silent operation - no console output
}

void
SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size, Addr current_sp)
{
    // Only track loads inside ROI
    if (!roi_active) {
        return;
    }

    total_loads++;
    dynamic_load_count++;

    // Clean up old stores first
    cleanupOldStores(tick);

    // Check if we have a recent store to this address
    auto store_it = store_map.find(address);
    if (store_it != store_map.end()) {
        const StoreInfo& store_info = store_it->second;

        // Real spill detection using isLikelySpill method
        if (isLikelySpill(store_info, pc, address, tick)) {
            total_spills_detected++;
            SpillEvent spill(store_info.pc, pc, address, store_info.tick, tick,
                             store_info.instruction_count, total_instructions);
            detected_spills.push_back(spill);
            writeSpillToLog(spill);
        }
        store_map.erase(store_it);
    }
}

void
SpillDetector::onInstructionExecute(Addr pc, Tick tick)
{
    total_instructions++;
    // No progress reporting - clean execution until final report
}

bool
SpillDetector::isLikelySpill(const StoreInfo& store_info, Addr load_pc, Addr address, Tick load_tick)
{
    // Simple spill detection: if store is followed by load to same address, it's a spill
    // No complex rules - just basic store-load pattern detection

    // 1. Check if store happened before load (time order)
    if (load_tick <= store_info.tick) {
        return false;  // Load happened before store, not a spill
    }

    return true;
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
    std::ofstream log_file("m5out/riscv_spill_stats.txt", std::ios::trunc);
    if (log_file.is_open()) {
        log_file << "# C++ Register Spill Detection Log - RISC-V\n";
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
    static std::ofstream log_file("m5out/riscv_spill_stats.txt", std::ios::app);
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

        total_spills_logged++; // Increment counter when actually written to log
    }
}

void
SpillDetector::printSpillReport() const
{
    // Silent operation - no console output
    // All spill detection results are logged to m5out/riscv_spill_stats.txt
    // This method remains for compatibility but produces no output
}

void
SpillDetector::beginROI()
{
    // Called when m5_work_begin is executed
    roi_active = true;

    // Optionally reset counters and clear maps to start fresh
    // (commented out to preserve stats from before ROI)
    // store_map.clear();
    // detected_spills.clear();
    // total_instructions = 0;
    // total_stores = 0;
    // total_loads = 0;
    // total_spills_detected = 0;
}

void
SpillDetector::endROI()
{
    // Called when m5_work_end is executed
    roi_active = false;

    // Clear the store map since we're done with ROI
    store_map.clear();
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
