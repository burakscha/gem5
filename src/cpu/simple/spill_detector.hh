/*
 * Copyright (c) 2025 CAST Research
 * All rights reserved.
 *
 * Generic Register Spill Detection System for gem5
 *
 * VERBOSITY FLAG
 * ==============
 * spill_verbose (default: false)
 *   false -> summary-only mode: counters are updated in RAM;
 *            a compact block is written to the log file only at ROI end.
 *            Output stays tiny (< 1 KB) regardless of spill count.
 *   true  -> verbose mode: every detected spill inside the ROI is written
 *            to the log file immediately, followed by a summary block.
 *            WARNING: can produce tens of GB for long workloads.
 *
 * Set via gem5 Python parameter:
 *   system.cpu.spill_verbose = True
 * or from se.py with --param:
 *   --param 'system.cpu.spill_verbose=True'
 */

#ifndef __CPU_SIMPLE_SPILL_DETECTOR_HH__
#define __CPU_SIMPLE_SPILL_DETECTOR_HH__

#include "base/types.hh"
#include <fstream>
#include <unordered_map>

namespace gem5 {

// Forward declarations (must be inside gem5 namespace)
class ThreadContext;
class Process;
class MemState;

class SpillDetector {
public:
  // -------------------------------------------------------
  // Store operation metadata (core of the detection map)
  // -------------------------------------------------------
  struct StoreInfo {
    Addr address;
    Addr pc;
    Tick tick;
    unsigned size;
    uint64_t instruction_count;
    Addr stack_ptr_at_store;
    // True when the store addressed memory SP/FP-relative — the addressing
    // mode compiler spill code uses. Only such stores can form spill pairs.
    bool sp_relative;
    // Set on the first matching reload. A spilled value can be reloaded
    // many times (e.g. inside a loop); the pair is counted once but every
    // reload is counted in roi_spill_reloads and tagged for cache stats.
    bool reloaded;

    StoreInfo()
        : address(0), pc(0), tick(0), size(0), instruction_count(0),
          stack_ptr_at_store(0), sp_relative(false), reloaded(false) {}

    StoreInfo(Addr addr, Addr program_counter, Tick simulation_tick,
              unsigned data_size, uint64_t inst_count, Addr current_stack_ptr,
              bool sp_rel)
        : address(addr), pc(program_counter), tick(simulation_tick),
          size(data_size), instruction_count(inst_count),
          stack_ptr_at_store(current_stack_ptr), sp_relative(sp_rel),
          reloaded(false) {}
  };

  // -------------------------------------------------------
  // Per-spill event (used only in verbose mode)
  // -------------------------------------------------------
  struct SpillEvent {
    Addr store_pc;
    Addr load_pc;
    Addr address;
    Tick store_tick;
    Tick load_tick;
    Tick tick_diff;
    uint64_t store_inst_count;
    uint64_t load_inst_count;

    SpillEvent(Addr s_pc, Addr l_pc, Addr addr, Tick s_tick, Tick l_tick,
               uint64_t s_inst, uint64_t l_inst)
        : store_pc(s_pc), load_pc(l_pc), address(addr), store_tick(s_tick),
          load_tick(l_tick), tick_diff(l_tick - s_tick),
          store_inst_count(s_inst), load_inst_count(l_inst) {}
  };

private:
  // address -> StoreInfo map (core detection structure)
  std::unordered_map<Addr, StoreInfo> store_map;

  // Global counters
  uint64_t total_instructions;
  uint64_t total_stores;
  uint64_t total_loads;
  uint64_t total_spills_detected;

  // Static / dynamic analysis counters (kept for completeness)
  uint64_t static_store_count;
  uint64_t static_load_count;
  uint64_t dynamic_store_count;
  uint64_t dynamic_load_count;

  // =========================================
  // ROI tracking
  // =========================================
  bool roi_active;
  bool inside_roi;
  uint64_t current_roi_id;

  uint64_t roi_spills_detected;
  uint64_t roi_stores;
  uint64_t roi_loads;
  uint64_t roi_instructions;
  // Store→load stack reuse pairs that pass the address/order/size/stack
  // checks but where store and/or load is NOT SP/FP-relative (stack
  // arrays, structs, buffers accessed through computed pointers).
  // roi_spills + roi_nonspill_reuse ≈ the old, broader spill definition,
  // so both definitions are measurable from a single run.
  uint64_t roi_nonspill_reuse;
  // Total spill reload accesses, counting repeated reloads of the same
  // spill slot. This is the spill-induced load traffic the cache sees:
  // dcache.spillLoadHits + dcache.spillLoadMisses == roi_spill_reloads.
  // roi_spills counts pairs (first reload per store) instead.
  uint64_t roi_spill_reloads;
  Tick     roi_start_tick;
  uint64_t roi_entry_total_insts;
  uint64_t roi_entry_total_spills;

