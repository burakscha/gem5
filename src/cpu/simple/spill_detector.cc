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
#include "base/logging.hh"
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
#include <sstream>
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
    : next_store_event_id(1),
      classification_mode(ClassificationMode::Heuristic),
      total_instructions(0), total_store_insts(0), total_load_insts(0),
      total_spill_events(0), roi_active(false), inside_roi(false),
      roi_start_pending(false), current_roi_id(0), roi_sequence(0),
      log_initialized(false), roi_spill_events(0), roi_store_insts(0),
      roi_load_insts(0), roi_instructions(0), roi_nonspill_reuse(0),
      roi_spill_load_insts(0), roi_repeat_spill_load_insts(0),
      roi_spill_store_insts(0), roi_spill_load_l1_accesses(0),
      roi_paired_store_l1_accesses(0), roi_spill_store_l1_accesses(0),
      roi_spill_load_split_insts(0), roi_paired_store_split_insts(0),
      roi_spill_load_extra_fragments(0), roi_paired_store_extra_fragments(0),
      roi_spill_load_l1_hits(0), roi_spill_load_l1_misses(0),
      roi_spill_load_l2_hits(0), roi_spill_load_l2_misses(0),
      roi_paired_store_l1_hits(0), roi_paired_store_l1_misses(0),
      roi_paired_store_l2_hits(0), roi_paired_store_l2_misses(0),
      roi_spill_store_l1_hits(0), roi_spill_store_l1_misses(0),
      roi_spill_store_l2_hits(0), roi_spill_store_l2_misses(0),
      roi_spill_store_split_insts(0),
      roi_spill_store_extra_fragments(0),
      roi_start_tick(0), roi_entry_total_insts(0),
      roi_entry_total_spill_events(0), verbose(false), evicted_stores(0),
      store_map_high_water(0), global_summary_written(false) {
  std::memset(reuse_dist_hist, 0, sizeof(reuse_dist_hist));
  store_map.reserve(1000);
}

SpillDetector::~SpillDetector() { finalize(); }

// -------------------------------------------------------------------------
// setVerbose — called by TimingSimpleCPU constructor from params
// -------------------------------------------------------------------------
void SpillDetector::setVerbose(bool v) {
  verbose = v;
  if (verbose) {
    // Write the full SPILL-format header so the file is self-documenting
    writeLogHeader();
    log_initialized = true;
  }
}

void SpillDetector::configurePcMap(const std::string &path) {
  exact_store_pcs.clear();
  exact_load_pcs.clear();
  classification_mode = ClassificationMode::Heuristic;
  if (path.empty())
    return;

  std::ifstream input(path);
  fatal_if(!input.is_open(), "Cannot open spill PC map: %s", path);

  std::string line;
  unsigned line_number = 0;
  while (std::getline(input, line)) {
    line_number++;
    const size_t comment = line.find('#');
    if (comment != std::string::npos)
      line.erase(comment);
    std::istringstream fields(line);
    std::string kind;
    std::string address_text;
    if (!(fields >> kind))
      continue;
    fatal_if(!(fields >> address_text),
             "Missing address in spill PC map %s:%u", path, line_number);

    Addr pc = 0;
    try {
      size_t consumed = 0;
      pc = std::stoull(address_text, &consumed, 0);
      fatal_if(consumed != address_text.size(),
               "Invalid address in spill PC map %s:%u: %s", path,
               line_number, address_text);
    } catch (const std::exception &) {
      fatal("Invalid address in spill PC map %s:%u: %s", path, line_number,
            address_text);
    }

    if (kind == "store" || kind == "S") {
      exact_store_pcs.insert(pc);
    } else if (kind == "load" || kind == "L") {
      exact_load_pcs.insert(pc);
    } else {
      fatal("Invalid record type in spill PC map %s:%u: %s", path,
            line_number, kind);
    }
  }

  fatal_if(exact_store_pcs.empty() || exact_load_pcs.empty(),
           "Spill PC map %s must contain at least one store and one load PC",
           path);
  classification_mode = ClassificationMode::ExactPcMap;
}

