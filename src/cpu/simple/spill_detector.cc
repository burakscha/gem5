/*
 * Copyright (c) 2025 CAST Research
 * All rights reserved.
 *
 * Generic Register Spill Detection System Implementation
 *
 * Two output modes controlled by the spill_verbose flag
 * (set via BaseTimingSimpleCPU.spill_verbose SimObject parameter):
 *
 *   verbose = false (default, SUMMARY MODE)
 *     - Zero disk I/O during the ROI.
 *     - At ROI end, writes one compact block (~300 bytes) with all counters.
 *     - Safe for all workloads regardless of spill count.
 *
 *   verbose = true (VERBOSE MODE)
 *     - Writes a SPILL CSV line for every detected event inside the ROI.
 *     - At ROI end, also writes the compact summary block.
 *     - WARNING: 419M spills (e.g. MCF) -> ~38 GB output file.
 *     - Only use this for small tests or targeted analysis.
 */

#include "cpu/simple/spill_detector.hh"
#include "base/output.hh"
#include "base/trace.hh"
#include "cpu/thread_context.hh"
#include "debug/SpillDetector.hh"
#include "sim/mem_state.hh"
#include "sim/process.hh"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <vector>

// ========================================================================
// ISA-specific log file names (determined at compile time)
// ========================================================================
#if defined(USE_X86_ISA)
#define SPILL_LOG_FILENAME "x86_spill_stats.txt"
#define ISA_NAME_STR "X86"
#elif defined(USE_RISCV_ISA)
#define SPILL_LOG_FILENAME "riscv_spill_stats.txt"
#define ISA_NAME_STR "RISC-V"
#elif defined(USE_ARM_ISA)
#define SPILL_LOG_FILENAME "arm_spill_stats.txt"
#define ISA_NAME_STR "ARM"
#elif defined(USE_SPARC_ISA)
#define SPILL_LOG_FILENAME "sparc_spill_stats.txt"
#define ISA_NAME_STR "SPARC"
#elif defined(USE_POWER_ISA)
#define SPILL_LOG_FILENAME "power_spill_stats.txt"
#define ISA_NAME_STR "POWER"
#elif defined(USE_MIPS_ISA)
#define SPILL_LOG_FILENAME "mips_spill_stats.txt"
#define ISA_NAME_STR "MIPS"
#else
#define SPILL_LOG_FILENAME "generic_spill_stats.txt"
#define ISA_NAME_STR "Generic"
#endif
// ========================================================================

namespace gem5 {

SpillDetector::SpillDetector()
    : total_instructions(0), total_stores(0), total_loads(0),
      total_spills_detected(0), static_store_count(0), static_load_count(0),
      dynamic_store_count(0), dynamic_load_count(0), roi_active(false),
      inside_roi(false), current_roi_id(0), roi_spills_detected(0),
      roi_stores(0), roi_loads(0), roi_instructions(0),
      roi_nonspill_reuse(0), roi_spill_reloads(0), roi_start_tick(0),
      roi_entry_total_insts(0), roi_entry_total_spills(0),
      evicted_stores(0), store_map_high_water(0), verbose(false) {
  std::memset(reuse_dist_hist, 0, sizeof(reuse_dist_hist));
  store_map.reserve(1000);
}

SpillDetector::~SpillDetector() {}

// -------------------------------------------------------------------------
// setVerbose — called by TimingSimpleCPU constructor from params
// -------------------------------------------------------------------------
void SpillDetector::setVerbose(bool v) {
  verbose = v;
  if (verbose) {
    // Write the full SPILL-format header so the file is self-documenting
    writeLogHeader();
  }
}

// -------------------------------------------------------------------------
// Hot-path callbacks
// -------------------------------------------------------------------------
bool SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick,
                                       unsigned size, Addr current_stack_ptr,
                                       bool sp_fp_relative,
                                       ThreadContext *tc) {
  total_stores++;
  dynamic_store_count++;

  if (inside_roi) {
    roi_stores++;
  }

  StoreInfo store_info(address, pc, tick, size, total_instructions,
                       current_stack_ptr, sp_fp_relative);
  store_map[address] = store_info;

  if (store_map.size() > MAX_STORE_ENTRIES) {
    evictOldStores();
  }
  if (store_map.size() > store_map_high_water) {
    store_map_high_water = store_map.size();
  }

  // Tag SP/FP-relative stack stores inside ROI as spill-write candidates.
  // Still an over-approximation (a pairing load is not required — it is
  // unknown at store time), but computed-pointer stack traffic is excluded.
  return inside_roi && sp_fp_relative && isStackAddress(address, tc);
}

