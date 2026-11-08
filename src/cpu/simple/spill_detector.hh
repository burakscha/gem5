/*
 * Copyright (c) 2025 CAST Research
 * All rights reserved.
 *
 * Runtime register-spill detection for gem5 (register spill study)
 *
 * A spill is detected from effective addresses alone (metric schema 10): no
 * compiler information and no base-register test takes part. Output names:
 * total_ = whole simulation, roi_ = inside the ROI, diag_ = diagnostic.
 *
 *   roi_spill_store  stores that meet the store conditions of a spill:
 *                    inside the ROI, to the process stack region, not an
 *                    atomic operation, no fault. Read back or not.
 *   roi_spill_load   later loads inside the ROI whose start address lies in
 *                    the bytes [address, address + size) of the spill store
 *                    that last wrote that byte; after a partial overwrite
 *                    the newest store owns the overlapped bytes. The widths
 *                    may differ. Repeats count.
 *   roi_spill_event  distinct spill stores read back by at least one spill
 *                    load: one event per store, at its first reload. A
 *                    store read back n times is one spill event and n
 *                    spill loads.
 *
 * Stores before the ROI are not tracked, so a reload of one does not pair.
 * In a SimPoint run the ROI is the simulated interval: stores of the warmup
 * do not pair either.
 *
 * Atomic memory operations (LR/SC, AMO) are out of scope: they are never
 * stack stores or spill loads. A successful SC or an AMO still owns the bytes
 * it wrote, so a later load is not paired through it with an older store; a
 * failed SC wrote nothing and changes nothing.
 *
 * Cache outcomes: TimingSimpleCPU tags every spill store and every spill load
 * so BaseCache counts their L1D/L2 hits and misses. Whether a store starts a
 * spill event is known only at its first reload, so each store keeps its own
 * cache outcome in the store table, and the spill-event tally adds it then,
 * once per store (roi_spill_event_*: the store side of each event).
 *
 * Stack-release diagnostic (optional, spill_track_stack_release): a store
 * stays in the table until a newer store overwrites it, also after its
 * frame is popped. The detector watches sp at every committed ROI
 * instruction; a spill load whose byte lay below sp at some point after its
 * store (the stack there was released) is counted in
 * diag_load_after_stack_release, a suspicious pair, not necessarily a wrong
 * one. sp never decides whether an access is a spill.
 *
 * VERBOSITY FLAG
 * ==============
 * spill_verbose (default: false)
 *   false -> summary-only mode: counters are updated in RAM;
 *            a compact block is written to the log file only at ROI end.
 *   true  -> verbose mode: every spill load inside the ROI is written to the
 *            log file immediately, followed by a summary block.
 *            WARNING: can produce tens of GB for long workloads.
 *
 * Set via gem5 Python parameter:
 *   system.cpu.spill_verbose = True
 * or from se.py with --param:
 *   --param 'system.cpu[0].spill_verbose=True'
 */

#ifndef __CPU_SIMPLE_SPILL_DETECTOR_HH__
#define __CPU_SIMPLE_SPILL_DETECTOR_HH__