// -------------------------------------------------------------------------
// Hot-path callbacks
// -------------------------------------------------------------------------
bool SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick,
                                       unsigned size, Addr current_stack_ptr,
                                       bool sp_fp_relative,
                                       unsigned l1_fragments,
                                       ThreadContext *tc) {
  pending_access.clear();
  pending_access.type = PendingType::Store;
  pending_access.address = address;
  pending_access.pc = pc;
  pending_access.issue_tick = tick;
  pending_access.size = size;
  pending_access.stack_ptr = current_stack_ptr;
  pending_access.sp_relative = sp_fp_relative;
  pending_access.stack_address = isStackAddress(address, tc);
  pending_access.l1_fragments = l1_fragments;

  // The tag covers every SP/FP-relative stack store, not just the ones that
  // turn out to be paired: whether a store belongs to a spill event is only
  // known once a later load reloads it, which is far too late to tag the
  // request. So the SPILL_STORE flag (and therefore the gem5 cache stats that
  // key off it) sees the superset reported as diag_stack_store_* in the ROI
  // summary, while the canonical spill_* counters are the paired subset.
  const bool selected = classification_mode == ClassificationMode::ExactPcMap
      ? exact_store_pcs.count(pc) != 0
      : sp_fp_relative;
  return inside_roi && pending_access.stack_address && selected;
}

bool SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick,
                                      unsigned size, Addr current_stack_ptr,
                                      bool sp_fp_relative,
                                      unsigned l1_fragments,
                                      ThreadContext *tc) {
  pending_access.clear();
  pending_access.type = PendingType::Load;
  pending_access.address = address;
  pending_access.pc = pc;
  pending_access.issue_tick = tick;
  pending_access.size = size;
  pending_access.stack_ptr = current_stack_ptr;
  pending_access.sp_relative = sp_fp_relative;
  pending_access.stack_address = isStackAddress(address, tc);
  pending_access.l1_fragments = l1_fragments;

  if (!inside_roi || !pending_access.stack_address)
    return false;

  auto store_it = store_map.find(address);
  if (store_it != store_map.end()) {
    const StoreInfo &store_info = store_it->second;

    if (isLikelySpill(store_info, pc, address, tick, size, tc)) {
      const bool selected =
          classification_mode == ClassificationMode::ExactPcMap
              ? exact_load_pcs.count(pc) != 0
              : store_info.sp_relative && sp_fp_relative;
      if (selected) {
        pending_access.predicted_spill_load = true;
        pending_access.matched_store_id = store_info.event_id;
      } else if (classification_mode == ClassificationMode::Heuristic) {
        pending_access.predicted_nonspill_reuse = true;
        pending_access.matched_store_id = store_info.event_id;
      }
    }
  }
  return pending_access.predicted_spill_load;
}

