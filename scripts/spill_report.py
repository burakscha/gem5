#!/usr/bin/env python3
"""Collect spill and cache metrics for every SPEC run and report them.

Reads two files per gem5 output directory:

  riscv_spill_stats.txt  ROI summary blocks written by SpillDetector. Already
                         ROI-scoped. Schema 10: stack stores, spill events
                         (stack stores read back) and spill loads, found from
                         addresses alone. Schema 9 (older results): the spill,
                         csave and other_stack classes; stack_* is their sum.
  stats.txt              gem5 statistics. Since workbegin/workend dump AND
                         reset the statistics, the ROI occupies its own
                         block(s), which is what the cache hit/miss numbers
                         below are taken from.

Produces an aligned terminal table, a CSV, a one-page LaTeX source and (when a
LaTeX engine is available) the compiled PDF.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SCHEMA = 10
SIMPOINT = False   # --simpoint: the runs are SimPoint estimates
# Schema 9: ROI summary field prefix, gem5 cache statistic prefix, label.
CLASSES = (("spill", "spill", "sp"), ("csave", "csave", "cs"),
           ("other_stack", "stackOther", "ot"))
# Schema 10: populations with a cache tally, and the gem5 statistic counting
# the same accesses (None: the detector alone knows which stores were read
# back).
# Canonical ROI counter prefixes with a cache tally, and the gem5 statistic
# counting the same accesses (None: detector only).
POPULATIONS = (("roi_spill_store", "stackStore"), ("roi_spill_event", None),
               ("roi_spill_load", "spillLoad"))

ROI_HEADER = re.compile(r"^# ROI SUMMARY")
GLOBAL_HEADER = re.compile(r"^# GLOBAL SUMMARY")
INT_FIELD = re.compile(r"^#\s+([A-Za-z0-9_\[\] ]+?)\s*:\s*([0-9]+)\s*(?:\(|$)")
CLASSIFICATION = re.compile(r"^#\s+classification\s*:\s*(\S+)")
STATS_BLOCK = re.compile(r"^-+\s*Begin Simulation Statistics")
STAT_LINE = re.compile(r"^(\S+)\s+([-+0-9.eEinf]+)(?:\s|$)")


class ReportError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def parse_spill_log(path: Path) -> tuple[list[dict[str, int]], dict[str, int], str]:
    """Return (roi blocks, global block, classification)."""
    rois: list[dict[str, int]] = []
    global_block: dict[str, int] = {}
    classification = "unknown"
    current: dict[str, int] | None = None
    for line in path.read_text().splitlines():
        if ROI_HEADER.match(line):
            current = {}
            rois.append(current)
            continue
        if GLOBAL_HEADER.match(line):
            current = global_block
            continue
        match = CLASSIFICATION.match(line)
        if match:
            classification = match.group(1)
            continue
        field_match = INT_FIELD.match(line)
        if current is not None and field_match:
            key = field_match.group(1).strip()
            if "reuse_log2" in key:
                continue
            current[key] = int(field_match.group(2))
    for roi in rois:
        canonical_roi(roi)
    return rois, global_block, classification


_TALLY = ("l1_hits", "l1_misses", "l2_hits", "l2_misses", "split_insts")


def canonical_roi(roi: dict[str, int]) -> None:
    """Schema-10 summaries of 2026-11-05..08 (they have roi_stack_store) under
    the current names: their roi_stack_store are the spill stores, their spill
    events are roi_spill_event (11-08) or roi_spill_store (11-05..07). Same
    rule as cache_scripts/cache_status.canonical()."""
    if "roi_stack_store" not in roi:
        return
    events = "roi_spill_event" if "roi_spill_event" in roi else "roi_spill_store"
    renamed = {"roi_spill_store": roi["roi_stack_store"], "roi_spill_event": roi[events]}
    for f in _TALLY:
        renamed[f"roi_spill_store_{f}"] = roi.get(f"roi_stack_store_{f}", 0)
        renamed[f"roi_spill_event_{f}"] = roi.get(f"{events}_{f}", 0)
    if "diag_store_first_reload_after_stack_release" in roi:
        renamed["diag_event_after_stack_release"] = roi[
            "diag_store_first_reload_after_stack_release"]
    for k in [k for k in roi if k.startswith("roi_stack_store")]:
        del roi[k]
    roi.update(renamed)


def parse_stats_blocks(path: Path) -> list[dict[str, float]]:
    """Split stats.txt into its dump blocks, newest last."""
    blocks: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in path.read_text().splitlines():
        if STATS_BLOCK.match(line):
            current = {}
            blocks.append(current)
            continue
        if current is None:
            continue
        match = STAT_LINE.match(line)
        if not match:
            continue
        try:
            current[match.group(1)] = float(match.group(2))
        except ValueError:
            pass
    return blocks


def roi_stats(blocks: list[dict[str, float]], roi_count: int) -> tuple[dict[str, float], str]:
    """Sum the statistics blocks that cover the ROIs.

    workbegin and workend each dump+reset, so the blocks alternate
    pre-ROI, ROI-1, gap, ROI-2, ..., post-ROI and the ROI blocks sit at the
    odd indices. A SimPoint run (and its combined estimate) holds two
    blocks, the warmup (or a placeholder) and the interval, which is its ROI.
    If the layout does not match (an older binary without the ROI dump
    hooks, or an aborted run) fall back to summing every block, which
    reproduces the whole-simulation totals, and say so.
    """
    if roi_count == 1 and len(blocks) == 2:
        return dict(blocks[1]), "roi"
    if roi_count > 0 and len(blocks) == 2 * roi_count + 1:
        merged: dict[str, float] = {}
        for index in range(1, 2 * roi_count, 2):
            for key, value in blocks[index].items():
                merged[key] = merged.get(key, 0.0) + value
        return merged, "roi"
    merged = {}
    for block in blocks:
        for key, value in block.items():
            merged[key] = merged.get(key, 0.0) + value
    return merged, "whole-run"


# --------------------------------------------------------------------------
# Metric assembly
# --------------------------------------------------------------------------
@dataclass
class Row:
    benchmark: str
    input_desc: str
    m5out: Path
    values: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def total(rois: list[dict[str, int]], key: str) -> int:
    return sum(roi.get(key, 0) for roi in rois)


def pct(numerator: float, denominator: float) -> float | None:
    return 100.0 * numerator / denominator if denominator else None


def cache_pair(stats: dict[str, float], unit: str) -> tuple[int, int]:
    hits = int(stats.get(f"{unit}.demandHits::total", 0))
    misses = int(stats.get(f"{unit}.demandMisses::total", 0))
    return hits, misses


def build_row(benchmark: str, input_desc: str, m5out: Path) -> Row:
    log = m5out / "riscv_spill_stats.txt"
    stats_file = m5out / "stats.txt"
    if not log.is_file():
        raise ReportError(f"{benchmark}: missing {log.name}")
    if not stats_file.is_file():
        raise ReportError(f"{benchmark}: missing {stats_file.name}")

    rois, global_block, classification = parse_spill_log(log)
    if not rois:
        raise ReportError(f"{benchmark}: no ROI summary in {log.name}")
    schemas = {roi.get("metric_schema") for roi in rois}
    if schemas != {SCHEMA}:
        raise ReportError(
            f"{benchmark}: metric_schema {sorted(s for s in schemas if s)} "
            f"(expected {SCHEMA}) — rerun with the current gem5 build"
        )

    stats, scope = roi_stats(parse_stats_blocks(stats_file), len(rois))
    row = Row(benchmark, input_desc, m5out)
    if scope != "roi":
        row.warnings.append("cache stats are whole-run, not ROI-scoped")

    instructions = total(rois, "roi_total_insts")
    l1d_hits, l1d_misses = cache_pair(stats, "system.cpu.dcache")
    l1i_hits, l1i_misses = cache_pair(stats, "system.cpu.icache")
    l2_hits, l2_misses = cache_pair(stats, "system.l2")

    # gem5's own instruction counters. They are ROI-scoped too, because
    # workbegin/workend dump+reset the statistics, so they are an independent
    # check on the detector's ROI counters rather than a different window.
    gem5_roi_ops = int(stats.get("simOps", 0))
    gem5_roi_loads = int(stats.get("system.cpu.commitStats0.numLoadInsts", 0))
    gem5_roi_stores = int(stats.get("system.cpu.commitStats0.numStoreInsts", 0))

    values: dict[str, object] = {
        "benchmark": benchmark,
        "input": input_desc,
        "classification": classification,
        "cache_stat_scope": scope,
        "roi_count": len(rois),
        # --- tier 1: global, whole simulation ---
        "total_insts": global_block.get("total_insts", 0),
        "total_load": global_block.get("total_load", 0),
        "total_store": global_block.get("total_store", 0),
        # --- tier 2: ROI ---
        "roi_total_insts": instructions,
        "roi_load": total(rois, "roi_load"),
        "roi_store": total(rois, "roi_store"),
        # gem5's native ROI counters, for cross-validation. numStoreInsts
        # counts isStore() OR isAtomic(), while the detector counts only
        # isStore(), so the store delta is the ROI's atomic instructions.
        "gem5_roi_ops": gem5_roi_ops,
        "gem5_roi_load": gem5_roi_loads,
        "gem5_roi_store": gem5_roi_stores,
        "delta_roi_insts": gem5_roi_ops - instructions,
        "delta_roi_load": gem5_roi_loads - total(rois, "roi_load"),
        "delta_roi_store": gem5_roi_stores - total(rois, "roi_store"),
        # --- overall cache behaviour over the same window ---
        "l1d_hits": l1d_hits,
        "l1d_misses": l1d_misses,
        "l1d_accesses": l1d_hits + l1d_misses,
        "l1d_miss_pct": pct(l1d_misses, l1d_hits + l1d_misses),
        "l1i_hits": l1i_hits,
        "l1i_misses": l1i_misses,
        "l1i_miss_pct": pct(l1i_misses, l1i_hits + l1i_misses),
        "l2_hits": l2_hits,
        "l2_misses": l2_misses,
        "l2_miss_pct": pct(l2_misses, l2_hits + l2_misses),
    }

    if SCHEMA >= 10:
        add_spill_metrics(row, values, rois, stats, scope)
    else:
        add_class_metrics(row, values, rois, stats, scope, classification)
    if values["diag_store_map_evicted"]:
        row.warnings.append("store map overflowed; some pairs were censored")
    return row


def add_class_metrics(row: Row, values: dict[str, object], rois: list[dict[str, int]],
                      stats: dict[str, float], scope: str, classification: str) -> None:
    """Schema 9: the spill / csave / other_stack classes and their sum."""
    instructions = values["roi_total_insts"]
    # --- tier 3: stack store/reload traffic, all classes, then per class ---
    stack_event = total(rois, "stack_event")
    for prefix in ("stack", *(c[0] for c in CLASSES)):
        store = total(rois, f"{prefix}_store")
        load = total(rois, f"{prefix}_load")
        event = total(rois, f"{prefix}_event")
        values.update({
            f"{prefix}_store": store,
            f"{prefix}_load": load,
            f"total_{prefix}_insts": store + load,
            f"{prefix}_event": event,
            f"repeat_{prefix}_load": total(rois, f"repeat_{prefix}_load"),
            f"{prefix}_store_unpaired": total(rois, f"{prefix}_store_unpaired"),
            f"{prefix}_inst_pct": pct(store + load, instructions),
            f"{prefix}_event_pct": pct(event, instructions),
        })
        if prefix != "stack":
            values[f"{prefix}_share_pct"] = pct(event, stack_event)
        for side in ("store", "load"):
            hits = total(rois, f"{prefix}_{side}_l1_hits")
            misses = total(rois, f"{prefix}_{side}_l1_misses")
            values.update({
                f"{prefix}_{side}_l1_hits": hits,
                f"{prefix}_{side}_l1_misses": misses,
                f"{prefix}_{side}_l1_miss_pct": pct(misses, hits + misses),
                f"{prefix}_{side}_l2_hits":
                    total(rois, f"{prefix}_{side}_l2_hits"),
                f"{prefix}_{side}_l2_misses":
                    total(rois, f"{prefix}_{side}_l2_misses"),
            })
            # The counters exist so these identities can be checked rather
            # than assumed; a silent capture failure would look like data.
            check_identity(row, f"{prefix}_{side} L1 accesses", hits + misses,
                           total(rois, f"{prefix}_{side}_l1_accesses"))
        check_identity(row, f"{prefix}_store_unpaired",
                       values[f"{prefix}_store_unpaired"], store - event)

    # --- diagnostics, reported but never mixed into the headline ---
    for key in ("diag_nonspill_reuse", "diag_spill_reload_unmapped",
                "diag_spill_load_pc_other_store", "diag_store_map_evicted"):
        values[key] = total(rois, key)

    if classification != "compiler_pc_map":
        row.warnings.append("no stack_pc_map: spill and csave not measured, "
                            "every pair is other_stack")
    for key in ("diag_spill_reload_unmapped", "diag_spill_load_pc_other_store"):
        if values[key]:
            row.warnings.append(f"{key} = {values[key]} (expected about 0: reloads of "
                                f"stores before the ROI, or a stale map)")
    if scope == "roi":
        # Each class's request flags mark exactly that class's population.
        for prefix, stat_prefix, _ in CLASSES:
            for side, Side in (("load", "Load"), ("store", "Store")):
                for outcome, Outcome in (("hits", "Hits"), ("misses", "Misses")):
                    for level, unit in (("l1", "system.cpu.dcache"),
                                        ("l2", "system.l2")):
                        check_identity(
                            row, f"{unit}.{stat_prefix}{Side}{Outcome}",
                            values[f"{prefix}_{side}_{level}_{outcome}"],
                            int(stats.get(f"{unit}.{stat_prefix}{Side}{Outcome}",
                                          -1)))
    row.values = values


def add_spill_metrics(row: Row, values: dict[str, object], rois: list[dict[str, int]],
                      stats: dict[str, float], scope: str) -> None:
    """Schema 10, canonical names: roi_spill_store (the stores meeting the
    store conditions of a spill, read back or not), roi_spill_event (those
    read back, one per store), roi_spill_load and their L1D/L2 outcomes,
    read from the detector; the unread spill stores, the other stores and
    every ratio, computed here."""
    loads, stores = values["roi_load"], values["roi_store"]
    spill_store = total(rois, "roi_spill_store")
    spill_event = total(rois, "roi_spill_event")
    spill_load = total(rois, "roi_spill_load")
    values.update({
        "roi_spill_store": spill_store,
        "roi_spill_event": spill_event,
        "roi_spill_load": spill_load,
        "roi_unread_spill_store": spill_store - spill_event,
        "roi_other_store": stores - spill_store,
        "spill_load_pct": pct(spill_load, loads),
        "spill_store_pct": pct(spill_store, stores),
        "spill_event_pct": pct(spill_event, stores),
        "spill_event_of_spill_store_pct": pct(spill_event, spill_store),
        "spill_mem_pct": pct(spill_store + spill_load, loads + stores),
        "spill_inst_pct": pct(spill_store + spill_load, values["roi_total_insts"]),
    })
    for population, stat_prefix in POPULATIONS:
        hits = total(rois, f"{population}_l1_hits")
        misses = total(rois, f"{population}_l1_misses")
        hits2 = total(rois, f"{population}_l2_hits")
        misses2 = total(rois, f"{population}_l2_misses")
        values.update({
            f"{population}_l1_hits": hits,
            f"{population}_l1_misses": misses,
            f"{population}_l1_accesses": hits + misses,
            f"{population}_l1_miss_pct": pct(misses, hits + misses),
            f"{population}_l2_hits": hits2,
            f"{population}_l2_misses": misses2,
            f"{population}_l2_accesses": hits2 + misses2,
            f"{population}_l2_miss_pct": pct(misses2, hits2 + misses2),
        })
        check_identity(row, f"{population} L2 accesses == L1 misses", hits2 + misses2, misses)
        if scope == "roi" and stat_prefix:
            for outcome, Outcome in (("hits", "Hits"), ("misses", "Misses")):
                for level, unit in (("l1", "system.cpu.dcache"), ("l2", "system.l2")):
                    name = f"{unit}.{stat_prefix}{Outcome}"
                    check_identity(row, name, values[f"{population}_{level}_{outcome}"],
                                   int(stats.get(name, -1)))
    # Spill stores never read back: the difference of the two tallies; other
    # stores: gem5's L1D write requests minus the spill stores (only with the
    # ROI's own statistics block; no L2 rate: gem5's L2 counts store misses
    # together with AMO/SC and upgrade requests).
    for level in ("l1", "l2"):
        un_misses = (values[f"roi_spill_store_{level}_misses"]
                     - values[f"roi_spill_event_{level}_misses"])
        un_accesses = (values[f"roi_spill_store_{level}_accesses"]
                       - values[f"roi_spill_event_{level}_accesses"])
        values[f"roi_unread_spill_store_{level}_misses"] = un_misses
        values[f"roi_unread_spill_store_{level}_accesses"] = un_accesses
        values[f"roi_unread_spill_store_{level}_miss_pct"] = pct(un_misses, un_accesses)
    other_misses = other_accesses = None
    if scope == "roi":
        other_misses = (int(stats.get("system.cpu.dcache.WriteReq.misses::total", 0))
                        - values["roi_spill_store_l1_misses"])
        other_accesses = (int(stats.get("system.cpu.dcache.WriteReq.accesses::total", 0))
                          - values["roi_spill_store_l1_accesses"])
    values["roi_other_store_l1_misses"] = other_misses
    values["roi_other_store_l1_accesses"] = other_accesses
    values["roi_other_store_l1_miss_pct"] = (pct(other_misses, other_accesses)
                                            if scope == "roi" else None)
    values["diag_store_map_evicted"] = total(rois, "diag_store_map_evicted")
    # Stack-release diagnostic (absent when spill_track_stack_release is off).
    if any("diag_load_after_stack_release" in r for r in rois):
        released = total(rois, "diag_load_after_stack_release")
        values["diag_load_after_stack_release"] = released
        values["diag_event_after_stack_release"] = total(
            rois, "diag_event_after_stack_release")
        values["load_after_stack_release_pct"] = pct(released, spill_load)
    row.values = values


def check_identity(row: Row, label: str, left: int, right: int) -> None:
    if left != right:
        row.warnings.append(f"{label}: {left} != {right}")


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def discover(root: Path, profile: str, cache: str) -> tuple[list[tuple[str, str, Path]], list[str]]:
    """Find the latest completed run of every benchmark for profile/cache.

    Runs live in benchmarks/<bench>/m5out_<bench>/, all profiles and caches
    side by side, with one latest_<profile>_<cache>_<run_id> symlink per
    combination.
    """
    found: list[tuple[str, str, Path]] = []
    skipped: list[str] = []
    base = root / "benchmarks"
    if not base.is_dir():
        return found, skipped
    for bench_dir in sorted(base.iterdir()):
        run_root = bench_dir / f"m5out_{bench_dir.name}"
        if not run_root.is_dir():
            continue
        prefix = f"latest_{profile}_{cache}_"
        for link in sorted(run_root.glob(f"{prefix}*")):
            run_id = link.name[len(prefix):]
            resolved = link.resolve()
            status_file = resolved / ".runner" / "status"
            status = status_file.read_text().strip() if status_file.is_file() else "UNKNOWN"
            if status != "COMPLETED":
                skipped.append(f"{run_id}: {status}")
                continue
            found.append((run_id, describe_input(resolved), resolved))
    return found, skipped


def describe_input(m5out: Path) -> str:
    command = m5out / ".runner" / "command.sh"
    if not command.is_file():
        return ""
    for line in command.read_text().splitlines():
        if "--options" in line:
            match = re.search(r"--options[= ]'([^']*)'", line)
            if match:
                return " ".join(match.group(1).split())[:40]
    return ""


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
TABLE_COLUMNS_9 = [
    ("benchmark", "benchmark", "{}"),
    ("roi_total_insts", "ROI_insts", "{:,}"),
    ("stack_event", "stack_ev", "{:,}"),
    ("spill_event", "spill_ev", "{:,}"),
    ("csave_event", "csave_ev", "{:,}"),
    ("other_stack_event", "other_ev", "{:,}"),
    ("spill_share_pct", "spill/stack%", "{:.1f}"),
    ("spill_inst_pct", "spill%insts", "{:.2f}"),
    ("csave_inst_pct", "csave%insts", "{:.2f}"),
    ("l1d_miss_pct", "L1D miss%", "{:.3f}"),
    ("l2_miss_pct", "L2 miss%", "{:.2f}"),
    ("spill_load_l1_miss_pct", "sp_ld miss%", "{:.3f}"),
    ("spill_store_l1_miss_pct", "sp_st miss%", "{:.3f}"),
    ("csave_load_l1_miss_pct", "cs_ld miss%", "{:.3f}"),
    ("csave_store_l1_miss_pct", "cs_st miss%", "{:.3f}"),
    ("other_stack_load_l1_miss_pct", "ot_ld miss%", "{:.3f}"),
    ("delta_roi_store", "d_store(gem5)", "{:+,}"),
]
TABLE_COLUMNS_10 = [
    ("benchmark", "benchmark", "{}"),
    ("roi_total_insts", "roi_insts", "{:,}"),
    ("roi_spill_store", "spill_st", "{:,}"),
    ("roi_spill_event", "spill_ev", "{:,}"),
    ("roi_spill_load", "spill_ld", "{:,}"),
    ("spill_load_pct", "sp_ld%load", "{:.2f}"),
    ("spill_store_pct", "sp_st%st", "{:.2f}"),
    ("spill_event_pct", "sp_ev%st", "{:.2f}"),
    ("spill_event_of_spill_store_pct", "sp_ev%sp_st", "{:.1f}"),
    ("l1d_miss_pct", "L1D miss%", "{:.3f}"),
    ("l2_miss_pct", "L2 local%", "{:.2f}"),
    ("roi_spill_load_l1_miss_pct", "sp_ld L1%", "{:.3f}"),
    ("roi_spill_load_l2_miss_pct", "sp_ld L2loc%", "{:.2f}"),
    ("roi_spill_store_l1_miss_pct", "sp_st L1%", "{:.3f}"),
    ("roi_spill_event_l1_miss_pct", "sp_ev L1%", "{:.3f}"),
    ("roi_other_store_l1_miss_pct", "other_st L1%", "{:.3f}"),
    ("delta_roi_store", "d_store(gem5)", "{:+,}"),
]


def table_columns():
    return TABLE_COLUMNS_10 if SCHEMA >= 10 else TABLE_COLUMNS_9


def cell(value: object, spec: str) -> str:
    if value is None:
        return "n/a"
    try:
        return spec.format(value)
    except (ValueError, TypeError):
        return str(value)


def print_table(rows: list[Row]) -> None:
    columns = table_columns()
    header = [label for _, label, _ in columns]
    body = [[cell(row.values.get(key), spec) for key, _, spec in columns]
            for row in rows]
    widths = [max(len(header[i]), *(len(line[i]) for line in body)) if body
              else len(header[i]) for i in range(len(header))]
    sep = "  ".join("-" * w for w in widths)
    print("  ".join(h.rjust(w) for h, w in zip(header, widths)).replace(
        header[0].rjust(widths[0]), header[0].ljust(widths[0]), 1))
    print(sep)
    for line in body:
        cells = [line[0].ljust(widths[0])]
        cells += [line[i].rjust(widths[i]) for i in range(1, len(line))]
        print("  ".join(cells))


def write_csv(rows: list[Row], path: Path) -> None:
    fieldnames = list(rows[0].values)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.values)


def tex_escape(text: str) -> str:
    for char, replacement in (("\\", r"\textbackslash{}"), ("&", r"\&"),
                              ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                              ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                              ("~", r"\textasciitilde{}"),
                              ("^", r"\textasciicircum{}")):
        text = text.replace(char, replacement)
    return text


# key, header, format, how the Total row aggregates it:
#   "sum"  add the column up
#   (num, den, scale) recompute the ratio from the summed components
#   None   no meaningful total
LATEX_COLUMNS_9 = [
    ("benchmark", "Benchmark", "{}", None),
    ("roi_total_insts", r"ROI\_insts", "{:,}", "sum"),
    ("stack_event", r"stack\_event", "{:,}", "sum"),
    ("spill_event", r"\textbf{spill\_event}", "{:,}", "sum"),
    ("csave_event", r"csave\_event", "{:,}", "sum"),
    ("other_stack_event", r"other\_event", "{:,}", "sum"),
    ("spill_share_pct", r"spill/stack\,\%", "{:.1f}",
     ("spill_event", "stack_event", 100.0)),
    ("spill_inst_pct", r"Spill\,\%", "{:.2f}",
     ("total_spill_insts", "roi_total_insts", 100.0)),
    ("csave_inst_pct", r"Csave\,\%", "{:.2f}",
     ("total_csave_insts", "roi_total_insts", 100.0)),
    ("l1d_miss_pct", r"L1D m\,\%", "{:.3f}",
     ("l1d_misses", "l1d_accesses", 100.0)),
    ("l2_miss_pct", r"L2 m\,\%", "{:.2f}", None),
    ("spill_load_l1_miss_pct", r"sp\_load m\,\%", "{:.3f}", None),
    ("spill_store_l1_miss_pct", r"sp\_store m\,\%", "{:.3f}", None),
    ("csave_load_l1_miss_pct", r"cs\_load m\,\%", "{:.3f}", None),
    ("csave_store_l1_miss_pct", r"cs\_store m\,\%", "{:.3f}", None),
]
LATEX_COLUMNS_10 = [
    ("benchmark", "Benchmark", "{}", None),
    ("roi_total_insts", r"roi\_total\_insts", "{:,}", "sum"),
    ("roi_spill_store", r"\textbf{roi\_spill\_store}", "{:,}", "sum"),
    ("roi_spill_event", r"\textbf{roi\_spill\_event}", "{:,}", "sum"),
    ("roi_spill_load", r"roi\_spill\_load", "{:,}", "sum"),
    ("spill_load_pct", r"sp\_ld/load\,\%", "{:.2f}", ("roi_spill_load", "roi_load", 100.0)),
    ("spill_store_pct", r"sp\_st/st\,\%", "{:.2f}", ("roi_spill_store", "roi_store", 100.0)),
    ("spill_event_pct", r"sp\_ev/st\,\%", "{:.2f}", ("roi_spill_event", "roi_store", 100.0)),
    ("spill_event_of_spill_store_pct", r"sp\_ev/sp\_st\,\%", "{:.1f}",
     ("roi_spill_event", "roi_spill_store", 100.0)),
    ("l1d_miss_pct", r"L1D m\,\%", "{:.3f}", ("l1d_misses", "l1d_accesses", 100.0)),
    ("l2_miss_pct", r"L2 local m\,\%", "{:.2f}", None),
    ("roi_spill_load_l1_miss_pct", r"sp\_ld L1 m\,\%", "{:.3f}",
     ("roi_spill_load_l1_misses", "roi_spill_load_l1_accesses", 100.0)),
    ("roi_spill_load_l2_miss_pct", r"sp\_ld L2 local m\,\%", "{:.2f}",
     ("roi_spill_load_l2_misses", "roi_spill_load_l2_accesses", 100.0)),
    ("roi_spill_store_l1_miss_pct", r"sp\_st L1 m\,\%", "{:.3f}",
     ("roi_spill_store_l1_misses", "roi_spill_store_l1_accesses", 100.0)),
    ("roi_spill_event_l1_miss_pct", r"sp\_ev L1 m\,\%", "{:.3f}",
     ("roi_spill_event_l1_misses", "roi_spill_event_l1_accesses", 100.0)),
    ("roi_other_store_l1_miss_pct", r"other st L1 m\,\%", "{:.3f}",
     ("roi_other_store_l1_misses", "roi_other_store_l1_accesses", 100.0)),
]


def latex_columns():
    return LATEX_COLUMNS_10 if SCHEMA >= 10 else LATEX_COLUMNS_9


def build_latex(rows: list[Row], profile: str, cache: str, commit: str) -> str:
    def latex_int(value: object) -> str:
        return f"{int(value):,}".replace(",", r"\,")

    columns = latex_columns()
    header = " & ".join(label for _, label, _, _ in columns) + r" \\"
    lines = []
    for row in rows:
        cells = []
        for key, _, spec, _ in columns:
            value = row.values.get(key)
            if key == "benchmark":
                cells.append(tex_escape(str(value)))
            elif value is None:
                cells.append(r"\textemdash")
            elif spec.endswith("f}"):
                cells.append(cell(value, spec))
            else:
                cells.append(latex_int(value))
        lines.append(" & ".join(cells) + r" \\")
    body = "\n".join(lines)

    # Derived from the columns so the Total row can never drift out of sync
    # with the header when a column is added or moved.
    summed = {}
    for key, _, _, rule in columns:
        parts = [key] if rule == "sum" else list(rule[:2]) if isinstance(rule, tuple) else []
        for part in parts:
            summed[part] = sum(int(row.values.get(part) or 0) for row in rows)

    total_cells = []
    for key, _, spec, rule in columns:
        if key == "benchmark":
            total_cells.append(r"\textbf{Total}")
        elif rule == "sum":
            text = latex_int(summed[key])
            total_cells.append(r"\textbf{" + text + "}"
                               if key in ("spill_event", "roi_spill_store", "roi_spill_event")
                               else text)
        elif isinstance(rule, tuple):
            num, den, scale = rule
            denominator = summed.get(den, 0)
            total_cells.append(cell(scale * summed.get(num, 0) / denominator, spec)
                               if denominator else r"\textemdash")
        else:
            total_cells.append(r"\textemdash")
    total_row = " & ".join(total_cells) + r" \\"

    column_spec = "l" + "r" * (len(columns) - 1)
    size, _, org = cache.partition("-")
    sizes = {"standard": ("64", "2\\,MiB"), "small": ("4", "32\\,KiB")}
    orgs = {"": "L1D 2-way, L2 8-way", "dm": "direct-mapped L1D/L2",
            "nway": "L1D 8-way, L2 16-way",
            "fa": "fully associative L1D/L2 (FALRU)"}
    m = re.fullmatch(r"(\d+)way", org)
    if m:
        orgs[org] = f"L1D {m.group(1)}-way, L2 8-way"
    l1d, l2 = sizes.get(size, ("?", "?"))
    cache_desc = (f"L1D {l1d}\\,KiB, L1I 32\\,KiB, L2 {l2}, "
                  f"{orgs.get(org, org)}")
    generated = datetime.now().strftime("%-d %B %Y")
    simpoint_note = ""
    if SIMPOINT:
        simpoint_note = (r"\noindent\textbf{SimPoint estimates.} Ref runs are too long to "
                         r"simulate in full: every value is estimated from up to 30 simulation "
                         r"points of 100\,M instructions per run, each after a 500\,M-instruction "
                         r"warmup, weighted by SimPoint (\texttt{cache\_scripts/simpoint.sh}; "
                         r"points and weights in each run directory's \texttt{simpoint.txt}). "
                         r"\texttt{total\_insts} is the whole program's count from qemu."
                         r"\par\medskip" "\n")
    if SCHEMA >= 9:
        reload_rule = ("the load's address lies in the bytes the store wrote; "
                       "widths may differ")
        schema_note = simpoint_note
    else:
        reload_rule = "a load from the same address at the same width"
        schema_note = (r"\noindent\textbf{Superseded results (metric schema "
                       + str(SCHEMA) + r").} The current detector (schema 9) also counts "
                       r"a reload whose address lies inside a wider or merged store "
                       r"(e.g.\ two 4-byte spills read by one 8-byte load). Schema "
                       + str(SCHEMA) + r" missed those, so \texttt{spill\_load}, "
                       r"\texttt{spill\_event} and the \texttt{other\_stack} counts "
                       r"here are lower (up to 15\% of the spill reloads in bwaves, "
                       r"8.5\% in leela, 3\% in x264, under 0.1\% in most benchmarks); "
                       r"instruction counts, spill stores and the cache behaviour of "
                       r"the pairs it found are unaffected.\par\vspace{1mm}" + "\n")

    definitions = DEFINITIONS_10 if SCHEMA >= 10 else definitions_9(reload_rule)
    return rf"""\documentclass[9pt,landscape,a4paper]{{article}}
