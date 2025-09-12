/*
 * Copyright (c) 2025 Register Spilling Research
 * All rights reserved.
 *
 * Register Spill Detection System for gem5
 * 
 * This implements real-time instruction-level analysis to detect register
 * spills by tracking store-load patterns to the same memory addresses.
 */

#ifndef __CPU_SIMPLE_SPILL_DETECTOR_HH__
#define __CPU_SIMPLE_SPILL_DETECTOR_HH__

#include <unordered_map>
#include <vector>
#include <fstream>
#include "base/types.hh"

namespace gem5
{

/**
 * Register Spill Detection System
 * 
 * This class implements the exact approach requested by the user:
 * - Uses C++ std::unordered_map to track store operations
 * - Monitors each instruction's memory accesses in real-time
 * - Detects when a load operation accesses the same address as a recent store
 * - Counts such patterns as potential register spills
 */
class SpillDetector
{
  public:
    // Structure to store information about a store operation
    struct StoreInfo {
        Addr address;           // Memory address that was stored to
        Addr pc;               // Program counter of store instruction
        Tick tick;             // Simulation tick when store occurred
        unsigned size;         // Size of data stored (in bytes)
        uint64_t instruction_count; // Global instruction counter
        
        // Default constructor for std::unordered_map
        StoreInfo() : address(0), pc(0), tick(0), size(0), instruction_count(0) {}
        
        StoreInfo(Addr addr, Addr program_counter, Tick simulation_tick, 
                  unsigned data_size, uint64_t inst_count)
            : address(addr), pc(program_counter), tick(simulation_tick), 
              size(data_size), instruction_count(inst_count) {}
    };
    
    // Structure to store information about a detected spill
    struct SpillEvent {
        Addr store_pc;         // PC of the store instruction
        Addr load_pc;          // PC of the load instruction  
        Addr address;          // Memory address involved in spill
        Tick store_tick;       // When store happened
        Tick load_tick;        // When load happened
        Tick tick_diff;        // Time difference between store and load
        uint64_t store_inst_count; // Instruction count when store occurred
        uint64_t load_inst_count;  // Instruction count when load occurred
        
        SpillEvent(Addr s_pc, Addr l_pc, Addr addr, Tick s_tick, Tick l_tick,
                   uint64_t s_inst, uint64_t l_inst)
            : store_pc(s_pc), load_pc(l_pc), address(addr), 
              store_tick(s_tick), load_tick(l_tick), tick_diff(l_tick - s_tick),
              store_inst_count(s_inst), load_inst_count(l_inst) {}
    };

  private:
    // Map to track store operations: address -> StoreInfo
    // This is the core C++ map structure requested by the user
    std::unordered_map<Addr, StoreInfo> store_map;
    
    // Vector to store all detected spill events
    std::vector<SpillEvent> detected_spills;
    
    // Statistics counters
    uint64_t total_instructions;
    uint64_t total_stores;
    uint64_t total_loads;
    uint64_t total_spills_detected;
    
    // Configuration parameters
    static const Tick MAX_SPILL_WINDOW = 100000;  // Max ticks between store-load for spill
    static const unsigned MAX_STORE_ENTRIES = 10000; // Max stored addresses to track
    
    // Helper methods
    void cleanupOldStores(Tick current_tick);
    bool isLikelySpill(const StoreInfo& store_info, Addr load_pc, Tick load_tick);
    void writeSpillToLog(const SpillEvent& spill);
    void writeLogHeader();

  public:
    SpillDetector();
    ~SpillDetector();
    
    /**
     * Called when a store instruction executes
     * This is where we populate our C++ map with store information
     */
    void onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size);
    
    /**
     * Called when a load instruction executes  
     * This is where we check the map for matching stores and detect spills
     */
    void onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size);
    
    /**
     * Called for every instruction to update instruction counter
     */
    void onInstructionExecute(Addr pc, Tick tick);
    
    /**
     * Get current spill statistics
     */
    uint64_t getTotalSpills() const { return total_spills_detected; }
    uint64_t getTotalInstructions() const { return total_instructions; }
    uint64_t getTotalStores() const { return total_stores; }
    uint64_t getTotalLoads() const { return total_loads; }
    
    /**
     * Generate comprehensive spill report (console + file)
     */
    void printSpillReport();
    
    /**
     * Get spill rate as percentage
     */
    double getSpillRate() const;
    
    /**
     * Reset all counters and clear maps
     */
    void reset();
};

} // namespace gem5

#endif // __CPU_SIMPLE_SPILL_DETECTOR_HH__