#include "base/types.hh"
#include <cstdint>
#include <fstream>
#include <map>
#include <string>

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
    uint64_t event_id;
    Addr address;
    Addr pc;
    Tick tick;
    unsigned size;
    uint64_t instruction_count;
    // Set on the first spill load. A value can be read back many times
    // (e.g. inside a loop); the event is counted once, every reload in
    // spill_load.
    bool reloaded;
    // Written by an SC or AMO: owns its bytes, never read back as a spill.
    bool atomic;
    // Highest sp seen since the store while sp lay above some of its bytes
    // (0: none): those bytes were released. Diagnostic only.
    Addr max_sp;
    // The store's own cache outcome, added to the spill-event tally at its
    // first reload. l1_fragments is normally one; two when TimingSimpleCPU
    // splits a cross-line access.
    unsigned l1_fragments;
    unsigned l1_hits;
    unsigned l1_misses;
    unsigned l2_hits;
    unsigned l2_misses;

    StoreInfo()
        : event_id(0), address(0), pc(0), tick(0), size(0),
          instruction_count(0), reloaded(false), atomic(false), max_sp(0),
          l1_fragments(1), l1_hits(0),
          l1_misses(0), l2_hits(0), l2_misses(0) {}
  };

  // -------------------------------------------------------
  // Per-reload event (used only in verbose mode)
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
  // AtomicWrite: a store-conditional or an AMO, see onAtomicWrite().
  enum class PendingType : uint8_t { None, Load, Store, AtomicWrite };

  // Cache outcome of a group of instructions' accesses.
  struct CacheTally {
    uint64_t insts = 0;
    uint64_t l1_hits = 0;
    uint64_t l1_misses = 0;
    uint64_t l2_hits = 0;
    uint64_t l2_misses = 0;
    // Instructions split over two cache lines; each adds one access (an
    // access splits into at most two).
    uint64_t split_insts = 0;

    void add(unsigned fragments, unsigned level1_hits, unsigned level1_misses,
             unsigned level2_hits, unsigned level2_misses);
  };

  // TimingSimpleCPU asks for the tag before translation, but counters and
  // map state are committed only after the instruction completes
  // successfully. This prevents translation faults from being counted as
  // retired loads/stores or spill pairs.
  struct PendingAccess {
    PendingType type;
    Addr address;
    Addr pc;
    Tick issue_tick;
    unsigned size;
    bool stack_address;
    // Tagged at issue time: a stack store tracked by the map, or a load that
    // reads one back.
    bool tagged;
    uint64_t matched_store_id;
    // store_map key (start address) of the store a load reads back; the
    // load's own address may lie anywhere inside that store's bytes.
    Addr matched_store_addr;
    unsigned l1_fragments;
    unsigned l1_hits;
    unsigned l1_misses;
    unsigned l2_hits;
    unsigned l2_misses;

    PendingAccess()
        : type(PendingType::None), address(0), pc(0), issue_tick(0), size(0),
          stack_address(false), tagged(false), matched_store_id(0),
          matched_store_addr(0), l1_fragments(1), l1_hits(0), l1_misses(0),
          l2_hits(0), l2_misses(0) {}

    void clear() { *this = PendingAccess(); }
  };

  // start address -> StoreInfo, ordered so that the store covering any byte
  // can be found (core detection structure). An entry owns the bytes
  // [address, address + size) until a newer store overwrites them.
  using StoreMap = std::map<Addr, StoreInfo>;
  StoreMap store_map;
  // Widest stack store recorded; bounds the lookup window of a load.
  unsigned max_store_size;
  PendingAccess pending_access;
  uint64_t next_store_event_id;

  // Whole-simulation committed dynamic instruction counters.
  uint64_t total_instructions;
  uint64_t total_store_insts;
  uint64_t total_load_insts;

  // =========================================
  // ROI tracking
  // =========================================
  bool roi_active;
  bool inside_roi;
  // enterROI() is invoked while the m5_work_begin pseudo instruction is
  // executing. Activation is delayed until that marker commits so the marker
  // itself is excluded from ROI instruction counts.
  bool roi_start_pending;
  uint64_t current_roi_id;
  uint64_t roi_sequence;
  bool log_initialized;

  uint64_t roi_store_insts;
  uint64_t roi_load_insts;
  uint64_t roi_instructions;
  uint64_t roi_spill_store;   // every store meeting the store conditions
  uint64_t roi_spill_event;   // stack stores read back at least once
  uint64_t roi_spill_load;    // every spill load, repeats included
  CacheTally spill_store_cache;
  CacheTally spill_event_cache;  // each read-back store's own outcome, once
  CacheTally spill_load_cache;
  Tick     roi_start_tick;

  // =========================================
  // Verbosity flag
  // =========================================
  bool verbose; // set by TimingSimpleCPU from params.spill_verbose

  // Store-table entries dropped by emergency eviction inside the ROI.
  uint64_t evicted_stores;

  // Stack-release diagnostic (see the file comment).
  bool track_stack_release = true;
  bool sp_known = false;
  Addr last_sp = 0;
  uint64_t loads_after_release;         // diag_load_after_stack_release
  uint64_t events_after_release;        // diag_event_after_stack_release
  void noteStackPointer(Addr sp);

  // Store-map safety cap. There is intentionally NO time window: a reload is
  // valid no matter how far it is from its store. If the map ever exceeds
  // this cap, the oldest half is evicted and the eviction count appears in
  // the ROI summary so any censoring is visible in the data.
  static const size_t MAX_STORE_ENTRIES = 1 << 20; // ~1M entries

  // -------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------
  // Enters a committed stack store, or an atomic write, into the map.
  void recordStore(const PendingAccess &p);
  void evictOldStores();
  // The most recent store whose bytes contain addr, or store_map.end().
  StoreMap::iterator findCoveringStore(Addr addr);
  // Drops the entries whose every byte [address, address + size) overwrites.
  void eraseCoveredStores(Addr address, unsigned size);
  void resetRoiCounters();
  void writeLogHeader();
  void writeSpillToLog(const SpillEvent &spill);
  void writeROISummary(uint64_t workid);
  void writeTally(std::ofstream &log_file, const char *prefix,
                  const CacheTally &t) const;
  void writeGlobalSummary();
  bool global_summary_written;