\usepackage[landscape,a4paper,margin=10mm]{{geometry}}
\usepackage{{booktabs}}
\usepackage{{graphicx}}
\usepackage{{adjustbox}}
\usepackage{{lmodern}}
\usepackage[T1]{{fontenc}}
\usepackage{{array}}
\pagestyle{{empty}}
\setlength{{\tabcolsep}}{{2.6pt}}
\renewcommand{{\arraystretch}}{{1.08}}

\begin{{document}}
\begin{{center}}
{{\large\bfseries Improving CPU Efficiency for Data-Intensive Applications}}\\[1pt]
{{\large\bfseries through Cache-Aware Spill Optimization}}\\[5pt]
{{\normalsize Register Spill Behaviour and Cache Hit/Miss Rates on RISC-V SPEC CPU2017}}\\[7pt]
\begin{{tabular}}{{@{{}}c@{{\hspace{{3em}}}}c@{{}}}}
L\"utfullah Burak Kaya & Ismail Akturk \\[2pt]
{{\small Ozyegin University}} & {{\small Ozyegin University}} \\
{{\small burak.kaya.50711@ozu.edu.tr}} & {{\small ismail.akturk@ozyegin.edu.tr}} \\
\end{{tabular}}\\[6pt]
{{\small {generated}}}\\[3pt]
{{\small gem5 TimingSimpleCPU $\cdot$ workload profile \texttt{{{profile}}} $\cdot$ {cache_desc} $\cdot$ gem5 \texttt{{{commit}}}}}
\end{{center}}

