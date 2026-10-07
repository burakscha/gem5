#!/usr/bin/env python3
"""Collect schema-v7 spill and cache metrics for every SPEC run and report them.

Reads two files per gem5 output directory:

  riscv_spill_stats.txt  ROI summary blocks written by SpillDetector. Already
                         ROI-scoped, and the source of every spill/fill number.
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

SCHEMA = 7

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
            if key.startswith("reuse_log2"):
                continue
            current[key] = int(field_match.group(2))
    return rois, global_block, classification


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
    odd indices. If the layout does not match (an older binary without the
    ROI dump hooks, or an aborted run) fall back to summing every block,
    which reproduces the whole-simulation totals, and say so.
    """
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
    spill_store = total(rois, "spill_store")
    spill_load = total(rois, "spill_load")
    spill_event = total(rois, "spill_event")
    spill_total = spill_store + spill_load

    l1d_hits, l1d_misses = cache_pair(stats, "system.cpu.dcache")
    l1i_hits, l1i_misses = cache_pair(stats, "system.cpu.icache")
    l2_hits, l2_misses = cache_pair(stats, "system.l2")

    st_l1_hits = total(rois, "spill_store_l1_hits")
    st_l1_misses = total(rois, "spill_store_l1_misses")
    ld_l1_hits = total(rois, "spill_load_l1_hits")
    ld_l1_misses = total(rois, "spill_load_l1_misses")

    # gem5's own instruction counters. They are ROI-scoped too, because
    # workbegin/workend dump+reset the statistics, so they are an independent
    # check on the detector's ROI counters rather than a different window.
    gem5_roi_ops = int(stats.get("simOps", 0))
    gem5_roi_loads = int(stats.get("system.cpu.commitStats0.numLoadInsts", 0))
    gem5_roi_stores = int(stats.get("system.cpu.commitStats0.numStoreInsts", 0))

    row.values = {
        "benchmark": benchmark,
        "input": input_desc,
        "classification": classification,
        "cache_stat_scope": scope,
        "roi_count": len(rois),
        # --- tier 1: global, whole simulation ---
        "total_insts": global_block.get("total_insts", 0),
        "total_load": global_block.get("total_load", 0),
        "total_store": global_block.get("total_store", 0),
        "total_spill_event": global_block.get("total_spill_event", 0),
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
        # --- tier 3: spill, ROI only by construction ---
        "spill_store": spill_store,
        "spill_load": spill_load,
        "total_spill_insts": spill_total,
        "spill_event": spill_event,
        "repeat_spill_load": total(rois, "repeat_spill_load"),
        "spill_inst_pct": pct(spill_total, instructions),
        "spill_event_pct": pct(spill_event, instructions),
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
        # --- cache behaviour of the spill population itself ---
        "spill_store_l1_hits": st_l1_hits,
        "spill_store_l1_misses": st_l1_misses,
        "spill_store_l1_miss_pct": pct(st_l1_misses, st_l1_hits + st_l1_misses),
        "spill_store_l2_hits": total(rois, "spill_store_l2_hits"),
        "spill_store_l2_misses": total(rois, "spill_store_l2_misses"),
        "spill_load_l1_hits": ld_l1_hits,
        "spill_load_l1_misses": ld_l1_misses,
        "spill_load_l1_miss_pct": pct(ld_l1_misses, ld_l1_hits + ld_l1_misses),
        "spill_load_l2_hits": total(rois, "spill_load_l2_hits"),
        "spill_load_l2_misses": total(rois, "spill_load_l2_misses"),
        # --- diagnostics, reported but never mixed into the headline ---
        "spill_store_unpaired": total(rois, "spill_store_unpaired"),
        "diag_paired_store_l1_hits": total(rois, "diag_paired_store_l1_hits"),
        "diag_paired_store_l1_misses": total(rois, "diag_paired_store_l1_misses"),
        "diag_nonspill_reuse": total(rois, "diag_nonspill_reuse"),
        "diag_store_map_evicted": total(rois, "diag_store_map_evicted"),
    }

    # The counters exist so these identities can be checked rather than
    # assumed; a silent capture failure would otherwise look like clean data.
    check_identity(row, "spill_load L1 accesses", ld_l1_hits + ld_l1_misses,
                   total(rois, "spill_load_l1_accesses"))
    check_identity(row, "spill_store L1 accesses", st_l1_hits + st_l1_misses,
                   total(rois, "spill_store_l1_accesses"))
    check_identity(row, "spill_store_unpaired",
                   total(rois, "spill_store_unpaired"), spill_store - spill_event)
    if scope == "roi":
        # Both gem5 request tags line up with a headline counter now, which is
        # the point of defining spill_store as the whole write side.
        for tag, expected in (("spillLoadHits", ld_l1_hits),
                              ("spillLoadMisses", ld_l1_misses),
                              ("spillStoreHits", st_l1_hits),
                              ("spillStoreMisses", st_l1_misses)):
            check_identity(row, f"dcache.{tag}", expected,
                           int(stats.get(f"system.cpu.dcache.{tag}", -1)))
    if total(rois, "diag_store_map_evicted"):
        row.warnings.append("store map overflowed; some spill pairs were censored")
    return row


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
TABLE_COLUMNS = [
    ("benchmark", "benchmark", "{}"),
    ("roi_total_insts", "ROI_total_insts", "{:,}"),
    ("roi_load", "ROI_load", "{:,}"),
    ("roi_store", "ROI_store", "{:,}"),
    ("spill_store", "spill_store", "{:,}"),
    ("spill_load", "spill_load", "{:,}"),
    ("total_spill_insts", "total_spill", "{:,}"),
    ("spill_event", "spill_event", "{:,}"),
    ("spill_store_unpaired", "st_unpaired", "{:,}"),
    ("spill_inst_pct", "spill%", "{:.2f}"),
    ("l1d_hits", "L1D hit", "{:,}"),
    ("l1d_misses", "L1D miss", "{:,}"),
    ("l1d_miss_pct", "L1D miss%", "{:.3f}"),
    ("l2_hits", "L2 hit", "{:,}"),
    ("l2_misses", "L2 miss", "{:,}"),
    ("l2_miss_pct", "L2 miss%", "{:.2f}"),
    ("spill_load_l1_misses", "sp_ld miss", "{:,}"),
    ("spill_load_l1_miss_pct", "sp_ld miss%", "{:.3f}"),
    ("spill_store_l1_misses", "sp_st miss", "{:,}"),
    ("spill_store_l1_miss_pct", "sp_st miss%", "{:.3f}"),
    ("delta_roi_store", "d_store(gem5)", "{:+,}"),
]