bool SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick,
                                      unsigned size, Addr current_stack_ptr,
                                      bool sp_fp_relative,
                                      ThreadContext *tc) {
  total_loads++;
  dynamic_load_count++;

  if (inside_roi) {
    roi_loads++;
  }

  auto store_it = store_map.find(address);
  if (store_it != store_map.end()) {
    StoreInfo &store_info = store_it->second;

    if (isLikelySpill(store_info, pc, address, tick, size, tc)) {
      // A genuine spill pair requires spill-style addressing on BOTH
      // sides: store and reload each SP/FP-relative. Pairs that fail
      // only this filter are stack data reuse (arrays, structs, buffers
      // reached through computed pointers) and are counted separately.
      if (store_info.sp_relative && sp_fp_relative) {
        // The entry is intentionally NOT erased: a spilled value can be
        // reloaded many times before the slot is overwritten by the next
        // store to this address. The pair is counted once; every reload
        // is counted in roi_spill_reloads and tagged for cache stats.
        bool first_reload = !store_info.reloaded;
        store_info.reloaded = true;

        if (first_reload) {
          total_spills_detected++;
        }

        if (inside_roi) {
          if (first_reload) {
            roi_spills_detected++;
          }
          roi_spill_reloads++;

          // Reuse-distance histogram: log2 of the instruction distance
          // between the store and this reload (one entry per reload).
          uint64_t dist = total_instructions - store_info.instruction_count;
          int bucket = dist ? (63 - __builtin_clzll(dist)) : 0;
          reuse_dist_hist[bucket]++;

          // Verbose mode: write one CSV line per reload immediately
          if (verbose) {
            SpillEvent spill(store_info.pc, pc, address, store_info.tick,
                             tick, store_info.instruction_count,
                             total_instructions);
            writeSpillToLog(spill);
          }

          // Signal the caller that this load is a spill reload inside the
          // ROI so it can tag the Request with Request::SPILL_LOAD.
          return true;
        }
      } else if (inside_roi) {
        roi_nonspill_reuse++;
      }
    }
    // The entry survives failed matches too (e.g. a narrower load into
    // the middle of a spilled value must not destroy the pending store);
    // it is replaced by the next store to this address or evicted.
  }
  return false;
}

void SpillDetector::onInstructionExecute(Addr pc, Tick tick) {
  total_instructions++;

  if (inside_roi) {
    roi_instructions++;
  }
}

// -------------------------------------------------------------------------
// Spill detection logic
// -------------------------------------------------------------------------
bool SpillDetector::isLikelySpill(const StoreInfo &store_info, Addr load_pc,
                                  Addr address, Tick load_tick,
                                  unsigned load_size, ThreadContext *tc) {
  // 1. Temporal order: load must happen after store
  if (load_tick <= store_info.tick) {
    return false;
  }

  // 2. Size match: load and store must access same width
  if (load_size != store_info.size) {
    return false;
  }

  // 3. Stack region check (SE mode only)
  if (tc && !isStackAddress(address, tc))
    return false;

  return true;
}

bool SpillDetector::isStackAddress(Addr address, ThreadContext *tc) {
  if (!tc) return false;
  Process *process = tc->getProcessPtr();
  if (!process || !process->memState) return false;
  Addr stackBase = process->memState->getStackBase();
  Addr stackMin  = process->memState->getStackMin();
  return (address >= stackMin && address < stackBase);
}