  // =========================================
  // Verbosity flag
  // =========================================
  bool verbose; // set by TimingSimpleCPU from params.spill_verbose

  // =========================================
  // Debug / calibration counters (ROI-scoped, reported in ROI summary)
  // =========================================
  uint64_t evicted_stores;        // entries dropped by emergency eviction
  uint64_t store_map_high_water;  // max live entries seen inside the ROI
  // log2 histogram of reuse distance (instructions between the store and
  // its reload) for every spill detected inside the ROI. Answers directly
  // whether long-distance spill pairs exist and how many.
  uint64_t reuse_dist_hist[64];

  // Store-map safety cap. There is intentionally NO time window anymore:
  // a spill reload is valid no matter how far it is from its store.
  // (The old 50 µs tick window censored exactly the long-reuse-distance
  // pairs that are the most likely cache misses.) The map is bounded by
  // the distinct stack addresses with a pending store, so it stays small
  // in practice; if it ever exceeds this cap, the oldest half is evicted
  // and the eviction count appears in the ROI summary so any censoring
  // is visible in the data instead of silent.
  static const size_t MAX_STORE_ENTRIES = 1 << 20; // ~1M entries

  // -------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------
  // Emergency eviction: drops the oldest half of store_map (by
  // instruction count). Called only when MAX_STORE_ENTRIES is exceeded.
  void evictOldStores();

  // Writes the SPILL-format header (verbose mode only, called once)
  void writeLogHeader();

  // Writes a single SPILL CSV line (verbose mode only, per spill)
  void writeSpillToLog(const SpillEvent &spill);

  // Writes the compact ROI summary block (both modes)
  void writeROISummary(uint64_t workid);

public:
  SpillDetector();
  ~SpillDetector();

  // -------------------------------------------------------
  // Verbosity control — called by TimingSimpleCPU constructor
  // -------------------------------------------------------
  /**
   * Enable or disable per-spill verbose logging.
   * Must be called before any ROI begins.
   * When set to true the SPILL-format header is written immediately.
   */
  void setVerbose(bool v);
  bool isVerbose() const { return verbose; }

  // -------------------------------------------------------
  // Hot-path callbacks (called per instruction)
  // -------------------------------------------------------
  // Returns true when the store is a spill write candidate
  // (SP/FP-relative stack store inside ROI).
  // The caller (TimingSimpleCPU) uses this to tag the Request with SPILL_STORE.
  bool onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size,
                          Addr current_stack_ptr, bool sp_fp_relative,
                          ThreadContext *tc = nullptr);

  // Returns true when the load is confirmed as a spill reload inside the ROI.
  // The caller (TimingSimpleCPU) uses this to tag the Request with SPILL_LOAD.
  bool onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size,
                         Addr current_stack_ptr, bool sp_fp_relative,
                         ThreadContext *tc = nullptr);

  void onInstructionExecute(Addr pc, Tick tick);

  bool isLikelySpill(const StoreInfo &store_info, Addr load_pc, Addr address,
                     Tick load_tick, unsigned load_size, ThreadContext *tc);

  // Returns true if address falls within the process stack region (SE mode).
  bool isStackAddress(Addr address, ThreadContext *tc);

  void printSpillReport() const;

  // -------------------------------------------------------
  // Accessors
  // -------------------------------------------------------
  uint64_t getTotalSpills()       const { return total_spills_detected; }
  uint64_t getTotalInstructions() const { return total_instructions; }
  uint64_t getTotalStores()       const { return total_stores; }
  uint64_t getTotalLoads()        const { return total_loads; }

  void reset();

  // -------------------------------------------------------
  // ROI control (called from pseudo_inst.cc)
  // -------------------------------------------------------
  void enterROI(uint64_t workid);
  void exitROI(uint64_t workid);

  bool     isInsideROI()       const { return inside_roi; }
  uint64_t getROISpills()      const { return roi_spills_detected; }
  uint64_t getROIStores()      const { return roi_stores; }
  uint64_t getROILoads()       const { return roi_loads; }
  uint64_t getROIInstructions()const { return roi_instructions; }
};

} // namespace gem5

#endif // __CPU_SIMPLE_SPILL_DETECTOR_HH__