def cell(value: object, spec: str) -> str:
    if value is None:
        return "n/a"
    try:
        return spec.format(value)
    except (ValueError, TypeError):
        return str(value)


def print_table(rows: list[Row]) -> None:
    header = [label for _, label, _ in TABLE_COLUMNS]
    body = [[cell(row.values.get(key), spec) for key, _, spec in TABLE_COLUMNS]
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
LATEX_COLUMNS = [
    ("benchmark", "Benchmark", "{}", None),
    ("roi_total_insts", r"ROI\_total\_insts", "{:,}", "sum"),
    ("roi_load", r"ROI\_load", "{:,}", "sum"),
    ("roi_store", r"ROI\_store", "{:,}", "sum"),
    ("spill_store", r"spill\_store", "{:,}", "sum"),
    ("spill_load", r"spill\_load", "{:,}", "sum"),
    ("total_spill_insts", r"total\_spill", "{:,}", "sum"),
    ("spill_event", r"\textbf{spill\_event}", "{:,}", "sum"),
    ("spill_inst_pct", r"Spill\,\%", "{:.2f}",
     ("total_spill_insts", "roi_total_insts", 100.0)),
    ("l1d_hits", "L1D hits", "{:,}", "sum"),
    ("l1d_misses", "L1D miss", "{:,}", "sum"),
    ("l1d_miss_pct", r"L1D m\,\%", "{:.3f}",
     ("l1d_misses", "l1d_accesses", 100.0)),
    ("l2_hits", "L2 hits", "{:,}", "sum"),
    ("l2_misses", "L2 miss", "{:,}", "sum"),
    ("l2_miss_pct", r"L2 m\,\%", "{:.2f}", None),
    ("spill_load_l1_miss_pct", r"sp\_load m\,\%", "{:.3f}", None),
    ("spill_store_l1_miss_pct", r"sp\_store m\,\%", "{:.3f}", None),
]


def build_latex(rows: list[Row], profile: str, cache: str, commit: str) -> str:
    def latex_int(value: object) -> str:
        return f"{int(value):,}".replace(",", r"\,")

    header = " & ".join(label for _, label, _, _ in LATEX_COLUMNS) + r" \\"
    lines = []
    for row in rows:
        cells = []
        for key, _, spec, _ in LATEX_COLUMNS:
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

    # Derived from LATEX_COLUMNS so the Total row can never drift out of sync
    # with the header when a column is added or moved.
    summed = {}
    for key, _, _, rule in LATEX_COLUMNS:
        if rule == "sum":
            summed[key] = sum(int(row.values.get(key) or 0) for row in rows)
    for extra in ("l1d_accesses",):
        summed[extra] = sum(int(row.values.get(extra) or 0) for row in rows)

    total_cells = []
    for key, _, spec, rule in LATEX_COLUMNS:
        if key == "benchmark":
            total_cells.append(r"\textbf{Total}")
        elif rule == "sum":
            text = latex_int(summed[key])
            total_cells.append(r"\textbf{" + text + "}"
                               if key == "spill_event" else text)
        elif isinstance(rule, tuple):
            num, den, scale = rule
            denominator = summed.get(den, 0)
            total_cells.append(cell(scale * summed.get(num, 0) / denominator, spec)
                               if denominator else r"\textemdash")
        else:
            total_cells.append(r"\textemdash")
    total_row = " & ".join(total_cells) + r" \\"

    column_spec = "l" + "r" * (len(LATEX_COLUMNS) - 1)
    cache_desc = ("L1I/L1D 32\\,KiB, L2 256\\,KiB" if cache == "standard"
                  else "L1D 4\\,KiB, L2 32\\,KiB")
    generated = datetime.now().strftime("%-d %B %Y")

    return rf"""\documentclass[9pt,landscape,a4paper]{{article}}
\usepackage[landscape,a4paper,margin=10mm]{{geometry}}
\usepackage{{booktabs}}
\usepackage{{graphicx}}
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
\textbf{{Definitions.}} A \texttt{{spill\_store}} is a stack store issued
SP/FP-relative inside the region of interest; a \texttt{{spill\_load}} is a
load that reads a value back from the same address at the same access width,
repeats counted. A \texttt{{spill\_event}} is one (store, first read-back)
pair, i.e.\ one \emph{{potential}} spill. Hence
$\texttt{{spill\_event}} \leq \texttt{{spill\_store}}$ (a value may be written
and never read back again inside the region) and
$\texttt{{spill\_load}} \geq \texttt{{spill\_event}}$ (a value may be read back
many times), while
$\texttt{{total\_spill\_insts}} = \texttt{{spill\_store}} +
\texttt{{spill\_load}}$. The classification is microarchitectural and cannot
separate compiler register spills from ABI-mandated callee-save traffic or
ordinary scalar stack locals, so these are upper bounds on true
register-allocator spilling; the store side is the looser of the two, because
at store time a later read-back is unknowable. All counters cover only the
region delimited by \texttt{{m5\_work\_begin}}/\texttt{{m5\_work\_end}}: the
gem5 statistics are dumped and reset at those boundaries, so the cache columns
span exactly the same window, and the ROI instruction, load and store columns
were cross-checked against gem5's own \texttt{{simOps}} and
\texttt{{commitStats0}} counters. \emph{{Spill\,\%}} is
$\texttt{{total\_spill\_insts}}/\texttt{{ROI\_total\_insts}}$.

\vspace{{2mm}}
\centering
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{{column_spec}}}
\toprule
{header}
\midrule
{body}
\midrule
{total_row}
\bottomrule
\end{{tabular}}%
}}

\end{{document}}
"""


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
    parser.add_argument("--no-files", action="store_true",
                        help="print the table only; write no CSV/LaTeX/PDF")
    parser.add_argument("m5out", nargs="*", type=Path,
                        help="analyse these directories instead of discovering runs")
    args = parser.parse_args()

    if args.m5out:
        candidates = [(path.name, "", path.resolve()) for path in args.m5out]
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