// -------------------------------------------------------------------------
// Store map maintenance
// -------------------------------------------------------------------------
// Emergency eviction, only runs when MAX_STORE_ENTRIES is exceeded.
// Drops the oldest half of the map (by instruction count) so the cost is
// amortized O(1) per store. Every dropped entry is a potential censored
// spill pair, so the count is surfaced in the ROI summary.
void SpillDetector::evictOldStores() {
  std::vector<uint64_t> inst_counts;
  inst_counts.reserve(store_map.size());
  for (const auto &kv : store_map) {
    inst_counts.push_back(kv.second.instruction_count);
  }

  auto mid = inst_counts.begin() + inst_counts.size() / 2;
  std::nth_element(inst_counts.begin(), mid, inst_counts.end());
  const uint64_t threshold = *mid;

  for (auto it = store_map.begin(); it != store_map.end();) {
    if (it->second.instruction_count <= threshold) {
      it = store_map.erase(it);
      evicted_stores++;
    } else {
      ++it;
    }
  }
}

// -------------------------------------------------------------------------
// File output helpers
// -------------------------------------------------------------------------

// Called once when verbose mode is enabled — writes format documentation
void SpillDetector::writeLogHeader() {
  std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::trunc);
  if (!log_file.is_open()) return;

  log_file << "# Register Spill Detection Log - " << ISA_NAME_STR
           << " (VERBOSE MODE)\n";
  log_file << "# Generated by gem5 SpillDetector\n";
  log_file << "# =================================\n";
  log_file << "#\n";
  log_file << "# Format: "
              "SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,"
              "tick_diff,store_inst_count,load_inst_count\n";
  log_file << "#\n";
  log_file << "# Field Descriptions:\n";
  log_file << "#   store_pc        : PC (hex) of the store that spilled to memory\n";
  log_file << "#   load_pc         : PC (hex) of the load that retrieved the spill\n";
  log_file << "#   memory_address  : Stack address (hex) where the spill occurred\n";
  log_file << "#   store_tick      : Simulation tick of the store\n";
  log_file << "#   load_tick       : Simulation tick of the load\n";
  log_file << "#   tick_diff       : load_tick - store_tick\n";
  log_file << "#   store_inst_count: Global instruction counter at store\n";
  log_file << "#   load_inst_count : Global instruction counter at load\n";
  log_file << "#\n";
  log_file << "# NOTE: SPILL lines appear only within ROI regions.\n";
  log_file << "#       Each ROI region ends with a compact summary block.\n";
  log_file << "# WARNING: This is verbose mode. Disable spill_verbose for\n";
  log_file << "#          large workloads to avoid multi-GB output files.\n";
  log_file << "# =================================\n\n";
}

// Called per spill in verbose mode — writes one CSV SPILL line
void SpillDetector::writeSpillToLog(const SpillEvent &spill) {
  // Open and close per call so each write is flushed to the OS immediately.
  // This ensures SPILL lines appear before the ROI summary in the output file.
  // (verbose mode is intended for small tests only — performance is acceptable)
  std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
  if (!log_file.is_open()) return;

  log_file << "SPILL," << std::hex << spill.store_pc << ","
           << std::hex << spill.load_pc << ","
           << std::hex << spill.address << ","
           << std::dec << spill.store_tick << ","
           << spill.load_tick << ","
           << spill.tick_diff << ","
           << spill.store_inst_count << ","
           << spill.load_inst_count << "\n";
}

