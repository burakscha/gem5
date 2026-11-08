/*
 * Copyright (c) 2025 CAST Research
 * All rights reserved.
 *
 * Runtime register-spill detection for gem5 (register spill study).
 * See spill_detector.hh for the definitions (metric schema 10).
 *
 * Two output modes controlled by the spill_verbose flag
 * (set via BaseTimingSimpleCPU.spill_verbose SimObject parameter):
 *
 *   verbose = false (default, SUMMARY MODE)
 *     - Zero disk I/O during the ROI.
 *     - At ROI end, writes one compact block with all counters.
 *
 *   verbose = true (VERBOSE MODE)
 *     - Writes a SPILL CSV line for every spill load inside the ROI.
 *     - At ROI end, also writes the compact summary block.
 *     - WARNING: long workloads produce multi-GB files.
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

namespace {

constexpr int METRIC_SCHEMA = 10;

} // anonymous namespace

// -------------------------------------------------------------------------
// Counter helpers
// -------------------------------------------------------------------------
void SpillDetector::CacheTally::add(unsigned fragments, unsigned level1_hits,
                                    unsigned level1_misses,
                                    unsigned level2_hits,
                                    unsigned level2_misses) {
  insts++;
  l1_hits += level1_hits;
  l1_misses += level1_misses;
  l2_hits += level2_hits;
  l2_misses += level2_misses;
  if (fragments > 1)
    split_insts++;
}

// -------------------------------------------------------------------------
// Construction / configuration
// -------------------------------------------------------------------------
SpillDetector::SpillDetector()
    : next_store_event_id(1), total_instructions(0), total_store_insts(0),
      total_load_insts(0), roi_active(false), inside_roi(false),
      roi_start_pending(false), current_roi_id(0), roi_sequence(0),
      log_initialized(false), roi_start_tick(0),
      verbose(false), global_summary_written(false) {
  max_store_size = 1;
  resetRoiCounters();
}

SpillDetector::~SpillDetector() { finalize(); }

void SpillDetector::setVerbose(bool v) {
  verbose = v;
  if (verbose) {
    // Write the full header so the file is self-documenting
    writeLogHeader();
    log_initialized = true;
  }
}

// -------------------------------------------------------------------------
// Hot-path callbacks
// -------------------------------------------------------------------------
bool SpillDetector::onStoreInstruction(Addr address, Addr pc, Tick tick,
                                       unsigned size, unsigned l1_fragments,
                                       ThreadContext *tc) {
  pending_access.clear();
  pending_access.type = PendingType::Store;
  pending_access.address = address;
  pending_access.pc = pc;
  pending_access.issue_tick = tick;
  pending_access.size = size;
  pending_access.stack_address = isStackAddress(address, tc);
  pending_access.l1_fragments = std::max(l1_fragments, 1u);

  // Whether this store will ever be read back is unknowable here, so every
  // stack store is tagged; the spill-event tally picks the read-back ones
  // out at their first reload.
  pending_access.tagged = inside_roi && pending_access.stack_address;
  return pending_access.tagged;
}

void SpillDetector::onAtomicWrite(Addr address, Addr pc, Tick tick,
                                  unsigned size, ThreadContext *tc) {
  pending_access.clear();
  pending_access.type = PendingType::AtomicWrite;
  pending_access.address = address;
  pending_access.pc = pc;
  pending_access.issue_tick = tick;
  pending_access.size = size;
  pending_access.stack_address = isStackAddress(address, tc);
}

bool SpillDetector::onLoadInstruction(Addr address, Addr pc, Tick tick,
                                      unsigned size, unsigned l1_fragments,
                                      ThreadContext *tc) {
  pending_access.clear();
  pending_access.type = PendingType::Load;
  pending_access.address = address;
  pending_access.pc = pc;
  pending_access.issue_tick = tick;
  pending_access.size = size;
  pending_access.stack_address = isStackAddress(address, tc);
  pending_access.l1_fragments = std::max(l1_fragments, 1u);

  if (!inside_roi || !pending_access.stack_address)
    return false;

  // The load reads back the most recent store whose bytes contain its
  // address; load and store widths may differ (e.g. two 4-byte stores read
  // back by one 8-byte load, or the low half of an 8-byte store).
  auto store_it = findCoveringStore(address);
  if (store_it == store_map.end() || store_it->second.atomic)
    return false;
  if (!isReload(store_it->second, address, tick, tc))
    return false;

  pending_access.matched_store_id = store_it->second.event_id;
  pending_access.matched_store_addr = store_it->first;
  pending_access.tagged = true;
  return true;
}

void SpillDetector::onInstructionCommit(bool is_load, bool is_store,
                                        Addr pc, Tick tick, Addr sp) {
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

  if (!inside_roi) {
    pending_access.clear();
    return;
  }

  roi_instructions++;
  if (is_load)
    roi_load_insts++;
  if (is_store)
    roi_store_insts++;

  const PendingAccess &p = pending_access;
  if (p.type == PendingType::Store && is_store) {
    // Heap and global traffic stays out of the bounded map.
    if (p.stack_address) {
      recordStore(p);
      roi_spill_store++;
      spill_store_cache.add(p.l1_fragments, p.l1_hits, p.l1_misses,
                            p.l2_hits, p.l2_misses);
    }
  } else if (p.type == PendingType::AtomicWrite) {
    // Not counted, but its bytes no longer hold an older store's value.
    if (p.stack_address)
      recordStore(p);
  } else if (p.type == PendingType::Load && is_load) {
    auto store_it = store_map.find(p.matched_store_addr);
    const bool matched = p.matched_store_id != 0 &&
                         store_it != store_map.end() &&
                         store_it->second.event_id == p.matched_store_id;

    if (matched) {
      StoreInfo &store_info = store_it->second;
      const bool first_reload = !store_info.reloaded;
      store_info.reloaded = true;

      roi_spill_load++;
      spill_load_cache.add(p.l1_fragments, p.l1_hits, p.l1_misses, p.l2_hits,
                           p.l2_misses);
      // Diagnostic only: the counters above and below do not depend on it.
      if (track_stack_release && store_info.max_sp > p.address) {
        loads_after_release++;
        if (first_reload)
          events_after_release++;
      }
      if (first_reload) {
        roi_spill_event++;
        spill_event_cache.add(store_info.l1_fragments, store_info.l1_hits,
                              store_info.l1_misses, store_info.l2_hits,
                              store_info.l2_misses);
      }

      if (verbose) {
        writeSpillToLog(SpillEvent(store_info.pc, p.pc, p.address,
                                   store_info.tick, tick,
                                   store_info.instruction_count,
                                   total_instructions));
      }
    }
  }

  pending_access.clear();
  if (track_stack_release)
    noteStackPointer(sp);
}

// sp rose from last_sp: the bytes [last_sp, sp) were released. Every store
// with bytes there remembers it; a later spill load of those bytes is a
// stack-release suspect.
void SpillDetector::noteStackPointer(Addr sp) {
  if (sp_known && sp > last_sp) {
    const Addr span = max_store_size - 1;
    const Addr lowest = last_sp >= span ? last_sp - span : 0;
    for (auto it = store_map.lower_bound(lowest);
         it != store_map.end() && it->first < sp; ++it)
      it->second.max_sp = std::max(it->second.max_sp, sp);
  }
  last_sp = sp;
  sp_known = true;
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
// Pairing rules
// -------------------------------------------------------------------------
bool SpillDetector::isReload(const StoreInfo &store_info, Addr address,
                             Tick load_tick, ThreadContext *tc) {
  // 1. Temporal order: load must happen after store
  if (load_tick <= store_info.tick) {
    return false;
  }

  // 2. Address: findCoveringStore() already placed the load's address in
  //    [store address, store address + store size). The widths may differ.

  // 3. Stack region check (SE mode only)
  if (tc && !isStackAddress(address, tc))
    return false;

  return true;
}

bool SpillDetector::isStackAddress(Addr address, ThreadContext *tc) {
  if (!tc) return false;
  Process *process = tc->getProcessPtr();
  if (!process || !process->memState) return false;
  // The first access to a stack page not mapped yet lies below stackMin: its
  // translation faults, the attempt is discarded, the fault handler grows
  // the stack (MemState::fixupFault), and the re-executed access passes
  // this check (tc26).
  Addr stackBase = process->memState->getStackBase();
  Addr stackMin  = process->memState->getStackMin();
  return (address >= stackMin && address < stackBase);
}

// -------------------------------------------------------------------------
// Store map maintenance
// -------------------------------------------------------------------------
void SpillDetector::recordStore(const PendingAccess &p) {
  StoreInfo info;
  info.event_id = next_store_event_id++;
  info.address = p.address;
  info.pc = p.pc;
  info.tick = p.issue_tick;
  info.size = p.size;
  info.instruction_count = total_instructions;
  info.atomic = p.type == PendingType::AtomicWrite;
  // Written below sp (outside the live stack): released already.
  info.max_sp = (sp_known && last_sp > p.address) ? last_sp : 0;
  info.l1_fragments = p.l1_fragments;
  info.l1_hits = p.l1_hits;
  info.l1_misses = p.l1_misses;
  info.l2_hits = p.l2_hits;
  info.l2_misses = p.l2_misses;
  // This store now owns [address, address + size): entries it overwrites
  // completely can never be read back and are dropped. An entry it overlaps
  // only partly keeps its other bytes; where they overlap, the lookup
  // prefers this newer store.
  eraseCoveredStores(p.address, p.size);
  store_map[p.address] = info;
  max_store_size = std::max(max_store_size, std::max(p.size, 1u));
  if (store_map.size() > MAX_STORE_ENTRIES)
    evictOldStores();
}

SpillDetector::StoreMap::iterator SpillDetector::findCoveringStore(Addr addr) {
  // Only stores starting at most max_store_size - 1 bytes below addr can
  // contain it; among those that do, the newest owns the byte.
  auto best = store_map.end();
  const Addr span = max_store_size - 1;
  const Addr lowest = addr >= span ? addr - span : 0;
  for (auto it = store_map.lower_bound(lowest);
       it != store_map.end() && it->first <= addr; ++it) {
    if (addr < it->first + it->second.size &&
        (best == store_map.end() ||
         it->second.event_id > best->second.event_id))
      best = it;
  }
  return best;
}

void SpillDetector::eraseCoveredStores(Addr address, unsigned size) {
  const Addr end = address + std::max(size, 1u);
  for (auto it = store_map.lower_bound(address);
       it != store_map.end() && it->first < end;) {
    if (it->first + it->second.size <= end)
      it = store_map.erase(it);
    else
      ++it;
  }
}

// Emergency eviction, only runs when MAX_STORE_ENTRIES is exceeded.
// Drops the oldest half of the map (by instruction count) so the cost is
// amortized O(1) per store. Every dropped entry is a potential censored
// pair, so the count is surfaced in the ROI summary.
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

  log_file << "# Spill store->load log - " << ISA_NAME_STR
           << " (VERBOSE MODE)\n";
  log_file << "# Generated by gem5 SpillDetector\n";
  log_file << "# =================================\n";
  log_file << "#\n";
  log_file << "# Format: SPILL,store_pc,load_pc,memory_address,store_tick,"
              "load_tick,tick_diff,store_inst_count,load_inst_count\n";
  log_file << "#\n";
  log_file << "# Field Descriptions:\n";
  log_file << "#   store_pc        : PC (hex) of the stack store\n";
  log_file << "#   load_pc         : PC (hex) of the load that read it back\n";
  log_file << "#   memory_address  : Load address (hex)\n";
  log_file << "#   store_tick      : Simulation tick of the store\n";
  log_file << "#   load_tick       : Simulation tick of the load\n";
  log_file << "#   tick_diff       : load_tick - store_tick\n";
  log_file << "#   store_inst_count: Global instruction counter at store\n";
  log_file << "#   load_inst_count : Global instruction counter at load\n";
  log_file << "#\n";
  log_file << "# One line per spill load, repeats included, only inside "
              "ROIs.\n";
  log_file << "# Each ROI region ends with a compact summary block.\n";
  log_file << "# =================================\n\n";
}

// Called per spill load in verbose mode — writes one CSV SPILL line
void SpillDetector::writeSpillToLog(const SpillEvent &spill) {
  // Open and close per call so each line reaches the OS before the ROI
  // summary (verbose mode is meant for small tests and short windows).
  std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
  if (!log_file.is_open()) return;

  log_file << "SPILL,"
           << std::hex << spill.store_pc << ","
           << spill.load_pc << ","
           << spill.address << ","
           << std::dec << spill.store_tick << ","
           << spill.load_tick << ","
           << spill.tick_diff << ","
           << spill.store_inst_count << ","
           << spill.load_inst_count << "\n";
}

void SpillDetector::writeTally(std::ofstream &log_file, const char *prefix,
                               const CacheTally &t) const {
  const std::string p(prefix);
  log_file << "# " << p << "_l1_hits : " << t.l1_hits << "\n";
  log_file << "# " << p << "_l1_misses : " << t.l1_misses << "\n";
  log_file << "# " << p << "_l2_hits : " << t.l2_hits << "\n";
  log_file << "# " << p << "_l2_misses : " << t.l2_misses << "\n";
  log_file << "# " << p << "_split_insts : " << t.split_insts << "\n";
}

// Called at ROI end in both modes — writes the compact counter summary
void SpillDetector::writeROISummary(uint64_t workid) {
  std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
  if (!log_file.is_open()) return;

  log_file << "# ================================================\n";
  log_file << "# ROI SUMMARY  ISA=" << ISA_NAME_STR
           << "  workid=" << workid
           << "  sequence=" << roi_sequence << "\n";
  if (verbose) {
    log_file << "# (verbose mode - individual SPILL lines logged above)\n";
  } else {
    log_file << "# (summary mode - set spill_verbose=True for per-reload "
                "lines)\n";
  }
  log_file << "# ------------------------------------------------\n";
  log_file << "# metric_schema      : " << METRIC_SCHEMA << "\n";
  log_file << "# detection          : runtime effective address only\n";
  log_file << "# reload_match       : load address in [store address, "
              "store address + store size) of the newest store covering "
              "it\n";
  log_file << "# store_tracking     : from_roi_begin\n";
  log_file << "#\n";
  log_file << "# DEFINITIONS (total_ = whole simulation, roi_ = inside the\n";
  log_file << "# ROI, diag_ = technical diagnostic)\n";
  log_file << "#   roi_spill_store : stores inside the ROI to the process stack\n";
  log_file << "#                     (the store conditions of a spill), read\n";
  log_file << "#                     back or not\n";
  log_file << "#   roi_spill_event : distinct spill stores read back at least\n";
  log_file << "#                     once inside the ROI (one event per store,\n";
  log_file << "#                     at its first reload)\n";
  log_file << "#   roi_spill_load  : loads inside the ROI whose start address\n";
  log_file << "#                     lies in the bytes [address, address + size)\n";
  log_file << "#                     of the spill store that last wrote them;\n";
  log_file << "#                     repeats included\n";
  log_file << "#   Operational definition, not necessarily compiler spill code.\n";
  log_file << "#   Stores before the ROI (a SimPoint warmup included) are not\n";
  log_file << "#   tracked. LR/SC and AMOs are out of scope. Cache fields count\n";
  log_file << "#   L1D/L2 accesses: a cross-line instruction (*_split_insts) is\n";
  log_file << "#   two. roi_spill_event_* is the store side of each event: the\n";
  log_file << "#   store's own outcome when it executed, added at its first\n";
  log_file << "#   reload.\n";
  log_file << "#\n";
  log_file << "# ---- ROI counters ----\n";
  log_file << "# roi_total_insts    : " << roi_instructions << "\n";
  log_file << "# roi_load           : " << roi_load_insts << "\n";
  log_file << "# roi_store          : " << roi_store_insts << "\n";
  log_file << "# roi_spill_store    : " << roi_spill_store << "\n";
  log_file << "# roi_spill_event    : " << roi_spill_event << "\n";
  log_file << "# roi_spill_load     : " << roi_spill_load << "\n";
  log_file << "# ---- ROI cache outcomes ----\n";
  writeTally(log_file, "roi_spill_store", spill_store_cache);
  writeTally(log_file, "roi_spill_event", spill_event_cache);
  writeTally(log_file, "roi_spill_load", spill_load_cache);
  log_file << "# ---- technical diagnostics ----\n";
  log_file << "# diag_store_map_evicted : " << evicted_stores
           << "   (store-table entries dropped at the size cap; non-zero "
              "means censored pairs)\n";
  if (track_stack_release) {
    log_file << "# diag_load_after_stack_release : " << loads_after_release
             << "   (spill loads of bytes that lay below sp after their "
                "store: released stack, suspicious pairs)\n";
    log_file << "# diag_event_after_stack_release : "
             << events_after_release
             << "   (spill events whose first spill load is such a load)\n";
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
  log_file << "# metric_schema      : " << METRIC_SCHEMA << "\n";
  log_file << "# ---- global counters (whole simulation) ----\n";
  log_file << "# total_insts        : " << total_instructions << "\n";
  log_file << "# total_load         : " << total_load_insts << "\n";
  log_file << "# total_store        : " << total_store_insts << "\n";
  log_file << "# ================================================\n\n";
}

// -------------------------------------------------------------------------
// ROI entry / exit
// -------------------------------------------------------------------------
void SpillDetector::resetRoiCounters() {
  roi_store_insts = 0;
  roi_load_insts = 0;
  roi_instructions = 0;
  roi_spill_store = 0;
  roi_spill_event = 0;
  roi_spill_load = 0;
  spill_store_cache = CacheTally();
  spill_event_cache = CacheTally();
  spill_load_cache = CacheTally();
  roi_start_tick = 0;
  evicted_stores = 0;
  loads_after_release = 0;
  events_after_release = 0;
}

void SpillDetector::enterROI(uint64_t workid, bool at_marker) {
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
  inside_roi        = !at_marker;
  roi_start_pending = at_marker;
  current_roi_id    = workid;
  roi_sequence++;

  resetRoiCounters();
  store_map.clear();
  pending_access.clear();
  sp_known = false;

  if (verbose) {
    std::ofstream log_file(simout.resolve(SPILL_LOG_FILENAME), std::ios::app);
    if (log_file.is_open()) {
      log_file << "# ========================================\n";
      log_file << "# ROI_BEGIN  workid=" << workid << "\n";
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

  DPRINTF(SpillDetector, "Exited ROI (workid=%d), roi_spill_event=%d\n",
          workid, roi_spill_event);
}

// -------------------------------------------------------------------------
// Misc
// -------------------------------------------------------------------------
void SpillDetector::reset() {
  store_map.clear();
  pending_access.clear();
  next_store_event_id = 1;
  total_instructions = 0;
  total_store_insts = 0;
  total_load_insts = 0;
  roi_active = false;
  inside_roi = false;
  roi_start_pending = false;
  current_roi_id = 0;
  roi_sequence = 0;
  resetRoiCounters();
  log_initialized = false;
  global_summary_written = false;
  // verbose is configuration, set once at init.
}

void SpillDetector::finalize() {
  writeGlobalSummary();
}

} // namespace gem5
