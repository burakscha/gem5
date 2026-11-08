#!/usr/bin/env python3
"""Status and percentage tables of every input set and cache configuration.

For the test, train and ref inputs (ref twice: SimPoint estimates and full
runs) it writes, into one directory:
    <set>_<config>.tex/.pdf        one input set and configuration: how many
                                   runs are completed, running and pending,
                                   the spill percentages of the program and
                                   the miss rates of the configuration, one
                                   row per run
    spill_tables_<date>.tex/.pdf   every set and configuration in one
                                   document, tables and percentages only
    README.md                      completion counts and the file list
Only completed runs of the chosen metric schema contribute numbers; the other
runs show their state, so the tables can be rebuilt at any time.

    cache_scripts/summary_tables.py
    cache_scripts/summary_tables.py --schema 9 --out DIR --no-pdf
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_status as cs  # noqa: E402

# (name, input, SimPoint, title)
SETS = [
    ("test", "test", False, "test input, full runs"),
    ("train", "train", False, "train input, full runs"),
    ("ref_simpoint", "ref", True, "ref input, SimPoint estimates"),
    ("ref_full", "ref", False, "ref input, full runs"),
]

# Program percentages: key, header, numerator fields, denominator field(s).
# A field written "-name" is subtracted.
PROGRAM_10 = [
    ("spill_roi", "spill/ROI", ("roi_spill_load", "roi_spill_store"), "roi_total_insts"),
    ("spill_ld", "spill ld/load", ("roi_spill_load",), "roi_load"),
    ("spill_st", "spill st/store", ("roi_spill_store",), "roi_store"),
    ("spill_ev", "spill event/store", ("roi_spill_event",), "roi_store"),
    ("match", "spill event/spill st", ("roi_spill_event",), "roi_spill_store"),
    ("spill_mem", "spill/mem", ("roi_spill_load", "roi_spill_store"), ("roi_load", "roi_store")),
]
PROGRAM_FORMULAS_10 = [
    ("spill/ROI", "((roi_spill_load + roi_spill_store) / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci spill load veya spill store"),
    ("spill ld/load", "(roi_spill_load / roi_load) * 100",
     "ROI load'larinin yuzde kaci spill load"),
    ("spill st/store", "(roi_spill_store / roi_store) * 100",
     "ROI store'larinin yuzde kaci spill store (geri okunsun okunmasin)"),
    ("spill event/store", "(roi_spill_event / roi_store) * 100",
     "ROI store'larinin yuzde kaci geri okunan spill store (spill event)"),
    ("spill event/spill st", "(roi_spill_event / roi_spill_store) * 100",
     "spill store'larin yuzde kaci ROI icinde geri okundu"),
    ("spill/mem", "((roi_spill_load + roi_spill_store) / (roi_load + roi_store)) * 100",
     "bellek komutlarinin yuzde kaci spill load veya spill store"),
]
PROGRAM_9 = [
    ("spill_roi", "spill/ROI", ("spill_load", "spill_store"), "roi_total_insts"),
    ("spill_ld", "spill ld/load", ("spill_load",), "roi_load"),
    ("spill_st", "spill st/store", ("spill_store",), "roi_store"),
    ("spcs_roi", "(spill+csave)/ROI",
     ("spill_load", "spill_store", "csave_load", "csave_store"), "roi_total_insts"),
    ("spcs_ld", "(spill+csave) ld/load", ("spill_load", "csave_load"), "roi_load"),
    ("spcs_st", "(spill+csave) st/store", ("spill_store", "csave_store"), "roi_store"),
]
PROGRAM_FORMULAS_9 = [
    ("spill/ROI", "((spill_load + spill_store) / roi_total_insts) * 100",
     "ROI komutlarinin yuzde kaci spill load veya spill store"),
    ("spill ld/load", "(spill_load / roi_load) * 100",
     "ROI load'larinin yuzde kaci spill reload"),
    ("spill st/store", "(spill_store / roi_store) * 100",
     "ROI store'larinin yuzde kaci spill store"),
    ("(spill+csave)/ROI",
     "((spill_load + spill_store + csave_load + csave_store) / roi_total_insts) * 100",
     "ayni oran, callee-save save/restore dahil"),
    ("(spill+csave) ld/load", "((spill_load + csave_load) / roi_load) * 100",
     "ROI load'larinin yuzde kaci spill reload veya callee-save restore"),
    ("(spill+csave) st/store", "((spill_store + csave_store) / roi_store) * 100",
     "ROI store'larinin yuzde kaci spill store veya callee-save save"),
]
# Miss rates: key of cs.MISS_COLUMNS, header.
CACHE_9 = [
    ("L1D_miss", "L1D"), ("spill_ld_L1miss", "spill ld L1"),
    ("other_ld_L1miss", "other ld L1"), ("spill_st_L1miss", "spill st L1"),
    ("other_st_L1miss", "other st L1"), ("L2_miss", "L2"),
    ("spill_ld_L2miss", "spill ld L2"), ("spill_st_L2miss", "spill st L2"),
]
CACHE_10 = [
    ("L1D_miss", "L1D"), ("spill_ld_L1miss", "spill ld L1"),
    ("other_ld_L1miss", "other ld L1"), ("spill_st_L1miss", "spill st L1"),
    ("spill_event_L1miss", "spill event st L1"), ("unread_st_L1miss", "unread st L1"),
    ("other_st_L1miss", "other st L1"), ("L2_local_miss", "L2 local"),
    ("spill_ld_L2local", "spill ld L2 local"), ("spill_st_L2local", "spill st L2 local"),
    ("spill_event_L2local", "spill event st L2 local"),
    ("unread_st_L2local", "unread st L2 local"),
]
PROGRAM, PROGRAM_FORMULAS, CACHE = PROGRAM_10, PROGRAM_FORMULAS_10, CACHE_10


def use_schema(schema: int) -> None:
    """Read results of this metric schema (9: compiler-map classes)."""
    global PROGRAM, PROGRAM_FORMULAS, CACHE
    cs.use_schema(schema)
    if schema >= 10:
        PROGRAM, PROGRAM_FORMULAS, CACHE = PROGRAM_10, PROGRAM_FORMULAS_10, CACHE_10
    else:
        PROGRAM, PROGRAM_FORMULAS, CACHE = PROGRAM_9, PROGRAM_FORMULAS_9, CACHE_9
DASH = r"\textemdash"
TEX_ESCAPE = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
              "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"$\sim$",
              "^": r"\^{}", ">": r"$>$", "<": r"$<$"}


def tex(s) -> str:
    return "".join(TEX_ESCAPE.get(ch, ch) for ch in str(s))


def fmt(part, whole) -> str:
    return DASH if part is None or not whole else f"{100.0 * part / whole:.2f}\\%"


# --------------------------------------------------------------------------
# Numbers of one run, as (numerator, denominator) so they can be pooled
# --------------------------------------------------------------------------
def program_fractions(r: dict) -> dict[str, tuple[float, float]]:
    roi = r["roi"]
    value = lambda f: -roi.get(f[1:], 0) if f.startswith("-") else roi.get(f, 0)
    return {key: (sum(value(f) for f in nums),
                  sum(value(f) for f in ((den,) if isinstance(den, str) else den)))
            for key, _, nums, den in PROGRAM}


def cache_fractions(r: dict) -> dict[str, tuple[float, float]]:
    return cs.miss_fractions(r)


def summary_cells(fracs: list[dict], keys: list[str]) -> tuple[list[str], list[str]]:
    """Pooled (sums of numerators over sums of denominators) and mean (of the
    per-run percentages) cells over the given runs."""
    pooled, mean = [], []
    for k in keys:
        pooled.append(fmt(sum(f[k][0] for f in fracs), sum(f[k][1] for f in fracs)))
        vals = [100.0 * f[k][0] / f[k][1] for f in fracs if f[k][1]]
        mean.append(f"{sum(vals) / len(vals):.2f}\\%" if vals else DASH)
    return pooled, mean


def state_cell(r: dict) -> str:
    if r["state"] == "COMPLETED":
        return "done"
    if r["state"] == "RUNNING":
        p = cs.progress(r)
        if p.startswith(">100%"):
            p = ">100%"
        return tex("running" + ("" if p == "-" else f" {p}"))
    return tex(r["state"].lower())


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def collect(inp: str, simpoint: bool) -> dict:
    cs.PROFILE, cs.SIMPOINT = inp, simpoint
    runs = cs.workloads()
    configs = cs.ALL_CONFIGS if simpoint else (cs.planned_caches(inp) or cs.ALL_CONFIGS)
    records, geometry = {}, {}
    for cfg in configs:
        records[cfg] = [cs.run_record(cfg, rid, bench) for rid, bench in runs]
        rows, _ = cs.geometry(cfg, runs)
        g = {row[0]: f"{row[5]} sets x {row[6]}" for row in rows}
        geometry[cfg] = f"L1D {g.get('L1D', '?')}, L2 {g.get('L2', '?')}"
    return {"runs": runs, "configs": configs, "records": records, "geometry": geometry}


def tally(records: list[dict]) -> dict[str, int]:
    t = {"completed": 0, "running": 0, "pending": 0, "other": 0, "total": len(records)}
    for r in records:
        key = r["state"].lower()
        t[key if key in ("completed", "running", "pending") else "other"] += 1
    t["remaining"] = t["total"] - t["completed"]
    return t


# --------------------------------------------------------------------------
# LaTeX
# --------------------------------------------------------------------------
def longtable(spec: str, header: list[str], rows: list[str], foot: list[str]) -> str:
    head = " & ".join(header) + r" \\"
    body = "\n".join(rows)
    tail = ("\n\\midrule\n" + "\n".join(foot)) if foot else ""
    return (f"\\begin{{longtable}}{{{spec}}}\n\\toprule\n{head}\n\\midrule\n\\endhead\n"
            f"\\bottomrule\n\\endfoot\n{body}{tail}\n\\end{{longtable}}\n")


def status_line(t: dict[str, int]) -> str:
    return (f"\\textbf{{{t['completed']} of {t['total']} runs completed}}, "
            f"{t['running']} running, {t['pending']} pending"
            + (f", {t['other']} other (failed/stopped)" if t["other"] else "")
            + f"; \\textbf{{{t['remaining']} remaining}}.\\par\n")


def program_table(runs, per_run: list[list[dict]], n_configs: int) -> str:
    """per_run[i]: completed records of run i over the configurations (the
    program counts do not depend on the cache; the first one is shown)."""
    keys = [k for k, _, _, _ in PROGRAM]
    rows, fracs = [], []
    for (rid, _), done in zip(runs, per_run):
        if done:
            f = program_fractions(done[0])
            fracs.append(f)
            cells = [fmt(*f[k]) for k in keys]
        else:
            cells = [DASH] * len(keys)
        rows.append(" & ".join([tex(rid), f"{len(done)}/{n_configs}", *cells]) + r" \\")
    foot = []
    if fracs:
        pooled, mean = summary_cells(fracs, keys)
        foot = [" & ".join(["pooled", "", *pooled]) + r" \\",
                " & ".join(["mean", "", *mean]) + r" \\"]
    header = ["run", "configs done", *(h for _, h, _, _ in PROGRAM)]
    return longtable("lc" + "r" * len(keys), header, rows, foot)


def cache_table(records: list[dict]) -> str:
    keys = [k for k, _ in CACHE]
    rows, fracs = [], []
    for r in records:
        if r["state"] == "COMPLETED":
            f = cache_fractions(r)
            fracs.append(f)
            cells = [fmt(*f[k]) for k in keys]
        else:
            cells = [DASH] * len(keys)
        rows.append(" & ".join([tex(r["run_id"]), state_cell(r), *cells]) + r" \\")
    foot = []
    if fracs:
        pooled, mean = summary_cells(fracs, keys)
        foot = [" & ".join(["pooled", "", *pooled]) + r" \\",
                " & ".join(["mean", "", *mean]) + r" \\"]
    return longtable("ll" + "r" * len(keys), ["run", "state", *(h for _, h in CACHE)],
                     rows, foot)


def remaining_table(data: dict) -> str:
    """State of every run that is not completed in all configurations."""
    configs, recs = data["configs"], data["records"]
    rows = []
    for i, (rid, _) in enumerate(data["runs"]):
        states = [recs[c][i] for c in configs]
        if all(r["state"] == "COMPLETED" for r in states):
            continue
        rows.append(" & ".join([tex(rid), *(state_cell(r) for r in states)]) + r" \\")
    if not rows:
        return ""
    return ("{\\small Runs not completed in every configuration:}\\par\n"
            + longtable("l" + "l" * len(configs), ["run", *map(tex, configs)], rows, []))


def legend() -> str:
    rows = [f"{tex(h)} & \\texttt{{{tex(f)}}} & {tex(d)} \\\\" for h, f, d in PROGRAM_FORMULAS]
    labels = dict(CACHE)
    for name, formula, lines in cs.MISS_FORMULAS:
        if name not in labels:
            continue
        rows.append(f"{tex(labels[name])} & \\texttt{{{tex(formula)}}} & "
                    f"{tex(' '.join(lines))} \\\\")
    return ("\\section*{Formulas}\n{\\footnotesize\n"
            + longtable("lp{11cm}p{10cm}", ["column", "formula", "aciklama"], rows, [])
            + (r"Schema 10: spills are found from runtime addresses alone, store and reload "
               r"both inside the ROI (an operational definition, not necessarily compiler "
               r"spill code). spill store = a store inside the ROI to the stack (the store "
               r"conditions of a spill), read back or not; spill event = a spill store read "
               r"back at least once, one per store; unread st = a spill store never read "
               r"back; other st = a store that is no spill store; spill load = a load that "
               r"reads a spill store back, repeats included. "
               if cs.SCHEMA >= 10 else
               "spill = compiler-confirmed register-allocator spill (GCC \\texttt{-dP}), "
               "csave = callee-saved register save/restore (CFI), both inside the ROI only. ")
            + "pooled = sum of numerators / sum of denominators over the completed runs; "
            "mean = average of the per-run percentages. "
            "Miss rates are per cache access; an L2 rate is local: its denominator is the "
            "L1D misses of that access type.\\par}\n")


def document(title: str, subtitle: str, body: str) -> str:
    return rf"""\documentclass[10pt,a4paper,landscape]{{article}}