// Called at ROI end in both modes — writes the compact counter summary
void SpillDetector::writeROISummary(uint64_t workid) {
  std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
  if (!log_file.is_open()) return;

  double spill_rate = (roi_instructions > 0)
      ? (double)roi_spills_detected / roi_instructions * 100.0
      : 0.0;

  log_file << "# ================================================\n";
  log_file << "# ROI SUMMARY  ISA=" << ISA_NAME_STR
           << "  workid=" << workid << "\n";
  if (verbose) {
    log_file << "# (verbose mode - individual SPILL lines logged above)\n";
  } else {
    log_file << "# (summary mode - set spill_verbose=True for per-spill lines)\n";
  }
  log_file << "# ------------------------------------------------\n";
  log_file << "# entry_total_insts  : " << roi_entry_total_insts  << "\n";
  log_file << "# entry_total_spills : " << roi_entry_total_spills << "\n";
  log_file << "# roi_instructions   : " << roi_instructions       << "\n";
  log_file << "# roi_stores         : " << roi_stores             << "\n";
  log_file << "# roi_loads          : " << roi_loads              << "\n";
  log_file << "# roi_spills         : " << roi_spills_detected    << "\n";
  log_file << "# spill_rate         : " << std::fixed
           << std::setprecision(4) << spill_rate << "%\n";
  log_file << "# roi_spill_reloads  : " << roi_spill_reloads
           << "   (total reload accesses incl. repeats;\n"
           << "#                       == dcache spillLoadHits+Misses)\n";
  log_file << "# roi_nonspill_reuse : " << roi_nonspill_reuse
           << "   (stack reuse pairs rejected by SP/FP filter;\n"
           << "#                       roi_spills + this ~= old broad "
              "definition)\n";
  log_file << "# ------------------------------------------------\n";
  log_file << "# store_map_live     : " << store_map.size()       << "\n";
  log_file << "# store_map_peak     : " << store_map_high_water   << "\n";
  log_file << "# store_map_evicted  : " << evicted_stores         << "\n";
  log_file << "# reuse distance histogram (spills, log2 of instruction\n";
  log_file << "# distance between store and reload):\n";
  for (int i = 0; i < 64; i++) {
    if (reuse_dist_hist[i] == 0)
      continue;
    uint64_t lo = (i == 0) ? 0 : (1ULL << i);
    log_file << "# reuse_log2[" << std::setw(2) << i << "]     : "
             << reuse_dist_hist[i] << "   (dist >= " << lo << " insts)\n";
  }
  log_file << "# ================================================\n\n";
}

// -------------------------------------------------------------------------
// ROI entry / exit
// -------------------------------------------------------------------------
void SpillDetector::enterROI(uint64_t workid) {
  // Truncate the log file so stale data from previous runs is never mixed in.
  // This ensures exactly one ROI summary per simulation output file.
  // In verbose mode re-write the format header, since the truncation would
  // otherwise erase the one written by setVerbose() at construction.
  if (verbose) {
    writeLogHeader();
  } else {
    std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::trunc);
  }

  roi_active     = true;
  inside_roi     = true;
  current_roi_id = workid;

  roi_entry_total_insts  = total_instructions;
  roi_entry_total_spills = total_spills_detected;

  roi_spills_detected = 0;
  roi_stores          = 0;
  roi_loads           = 0;
  roi_instructions    = 0;
  roi_nonspill_reuse  = 0;
  roi_spill_reloads   = 0;
  roi_start_tick      = 0;

  evicted_stores       = 0;
  store_map_high_water = 0;
  std::memset(reuse_dist_hist, 0, sizeof(reuse_dist_hist));

  store_map.clear();

  if (verbose) {
    std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
    if (log_file.is_open()) {
      log_file << "# ========================================\n";
      log_file << "# ROI_BEGIN  workid=" << workid
               << "  entry_total_insts=" << roi_entry_total_insts
               << "  entry_total_spills=" << roi_entry_total_spills << "\n";
      log_file << "# ========================================\n";
    }
  }

  DPRINTF(SpillDetector, "Entered ROI (workid=%d)\n", workid);
}

void SpillDetector::exitROI(uint64_t workid) {
  inside_roi = false;

  // Always write the compact summary (both modes)
  writeROISummary(workid);

  DPRINTF(SpillDetector, "Exited ROI (workid=%d), ROI spills=%d\n", workid,
          roi_spills_detected);
}

// -------------------------------------------------------------------------
// Misc
// -------------------------------------------------------------------------
void SpillDetector::printSpillReport() const {
  // All output is in the log file written at exitROI().
}

void SpillDetector::reset() {
  store_map.clear();
  total_instructions    = 0;
  total_stores          = 0;
  total_loads           = 0;
  total_spills_detected = 0;
  roi_active            = false;
  inside_roi            = false;
  current_roi_id        = 0;
  roi_spills_detected   = 0;
  roi_stores            = 0;
  roi_loads             = 0;
  roi_instructions      = 0;
  roi_nonspill_reuse    = 0;
  roi_spill_reloads     = 0;
  roi_start_tick        = 0;
  roi_entry_total_insts  = 0;
  roi_entry_total_spills = 0;
  evicted_stores         = 0;
  store_map_high_water   = 0;
  std::memset(reuse_dist_hist, 0, sizeof(reuse_dist_hist));
  // verbose is intentionally NOT reset — it is set once at init.
}

} // namespace gem5