void SpillDetector::onInstructionCommit(bool is_load, bool is_store,
                                        Addr pc, Tick tick) {
  total_instructions++;
  if (is_load)
    total_load_insts++;
  if (is_store)
    total_store_insts++;

  // m5_work_begin invokes enterROI() before its own instruction commits.
  // Count the marker globally, activate the ROI afterwards, and exclude the
  // marker from every ROI counter.
  if (roi_start_pending) {
    roi_start_pending = false;
    inside_roi = true;
    roi_start_tick = tick;
    pending_access.clear();
    return;
  }

  if (inside_roi) {
    roi_instructions++;
    if (is_load)
      roi_load_insts++;
    if (is_store)
      roi_store_insts++;
  }

  if (!inside_roi) {
    pending_access.clear();
    return;
  }

  if (pending_access.type == PendingType::Store && is_store) {
    // Only stack stores are relevant to stack reuse/spill matching. This keeps
    // heap and global traffic out of the bounded detector map.
    const bool selected =
        classification_mode == ClassificationMode::ExactPcMap
            ? exact_store_pcs.count(pending_access.pc) != 0
            : true;
    if (pending_access.stack_address && selected) {
      const uint64_t event_id = next_store_event_id++;
      StoreInfo store_info(event_id, pending_access.address,
                           pending_access.pc, pending_access.issue_tick,
                           pending_access.size, total_instructions,
                           pending_access.stack_ptr,
                           pending_access.sp_relative,
                           pending_access.l1_fragments,
                           pending_access.l1_hits,
                           pending_access.l1_misses,
                           pending_access.l2_hits,
                           pending_access.l2_misses);
      store_map[pending_access.address] = store_info;

      const bool candidate =
          classification_mode == ClassificationMode::ExactPcMap
              ? selected
              : pending_access.sp_relative;
      if (candidate) {
        roi_spill_store_insts++;
        roi_spill_store_l1_accesses += pending_access.l1_fragments;
        roi_spill_store_l1_hits += pending_access.l1_hits;
        roi_spill_store_l1_misses += pending_access.l1_misses;
        roi_spill_store_l2_hits += pending_access.l2_hits;
        roi_spill_store_l2_misses += pending_access.l2_misses;
        if (pending_access.l1_fragments > 1) {
          roi_spill_store_split_insts++;
          roi_spill_store_extra_fragments += pending_access.l1_fragments - 1;
        }
      }

      if (store_map.size() > MAX_STORE_ENTRIES)
        evictOldStores();
      if (store_map.size() > store_map_high_water)
        store_map_high_water = store_map.size();
    }
  } else if (pending_access.type == PendingType::Load && is_load) {
    auto store_it = store_map.find(pending_access.address);
    if (store_it != store_map.end() &&
        store_it->second.event_id == pending_access.matched_store_id) {
      StoreInfo &store_info = store_it->second;
      if (pending_access.predicted_spill_load) {
        const bool first_reload = !store_info.reloaded;
        store_info.reloaded = true;

        roi_spill_load_insts++;
        roi_spill_load_l1_accesses += pending_access.l1_fragments;
        roi_spill_load_l1_hits += pending_access.l1_hits;
        roi_spill_load_l1_misses += pending_access.l1_misses;
        roi_spill_load_l2_hits += pending_access.l2_hits;
        roi_spill_load_l2_misses += pending_access.l2_misses;
        if (pending_access.l1_fragments > 1) {
          roi_spill_load_split_insts++;
          roi_spill_load_extra_fragments +=
              pending_access.l1_fragments - 1;
        }

        if (first_reload) {
          total_spill_events++;
          roi_spill_events++;
          roi_paired_store_l1_accesses += store_info.l1_fragments;
          roi_paired_store_l1_hits += store_info.l1_hits;
          roi_paired_store_l1_misses += store_info.l1_misses;
          roi_paired_store_l2_hits += store_info.l2_hits;
          roi_paired_store_l2_misses += store_info.l2_misses;
          if (store_info.l1_fragments > 1) {
            roi_paired_store_split_insts++;
            roi_paired_store_extra_fragments +=
                store_info.l1_fragments - 1;
          }
        } else {
          roi_repeat_spill_load_insts++;
        }

        const uint64_t dist = total_instructions -
                              store_info.instruction_count;
        const int bucket = dist ? (63 - __builtin_clzll(dist)) : 0;
        reuse_dist_hist[bucket]++;

        if (verbose) {
          SpillEvent spill(store_info.pc, pc, pending_access.address,
                           store_info.tick, tick,
                           store_info.instruction_count,
                           total_instructions);
          writeSpillToLog(spill);
        }
      } else if (pending_access.predicted_nonspill_reuse) {
        roi_nonspill_reuse++;
      }
    }
  }

  pending_access.clear();
}