\vspace{{-2mm}}
\noindent\footnotesize
{schema_note}{definitions}

\vspace{{2mm}}
\centering
% Scaled to the page width and to the height left under the header, so the
% table stays on the first page however many runs it has.
\begin{{adjustbox}}{{max width=\textwidth, max totalheight=0.50\textheight}}%
\begin{{tabular}}{{{column_spec}}}
\toprule
{header}
\midrule
{body}
\midrule
{total_row}
\bottomrule
\end{{tabular}}%
\end{{adjustbox}}

\end{{document}}
"""


def definitions_9(reload_rule: str) -> str:
    return rf"""\textbf{{Definitions (metric schema {SCHEMA}).}} Every stack store issued inside
the region of interest, and every later load that reads it back ({reload_rule}), belongs to
exactly one class.
\texttt{{spill}}: register-allocator spill code, identified by GCC itself
(\texttt{{-dP}} RTL dumps of the same build, memory operands in the LRA spill
area). \texttt{{csave}}: callee-saved register save/restore, return address
included, identified from the binary's CFI (\texttt{{.eh\_frame}}).
\texttt{{other\_stack}}: every remaining SP/FP-relative stack store and reload
(stack-passed arguments, memory-resident locals). \texttt{{stack\_*}} is the sum
of the three. For each class an \emph{{event}} is one (store, first reload)
pair, so $\texttt{{event}} \leq \texttt{{store}}$ and
$\texttt{{load}} \geq \texttt{{event}}$. All counters cover only the region
delimited by \texttt{{m5\_work\_begin}}/\texttt{{m5\_work\_end}}: the gem5
statistics are dumped and reset at those boundaries, so the cache columns span
the same window, and the cache tags carry the class, so per-class hit/miss
rates come straight from gem5. \emph{{Spill\,\%}} and \emph{{Csave\,\%}} are the
class's store+reload instructions over \texttt{{ROI\_insts}};
\emph{{spill/stack\,\%}} is the share of stack events that are real spills."""


DEFINITIONS_10 = r"""\textbf{Definitions (metric schema 10).} Counter names: \texttt{total\_} = whole
simulation, \texttt{roi\_} = inside the region of interest (ROI). Spills are found at run time from
effective addresses alone, without compiler information or a base-register test (an operational
definition: \emph{runtime-detected stack store--load reuse}, not necessarily compiler spill code).
\texttt{roi\_spill\_store} counts the stores that meet the store conditions of a spill: inside the
ROI, to the process stack, not atomic; read back or not. \texttt{roi\_spill\_event} counts those
read back at least once inside the ROI, one event per store at its first reload.
\texttt{roi\_spill\_load} counts the loads inside the ROI whose start address lies in the bytes
$[\textit{address}, \textit{address} + \textit{size})$ of the spill store that last wrote them
(after a partial overwrite the newest store owns the overlap; widths may differ), repeats
included. Stores before the ROI, a SimPoint warmup included, are not tracked; LR/SC and AMOs are
out of scope. Miss rates are per cache access; L2 rates are local (their denominator is the L1D
misses of that kind); \emph{sp\_ev L1 m\,\%} uses the L1D outcome of each event's store when it
executed, counted once; \emph{other st} are the stores that are no spill stores. All counters
cover only the region delimited by \texttt{m5\_work\_begin}/\texttt{m5\_work\_end}; the gem5
statistics are dumped and reset at those boundaries, so the cache columns span the same
window."""


def compile_pdf(tex_path: Path) -> Path | None:
    engine = shutil.which("tectonic")
    if engine:
        command = [engine, "--keep-logs", "--outdir", str(tex_path.parent),
                   str(tex_path)]
    else:
        engine = shutil.which("pdflatex")
        if not engine:
            return None
        command = [engine, "-interaction=nonstopmode",
                   "-output-directory", str(tex_path.parent), str(tex_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    pdf = tex_path.with_suffix(".pdf")
    if result.returncode != 0 or not pdf.is_file():
        sys.stderr.write(result.stdout[-2000:] + result.stderr[-2000:])
        return None
    return pdf


def git_commit(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True)
        commit = out.stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain",
                                "--untracked-files=no"],
                               capture_output=True, text=True, check=True)
        return commit + ("+dirty" if dirty.stdout.strip() else "")
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--profile", default="test")
    parser.add_argument("--cache", default="standard")
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--simpoint", action="store_true",
                        help="the runs are SimPoint estimates (adds a note to the report)")
    parser.add_argument("--no-files", action="store_true",
                        help="print the table only; write no CSV/LaTeX/PDF")
    parser.add_argument("--schema", type=int, default=SCHEMA,
                        help="metric schema the runs must have (8 = superseded results)")
    parser.add_argument("m5out", nargs="*", type=Path,
                        help="analyse these directories instead of discovering runs")
    args = parser.parse_args()
    globals()["SCHEMA"] = args.schema
    globals()["SIMPOINT"] = args.simpoint

    if args.m5out:
        # The run's own record names it; a bare directory falls back to its name.
        def run_name(path: Path) -> str:
            rid = path / ".runner" / "run_id"
            return rid.read_text().strip() if rid.is_file() else path.name
        candidates = [(run_name(path), "", path.resolve()) for path in args.m5out]
        skipped: list[str] = []
    else:
        candidates, skipped = discover(args.root, args.profile, args.cache)

    rows: list[Row] = []
    errors: list[str] = []
    for benchmark, input_desc, m5out in candidates:
        try:
            rows.append(build_row(benchmark, input_desc, m5out))
        except ReportError as error:
            errors.append(str(error))

    if skipped:
        print(f"Not included ({len(skipped)}):")
        for item in skipped:
            print(f"  - {item}")
        print()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if not rows:
        print("No completed runs to report.", file=sys.stderr)
        return 1

    print(f"Profile={args.profile}  cache={args.cache}  benchmarks={len(rows)}\n")
    print_table(rows)

    flagged = [row for row in rows if row.warnings]
    if flagged:
        print("\nConsistency warnings:")
        for row in flagged:
            for warning in row.warnings:
                print(f"  {row.benchmark}: {warning}")

    if args.no_files:
        return 0

    outdir = args.outdir or (args.root / "general_reports" / "results" /
                             f"spill_{args.profile}_{args.cache}_"
                             f"{datetime.now():%Y%m%d}")
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "results.csv"
    write_csv(rows, csv_path)
    tex_path = outdir / "report.tex"
    tex_path.write_text(build_latex(rows, args.profile, args.cache,
                                    git_commit(args.root)))

    print(f"\nCSV   : {csv_path}")
    print(f"LaTeX : {tex_path}")
    if args.no_pdf:
        return 0
    pdf = compile_pdf(tex_path)
    if pdf:
        print(f"PDF   : {pdf}")
    else:
        print("PDF   : not built (no tectonic/pdflatex, or compilation failed)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