\usepackage[landscape,a4paper,margin=12mm]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern,booktabs,longtable}}
\setlength{{\LTpre}}{{2pt}}\setlength{{\LTpost}}{{8pt}}
\setlength{{\tabcolsep}}{{4pt}}
\begin{{document}}
\begin{{center}}
{{\large\bfseries {title}}}\\[3pt]
{{\small {subtitle}}}
\end{{center}}
{body}
\end{{document}}
"""


def config_body(data: dict, cfg: str) -> str:
    recs = data["records"][cfg]
    per_run = [[r] if r["state"] == "COMPLETED" else [] for r in recs]
    return (status_line(tally(recs))
            + "\\subsection*{Program (does not depend on the cache)}\n{\\footnotesize\n"
            + program_table(data["runs"], per_run, 1) + "}\n"
            + "\\subsection*{Miss rates}\n{\\footnotesize\n" + cache_table(recs) + "}\n")


def set_body(name: str, title: str, data: dict) -> str:
    configs, recs = data["configs"], data["records"]
    out = [f"\\clearpage\n\\section*{{{tex(title)}}}\n"]
    out.append("{\\small\n" + longtable(
        "lrrrrr", ["config", "completed", "running", "pending", "other", "remaining"],
        [" & ".join([tex(c), f"{t['completed']}/{t['total']}", str(t['running']),
                     str(t['pending']), str(t['other']), str(t['remaining'])]) + r" \\"
         for c in configs for t in [tally(recs[c])]], []) + "}\n")
    out.append(remaining_table(data))
    if not any(r["state"] == "COMPLETED" for c in configs for r in recs[c]):
        out.append("\\emph{No completed run yet: no percentages.}\\par\n")
        return "".join(out)
    per_run = [[recs[c][i] for c in configs if recs[c][i]["state"] == "COMPLETED"]
               for i in range(len(data["runs"]))]
    out.append("\\subsection*{Program (does not depend on the cache)}\n{\\footnotesize\n"
               + program_table(data["runs"], per_run, len(configs)) + "}\n")
    for cfg in configs:
        out.append(f"\\clearpage\n\\subsection*{{Miss rates: {tex(cfg)} "
                   f"({tex(data['geometry'][cfg])})}}\n"
                   + status_line(tally(recs[cfg]))
                   + "{\\footnotesize\n" + cache_table(recs[cfg]) + "}\n")
    return "".join(out)


def shown(path: Path) -> Path:
    """path relative to the repository when it lies inside it."""
    try:
        return path.relative_to(cs.ROOT)
    except ValueError:
        return path


def build_pdf(engine: str | None, tex_path: Path) -> str:
    if not engine:
        return ""
    r = subprocess.run([engine, "--outdir", str(tex_path.parent), str(tex_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        (tex_path.with_suffix(".log")).write_text(r.stdout + r.stderr)
        return " (pdf FAILED, see .log)"
    return " + pdf"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--schema", type=int, default=cs.CURRENT_SCHEMA)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    use_schema(args.schema)
    today = datetime.now()
    stamp = f"{today:%Y%m%d}"
    out = args.out or cs.ROOT / "general_reports" / "results" / f"summary_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    engine = None if args.no_pdf else (shutil.which("tectonic") or shutil.which("pdflatex"))
    common = (f"metric schema {args.schema} $\\cdot$ gem5 TimingSimpleCPU $\\cdot$ "
              f"{today:%-d %B %Y}")

    sets = {}
    for name, inp, simpoint, title in SETS:
        data = sets[name] = collect(inp, simpoint)
        for cfg in data["configs"]:
            path = out / f"{name}_{cfg}.tex"
            path.write_text(document(
                f"{tex(title)} --- {tex(cfg)}",
                f"{tex(data['geometry'][cfg])} $\\cdot$ {common}",
                config_body(data, cfg) + legend()))
            print(f"{shown(path)}{build_pdf(engine, path)}")

    # Overview: completion counts of every set and configuration.
    rows, md = [], []
    for name, _, _, title in SETS:
        data = sets[name]
        for cfg in data["configs"]:
            t = tally(data["records"][cfg])
            rows.append(" & ".join([tex(title), tex(cfg), f"{t['completed']}/{t['total']}",
                                    str(t['running']), str(t['pending']), str(t['other']),
                                    str(t['remaining'])]) + r" \\")
            md.append(f"| {title} | {cfg} | {t['completed']}/{t['total']} | {t['running']} "
                      f"| {t['pending']} | {t['other']} | {t['remaining']} |")
    overview = ("\\section*{Completion}\n{\\small\n" + longtable(
        "llrrrrr", ["set", "config", "completed", "running", "pending", "other", "remaining"],
        rows, []) + "}\n")
    combined = out / f"spill_tables_{stamp}.tex"
    combined.write_text(document(
        "Register spill study: status and percentage tables",
        f"L1D 4\\,KiB, L1I 32\\,KiB, L2 32\\,KiB, 64\\,B lines, LRU $\\cdot$ {common}",
        overview + "".join(set_body(name, title, sets[name]) for name, _, _, title in SETS)
        + "\\clearpage\n" + legend()))
    print(f"{shown(combined)}{build_pdf(engine, combined)}")

    (out / "README.md").write_text("\n".join([
        f"# Status and percentage tables, metric schema {args.schema}", "",
        f"Built {today:%Y-%m-%d %H:%M} by `cache_scripts/summary_tables.py`. Only completed "
        "runs contribute numbers; rebuild the files at any time.", "",
        "| set | config | completed | running | pending | other | remaining |",
        "|---|---|---|---|---|---|---|", *md, "",
        "| file | content |", "|---|---|",
        f"| `spill_tables_{stamp}.pdf` | every set and configuration in one document: "
        "tables and percentages only |",
        "| `<set>_<config>.pdf` | one set and configuration: completion, program "
        "percentages, miss rates (`.tex` is the source) |", "",
        "Detailed reports with counts: `general_reports/results/schema<N>_<input>[_simpoint]_<date>/` "
        "(`cache_scripts/export_results.py --pdf`) and per benchmark "
        "`benchmarks/<bench>/<input>/report/` (`cache_scripts/benchmark_reports.py`).", ""]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