void SpillDetector::recordPendingCacheOutcome(unsigned level, bool hit) {
  if (pending_access.type == PendingType::None)
    return;

  unsigned *hits = nullptr;
  unsigned *misses = nullptr;
  if (level == 0) {
    hits = &pending_access.l1_hits;
    misses = &pending_access.l1_misses;
  } else if (level == 1) {
    hits = &pending_access.l2_hits;
    misses = &pending_access.l2_misses;
  } else {
    return;
  }

  if (hit)
    (*hits)++;
  else
    (*misses)++;
}

void SpillDetector::discardPendingInstruction() {
  pending_access.clear();
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

  // spill_store is the write side (every SP/FP-relative stack store in the
  // ROI), spill_load the read-back side. spill_event pairs the two, so it is
  // the subset of spill_store that was actually read back again:
  //   spill_event <= spill_store   (a value may be written and never reloaded)
  //   spill_load  >= spill_event   (a value may be reloaded many times)
  const uint64_t spill_store = roi_spill_store_insts;
  const uint64_t spill_load = roi_spill_load_insts;
  const uint64_t spill_total = spill_store + spill_load;
  const uint64_t spill_store_unpaired =
      spill_store >= roi_spill_events ? spill_store - roi_spill_events : 0;
  const double spill_event_rate = roi_instructions > 0
      ? static_cast<double>(roi_spill_events) / roi_instructions * 100.0
      : 0.0;
  const double spill_inst_rate = roi_instructions > 0
      ? static_cast<double>(spill_total) / roi_instructions * 100.0
      : 0.0;

  log_file << "# ================================================\n";
  log_file << "# ROI SUMMARY  ISA=" << ISA_NAME_STR
           << "  workid=" << workid
           << "  sequence=" << roi_sequence << "\n";
  if (verbose) {
    log_file << "# (verbose mode - individual SPILL lines logged above)\n";
  } else {
    log_file << "# (summary mode - set spill_verbose=True for per-spill lines)\n";
  }
  log_file << "# ------------------------------------------------\n";
  log_file << "# metric_schema      : 7\n";
  log_file << "# classification     : "
           << (classification_mode == ClassificationMode::ExactPcMap
                   ? "compiler_pc_map_store_reload_match"
                   : "heuristic_stack_store_reload_match")
           << "\n";
  if (classification_mode == ClassificationMode::ExactPcMap) {
    log_file << "# exact_store_pc_count : " << exact_store_pcs.size() << "\n";
    log_file << "# exact_load_pc_count : " << exact_load_pcs.size() << "\n";
  } else {
    log_file << "#\n";
    log_file << "# DEFINITIONS\n";
    log_file << "#   spill_store : a stack store issued SP/FP-relative inside\n";
    log_file << "#                 the ROI. The write side. Counted whether or\n";
    log_file << "#                 not the value is ever read back.\n";
    log_file << "#   spill_load  : a load that reads back a value written by\n";
    log_file << "#                 such a store, from the same address at the\n";
    log_file << "#                 same width. Repeats are counted.\n";
    log_file << "#   spill_event : one (spill_store, first spill_load) pair =\n";
    log_file << "#                 one POTENTIAL spill. Hence\n";
    log_file << "#                 spill_event <= spill_store  (a value can be\n";
    log_file << "#                 written and never read back) and\n";
    log_file << "#                 spill_load  >= spill_event  (a value can be\n";
    log_file << "#                 read back many times).\n";
    log_file << "#   total_spill_insts : spill_store + spill_load.\n";
    log_file << "#\n";
    log_file << "# These are POTENTIAL spills: at the microarchitectural level\n";
    log_file << "# they cannot be separated from ABI callee-save traffic or\n";
    log_file << "# ordinary scalar stack locals. spill_store is the looser of\n";
    log_file << "# the two sides, since at store time a later reload is\n";
    log_file << "# unknowable. Use a compiler PC map (spill_pc_map) for an\n";
    log_file << "# exact classification.\n";
    log_file << "#\n";
  }
  log_file << "# entry_total_insts  : " << roi_entry_total_insts << "\n";
  log_file << "# entry_total_spill_event : "
           << roi_entry_total_spill_events << "\n";
  log_file << "# ---- ROI counters ----\n";
  log_file << "# roi_total_insts    : " << roi_instructions << "\n";
  log_file << "# roi_load           : " << roi_load_insts << "\n";
  log_file << "# roi_store          : " << roi_store_insts << "\n";
  log_file << "# ---- spill counters (ROI only, by construction) ----\n";
  log_file << "# spill_store        : " << spill_store << "\n";
  log_file << "# spill_load         : " << spill_load << "\n";
  log_file << "# total_spill_insts  : " << spill_total << "\n";
  log_file << "# spill_event        : " << roi_spill_events << "\n";
  log_file << "# spill_store_unpaired : " << spill_store_unpaired
           << "   (written inside the ROI, never read back there)\n";
  log_file << "# repeat_spill_load  : " << roi_repeat_spill_load_insts << "\n";
  log_file << "# spill_event_rate   : " << std::fixed
           << std::setprecision(4) << spill_event_rate << "%\n";
  log_file << "# spill_inst_rate    : " << std::fixed
           << std::setprecision(4) << spill_inst_rate << "%\n";
  log_file << "# ---- spill_store cache behaviour ----\n";
  log_file << "# spill_store_l1_accesses : "
           << roi_spill_store_l1_accesses << "\n";
  log_file << "# spill_store_l1_hits : " << roi_spill_store_l1_hits << "\n";
  log_file << "# spill_store_l1_misses : " << roi_spill_store_l1_misses << "\n";
  log_file << "# spill_store_l2_hits : " << roi_spill_store_l2_hits << "\n";
  log_file << "# spill_store_l2_misses : " << roi_spill_store_l2_misses << "\n";
  log_file << "# spill_store_split_insts : "
           << roi_spill_store_split_insts << "\n";
  log_file << "# spill_store_extra_fragments : "
           << roi_spill_store_extra_fragments << "\n";
  log_file << "# ---- spill_load cache behaviour ----\n";
  log_file << "# spill_load_l1_accesses : "
           << roi_spill_load_l1_accesses << "\n";
  log_file << "# spill_load_l1_hits : " << roi_spill_load_l1_hits << "\n";
  log_file << "# spill_load_l1_misses : " << roi_spill_load_l1_misses << "\n";
  log_file << "# spill_load_l2_hits : " << roi_spill_load_l2_hits << "\n";
  log_file << "# spill_load_l2_misses : " << roi_spill_load_l2_misses << "\n";
  log_file << "# spill_load_split_insts : "
           << roi_spill_load_split_insts << "\n";
  log_file << "# spill_load_extra_fragments : "
           << roi_spill_load_extra_fragments << "\n";
  log_file << "# ---- diagnostics (not headline metrics) ----\n";
  // Cache behaviour of just the paired subset of spill_store, captured per
  // store and attributed when the pairing happens. The headline
  // spill_store_* fields above cover the whole write side instead, which is
  // what the SPILL_STORE request flag tags, so they agree with the gem5
  // dcache.spillStoreHits/Misses statistics.
  log_file << "# diag_paired_store_l1_accesses : "
           << roi_paired_store_l1_accesses << "\n";
  log_file << "# diag_paired_store_l1_hits : "
           << roi_paired_store_l1_hits << "\n";
  log_file << "# diag_paired_store_l1_misses : "
           << roi_paired_store_l1_misses << "\n";
  log_file << "# diag_paired_store_l2_hits : "
           << roi_paired_store_l2_hits << "\n";
  log_file << "# diag_paired_store_l2_misses : "
           << roi_paired_store_l2_misses << "\n";
  log_file << "# diag_paired_store_split_insts : "
           << roi_paired_store_split_insts << "\n";
  log_file << "# diag_paired_store_extra_fragments : "
           << roi_paired_store_extra_fragments << "\n";
  log_file << "# diag_nonspill_reuse : " << roi_nonspill_reuse
           << "   (stack reuse pairs rejected by the SP/FP filter)\n";
  log_file << "# diag_store_map_live : " << store_map.size()     << "\n";
  log_file << "# diag_store_map_peak : " << store_map_high_water << "\n";
  log_file << "# diag_store_map_evicted : " << evicted_stores    << "\n";
  log_file << "# reuse distance histogram (spill events, log2 of instruction\n";
  log_file << "# distance between the spill_store and its first spill_load):\n";
  for (int i = 0; i < 64; i++) {
    if (reuse_dist_hist[i] == 0)
      continue;
    uint64_t lo = (i == 0) ? 0 : (1ULL << i);
    log_file << "# reuse_log2[" << std::setw(2) << i << "]     : "
             << reuse_dist_hist[i] << "   (dist >= " << lo << " insts)\n";
  }
  log_file << "# ================================================\n\n";
}