public:
  SpillDetector();
  ~SpillDetector();

  // -------------------------------------------------------
  // Configuration — called by TimingSimpleCPU constructor
  // -------------------------------------------------------
  void setVerbose(bool v);
  bool isVerbose() const { return verbose; }
  void setTrackStackRelease(bool on) { track_stack_release = on; }
  // Whether the next commit needs sp (the stack-release diagnostic).
  bool wantsStackPointer() const { return track_stack_release && inside_roi; }

  // -------------------------------------------------------
  // Hot-path callbacks (called per instruction)
  // -------------------------------------------------------
  // Stage a store before it is issued. True when it is a stack store the
  // map tracks; the caller then tags the request STACK_STORE.
  bool onStoreInstruction(Addr address, Addr pc, Tick tick, unsigned size,
                          unsigned l1_fragments, ThreadContext *tc = nullptr);

  // Stage a load before it is issued. True when it reads back a tracked
  // stack store; the caller then tags the request SPILL_LOAD.
  bool onLoadInstruction(Addr address, Addr pc, Tick tick, unsigned size,
                         unsigned l1_fragments, ThreadContext *tc = nullptr);

  // Stage a store-conditional or an AMO. Never tagged or counted; once it
  // commits, it owns the bytes it wrote. The caller discards a failed SC.
  void onAtomicWrite(Addr address, Addr pc, Tick tick, unsigned size,
                     ThreadContext *tc = nullptr);

  // Commit or discard the staged memory access. Called once per
  // successfully completed instruction, or on a fault respectively. sp is
  // the stack pointer after the instruction, read only when
  // wantsStackPointer() (else 0).
  void onInstructionCommit(bool is_load, bool is_store, Addr pc, Tick tick,
                           Addr sp = 0);
  // Records one fragment's cache traversal before its response packet is
  // destroyed. Level 0 is L1D and level 1 is L2.
  void recordPendingCacheOutcome(unsigned level, bool hit);
  void discardPendingInstruction();

  // Whether a load at address and load_tick reads back store_info: after
  // the store, on the stack (findCoveringStore() checked the address range).
  bool isReload(const StoreInfo &store_info, Addr address, Tick load_tick,
                ThreadContext *tc);

  // Returns true if address falls within the process stack region (SE mode).
  bool isStackAddress(Addr address, ThreadContext *tc);

  // -------------------------------------------------------
  // Accessors
  // -------------------------------------------------------
  uint64_t getTotalInstructions() const { return total_instructions; }
  uint64_t getTotalStores()       const { return total_store_insts; }
  uint64_t getTotalLoads()        const { return total_load_insts; }

  void reset();

  // -------------------------------------------------------
  // ROI control (called from pseudo_inst.cc, or from Python for a SimPoint
  // interval)
  // -------------------------------------------------------
  // at_marker: called while the m5_work_begin marker executes, which must
  // stay out of the ROI. Python opens a SimPoint interval between two
  // instructions instead, so the ROI starts with the next instruction.
  void enterROI(uint64_t workid, bool at_marker = true);
  void exitROI(uint64_t workid);
  void finalize();

  bool     isInsideROI()        const { return inside_roi; }
  uint64_t getROIStores()       const { return roi_store_insts; }
  uint64_t getROILoads()        const { return roi_load_insts; }
  uint64_t getROIInstructions() const { return roi_instructions; }
};

} // namespace gem5

#endif // __CPU_SIMPLE_SPILL_DETECTOR_HH__