void SpillDetector::writeGlobalSummary() {
  if (global_summary_written || total_instructions == 0)
    return;
  global_summary_written = true;

  std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
  if (!log_file.is_open())
    return;

  log_file << "# ================================================\n";
  log_file << "# GLOBAL SUMMARY  ISA=" << ISA_NAME_STR << "\n";
  log_file << "# metric_schema      : 7\n";
  log_file << "# ---- global counters (whole simulation) ----\n";
  log_file << "# total_insts        : " << total_instructions << "\n";
  log_file << "# total_load         : " << total_load_insts << "\n";
  log_file << "# total_store        : " << total_store_insts << "\n";
  log_file << "# total_spill_event  : " << total_spill_events << "\n";
  log_file << "# ================================================\n\n";
}

// -------------------------------------------------------------------------
// ROI entry / exit
// -------------------------------------------------------------------------
void SpillDetector::enterROI(uint64_t workid) {
  // Initialize the file once per simulation. Later ROIs append independent
  // summary blocks instead of silently erasing earlier workids.
  if (!log_initialized) {
    if (verbose) {
      writeLogHeader();
    } else {
      std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME),
                             std::ios::trunc);
    }
    log_initialized = true;
  }

  if (roi_active || inside_roi || roi_start_pending) {
    DPRINTF(SpillDetector,
            "Ignoring nested ROI begin (current workid=%d, new workid=%d)\n",
            current_roi_id, workid);
    return;
  }

  roi_active        = true;
  inside_roi        = false;
  roi_start_pending = true;
  current_roi_id    = workid;
  roi_sequence++;

  roi_entry_total_insts = total_instructions;
  roi_entry_total_spill_events = total_spill_events;

  roi_spill_events = 0;
  roi_store_insts = 0;
  roi_load_insts = 0;
  roi_instructions = 0;
  roi_nonspill_reuse = 0;
  roi_spill_load_insts = 0;
  roi_spill_store_insts = 0;
  roi_repeat_spill_load_insts = 0;
  roi_spill_load_l1_accesses = 0;
  roi_paired_store_l1_accesses = 0;
  roi_spill_store_l1_accesses = 0;
  roi_spill_load_split_insts = 0;
  roi_paired_store_split_insts = 0;
  roi_spill_load_extra_fragments = 0;
  roi_paired_store_extra_fragments = 0;
  roi_spill_load_l1_hits = 0;
  roi_spill_load_l1_misses = 0;
  roi_spill_load_l2_hits = 0;
  roi_spill_load_l2_misses = 0;
  roi_paired_store_l1_hits = 0;
  roi_paired_store_l1_misses = 0;
  roi_paired_store_l2_hits = 0;
  roi_paired_store_l2_misses = 0;
  roi_spill_store_l1_hits = 0;
  roi_spill_store_l1_misses = 0;
  roi_spill_store_l2_hits = 0;
  roi_spill_store_l2_misses = 0;
  roi_spill_store_split_insts = 0;
  roi_spill_store_extra_fragments = 0;
  roi_start_tick = 0;

  evicted_stores = 0;
  store_map_high_water = 0;
  std::memset(reuse_dist_hist, 0, sizeof(reuse_dist_hist));
  store_map.clear();
  pending_access.clear();

  if (verbose) {
    std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
    if (log_file.is_open()) {
      log_file << "# ========================================\n";
      log_file << "# ROI_BEGIN  workid=" << workid
               << "  entry_total_insts=" << roi_entry_total_insts
               << "  entry_total_spill_events="
               << roi_entry_total_spill_events << "\n";
      log_file << "# ========================================\n";
    }
  }

  DPRINTF(SpillDetector, "Entered ROI (workid=%d)\n", workid);
}

void SpillDetector::exitROI(uint64_t workid) {
  if (!roi_active && !inside_roi) {
    DPRINTF(SpillDetector, "Ignoring ROI end without an active ROI\n");
    return;
  }

  // exitROI() runs while m5_work_end itself is executing. Deactivate before
  // that marker commits so it is excluded from ROI instruction counters.
  inside_roi = false;
  roi_active = false;
  roi_start_pending = false;

  // Always write the compact summary (both modes)
  writeROISummary(workid);

  DPRINTF(SpillDetector, "Exited ROI (workid=%d), ROI spills=%d\n", workid,
          roi_spill_events);
}

// -------------------------------------------------------------------------
// Misc
// -------------------------------------------------------------------------
void SpillDetector::printSpillReport() const {
  // All output is in the log file written at exitROI().
}

void SpillDetector::reset() {
  store_map.clear();
  pending_access.clear();
  next_store_event_id = 1;
  total_instructions = 0;
  total_store_insts = 0;
  total_load_insts = 0;
  total_spill_events = 0;
  roi_active = false;
  inside_roi = false;
  roi_start_pending = false;
  current_roi_id = 0;
  roi_sequence = 0;
  roi_spill_events = 0;
  roi_store_insts = 0;
  roi_load_insts = 0;
  roi_instructions = 0;
  roi_nonspill_reuse = 0;
  roi_spill_load_insts = 0;
  roi_spill_store_insts = 0;
  roi_repeat_spill_load_insts = 0;
  roi_spill_load_l1_accesses = 0;
  roi_paired_store_l1_accesses = 0;
  roi_spill_store_l1_accesses = 0;
  roi_spill_load_split_insts = 0;
  roi_paired_store_split_insts = 0;
  roi_spill_load_extra_fragments = 0;
  roi_paired_store_extra_fragments = 0;
  roi_spill_load_l1_hits = 0;
  roi_spill_load_l1_misses = 0;
  roi_spill_load_l2_hits = 0;
  roi_spill_load_l2_misses = 0;
  roi_paired_store_l1_hits = 0;
  roi_paired_store_l1_misses = 0;
  roi_paired_store_l2_hits = 0;
  roi_paired_store_l2_misses = 0;
  roi_spill_store_l1_hits = 0;
  roi_spill_store_l1_misses = 0;
  roi_spill_store_l2_hits = 0;
  roi_spill_store_l2_misses = 0;
  roi_spill_store_split_insts = 0;
  roi_spill_store_extra_fragments = 0;
  roi_start_tick = 0;
  roi_entry_total_insts = 0;
  roi_entry_total_spill_events = 0;
  evicted_stores = 0;
  store_map_high_water = 0;
  log_initialized = false;
  global_summary_written = false;
  std::memset(reuse_dist_hist, 0, sizeof(reuse_dist_hist));
  // verbose is intentionally NOT reset — it is set once at init.
}

void SpillDetector::finalize() {
  writeGlobalSummary();
}

} // namespace gem5
