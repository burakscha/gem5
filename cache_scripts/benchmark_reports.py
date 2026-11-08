#!/usr/bin/env python3
"""Per-benchmark LaTeX reports of the cache organisation experiment.

For every benchmark and input set it writes
    benchmarks/<bench>/<input>/report/<bench>_<input>.tex  (and .pdf)
with, for each of the benchmark's runs (SPEC invocations) of that input:
  - the program table: instruction, load/store and stack-class counts and the
    spill ratios. They do not depend on the cache, so one row serves all
    configurations (the script checks that every configuration agrees);
  - the configuration table: one row per cache configuration with its
    geometry and the miss rates of table 3 of status_cache.sh.
Only completed runs of the chosen metric schema are used; a run that has not
finished yet shows as missing, so the reports can be rebuilt at any time.

    cache_scripts/benchmark_reports.py --input test
    cache_scripts/benchmark_reports.py --input train --bench x264 mcf
    cache_scripts/benchmark_reports.py --input test --schema 8 --out /tmp/r8
    cache_scripts/benchmark_reports.py --input ref --simpoint   (-> <bench>_ref_simpoint.tex)
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

PROGRAM_9 = [  # (label, value(counts, roi)); schema 9 results
    ("ROI insts", lambda c, r: c["roi_total_insts"]),
    ("ROI loads", lambda c, r: c["roi_load"]),
    ("ROI stores", lambda c, r: c["roi_store"]),
    ("spill store", lambda c, r: r.get("spill_store")),
    ("spill load", lambda c, r: r.get("spill_load")),
    ("spill event", lambda c, r: r.get("spill_event")),
    ("csave event", lambda c, r: r.get("csave_event")),
    ("other\\_stack event", lambda c, r: r.get("other_stack_event")),
]
PROGRAM_10 = [  # schema 10, under the canonical counter names
    ("roi\\_total\\_insts", lambda c, r: c["roi_total_insts"]),
    ("roi\\_load", lambda c, r: c["roi_load"]),
    ("roi\\_store", lambda c, r: c["roi_store"]),
    ("roi\\_spill\\_store", lambda c, r: c["roi_spill_store"]),
    ("roi\\_spill\\_event", lambda c, r: c["roi_spill_event"]),
    ("roi\\_spill\\_load", lambda c, r: c["roi_spill_load"]),
]
PROGRAM_PCT_9 = [  # (label, numerator, denominator) over counts()
    ("spill/ROI", "roi_spill_insts", "roi_total_insts"),
    ("spill load/load", "roi_spill_load", "roi_load"),
    ("spill store/store", "roi_spill_store", "roi_store"),
]
PROGRAM_PCT_10 = [
    ("spill/ROI", "roi_spill_insts", "roi_total_insts"),
    ("spill load/load", "roi_spill_load", "roi_load"),
    ("spill store/store", "roi_spill_store", "roi_store"),
    ("spill event/store", "roi_spill_event", "roi_store"),
    ("spill event/spill store", "roi_spill_event", "roi_spill_store"),
    ("spill/mem", "roi_spill_insts", "roi_total_mem"),
]


def program_columns():
    return ((PROGRAM_10, PROGRAM_PCT_10) if cs.SCHEMA >= 10
            else (PROGRAM_9, PROGRAM_PCT_9))
MISS_LABELS = {
    "L1D_miss": "L1D", "spill_ld_L1miss": "spill ld L1", "other_ld_L1miss": "other ld L1",
    "spill_st_L1miss": "spill st L1", "other_st_L1miss": "other st L1",
    "stack_st_L1miss": "stack st L1",
    "L2_miss": "L2", "spill_ld_L2miss": "spill ld L2", "spill_st_L2miss": "spill st L2",
    "stack_st_L2miss": "stack st L2",
    "L2_local_miss": "L2 local", "spill_ld_L2local": "spill ld L2 local",
    "spill_st_L2local": "spill st L2 local",
    "spill_event_L1miss": "spill event st L1", "spill_event_L2local": "spill event st L2 local",
    "unread_st_L1miss": "unread st L1", "unread_st_L2local": "unread st L2 local",
}
SPEC_NAMES = {
    "perlbench": "500.perlbench_r", "gcc": "502.gcc_r", "bwaves": "503.bwaves_r",
    "mcf": "505.mcf_r", "cactuBSSN": "507.cactuBSSN_r", "namd": "508.namd_r",
    "parest": "510.parest_r", "povray": "511.povray_r", "lbm": "519.lbm_r",
    "omnetpp": "520.omnetpp_r", "wrf": "521.wrf_r", "xalancbmk": "523.xalancbmk_r",
    "x264": "525.x264_r", "blender": "526.blender_r", "cam4": "527.cam4_r",
    "deepsjeng": "531.deepsjeng_r", "imagick": "538.imagick_r", "leela": "541.leela_r",
    "nab": "544.nab_r", "exchange2": "548.exchange2_r", "fotonik3d": "549.fotonik3d_r",
    "roms": "554.roms_r", "xz": "557.xz_r",
}


def tex(s: str) -> str:
    return (str(s).replace("\\", "\\textbackslash{}").replace("_", "\\_")
            .replace("%", "\\%").replace("&", "\\&").replace("#", "\\#"))


def num(v) -> str:
    return "\\textemdash" if v is None else f"{int(v):,}".replace(",", "\\,")


def pct(a, b) -> str:
    return "\\textemdash" if a is None or not b else f"{100.0 * a / b:.2f}\\%"


def run_section(run_id: str, input_desc: str, records: dict[str, dict],
                geometry: dict[str, str]) -> str:
    done = {cfg: r for cfg, r in records.items() if r["state"] == "COMPLETED"}
    head = f"\\subsection*{{{tex(run_id)}}}\n{{\\small input: {tex(input_desc)}}}\\par\\smallskip\n"
    if not done:
        return head + "\\emph{No completed run yet.}\n"
    first = next(iter(done.values()))
    c0, r0 = cs.counts(first), first["roi"]
    program, program_pct = program_columns()
    values = [f(c0, r0) for _, f in program]
    agree = all([f(cs.counts(r), r["roi"]) for _, f in program] == values
                for r in done.values())
    prog = ("\\begin{tabular}{" + "r" * (len(program) + len(program_pct)) + "}\\toprule\n"
            + " & ".join(l for l, _ in program) + " & "
            + " & ".join(l for l, _, _ in program_pct) + " \\\\\\midrule\n"
            + " & ".join(num(v) for v in values) + " & "
            + " & ".join(pct(c0[a], c0[b]) for _, a, b in program_pct)
            + " \\\\\\bottomrule\n\\end{tabular}\n")
    note = ("" if agree else
            "\\par{\\small\\textbf{Note:} the configurations do not agree on these "
            "counts; values above are from the first completed one.}\n")
    rows = []
    for cfg, r in records.items():
        m = cs.cache_misses(r) if r["state"] == "COMPLETED" else {}
        cells = [tex(cfg), tex(geometry.get(cfg, "")),
                 *(tex(m.get(k, "\\textemdash")) if m.get(k, "-") != "-" else "\\textemdash"
                   for k in cs.MISS_COLUMNS),
                 cs.duration(r["elapsed"]) if r["state"] == "COMPLETED" else tex(r["state"])]
        rows.append(" & ".join(cells) + " \\\\")
    conf = ("\\begin{tabular}{ll" + "r" * (len(cs.MISS_COLUMNS) + 1) + "}\\toprule\n"
            "config & L1D / L2 & " + " & ".join(MISS_LABELS[k] for k in cs.MISS_COLUMNS)
            + " & host time \\\\\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
    return (head + "\\resizebox{\\linewidth}{!}{" + prog + "}" + note
            + "\\par\\medskip\n\\resizebox{\\linewidth}{!}{" + conf + "}\n")


def document(bench: str, input_set: str, sections: list[str], schema: int,
             simpoint: bool = False) -> str:
    spec = SPEC_NAMES.get(bench, bench)
    if schema >= 10:
        rule = (r"Spills are found at run time from addresses alone: a \emph{stack store} is a "
                r"store to the stack, a \emph{spill load} a later load whose address lies in the "
                r"bytes the newest covering stack store wrote, and a \emph{spill store} a stack "
                r"store read back at least once (one \emph{event}; every reload is a spill load). "
                r"Spill-store miss rates use each read-back store's own outcome; stack-store "
                r"miss rates cover every stack store.")
    elif schema >= 9:
        rule = (r"A stack store's reload is a later load whose address lies in the bytes the "
                r"store wrote. \texttt{spill}: compiler-confirmed register-allocator spill "
                r"(GCC \texttt{-dP}); \texttt{csave}: callee-saved save/restore (CFI); "
                r"\texttt{other\_stack}: other SP/FP-relative stack traffic. An \emph{event} "
                r"is one store and its first reload.")
    else:
        rule = ("A stack store's reload is a later load from the same address at the same "
                "width (schema " + str(schema) + ", superseded by schema 9).")
    simpoint = ("" if not simpoint else
                r" Ref values are SimPoint estimates: per run up to 30 simulation points of"
                r" 100\,M instructions, each after a 500\,M-instruction warmup, weighted by"
                r" SimPoint (\texttt{cache\_scripts/simpoint.sh}); host time is the summed"
                r" simulation time of the points.")
    return rf"""\documentclass[10pt,a4paper,landscape]{{article}}
\usepackage[landscape,a4paper,margin=12mm]{{geometry}}
\usepackage{{booktabs,graphicx,lmodern}}
\usepackage[T1]{{fontenc}}
\pagestyle{{empty}}
\begin{{document}}
\begin{{center}}
{{\large\bfseries {tex(spec)} --- {tex(input_set)} input}}\\[3pt]
{{\small Register spill behaviour and cache miss rates under five L1D/L2 organisations
(L1D 4\,KiB, L1I 32\,KiB, L2 32\,KiB, 64\,B lines, LRU) $\cdot$ gem5 TimingSimpleCPU
$\cdot$ metric schema {schema} $\cdot$ {datetime.now():%-d %B %Y}}}
\end{{center}}
{{\footnotesize Counts cover only the region of interest (\texttt{{m5\_work\_begin}}/\texttt{{end}}).
{rule}
The program table does not
depend on the cache; the configuration table gives miss rates in percent of cache accesses:
\emph{{L1D}} all data accesses, \emph{{spill/other ld/st L1}} spill vs.\ other loads and stores in
L1D, \emph{{L2}} all requests reaching L2, \emph{{spill ld/st L2}} the L1D misses of spill accesses
that missed in L2 too.{simpoint}\par}}
{"".join(sections)}
\end{{document}}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", default="test", choices=("test", "train", "ref"))
    ap.add_argument("--schema", type=int, default=cs.CURRENT_SCHEMA)
    ap.add_argument("--bench", nargs="*", help="only these benchmarks")
    ap.add_argument("--out", type=Path, help="write here instead of benchmarks/<b>/<input>/report")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--simpoint", action="store_true",
                    help="SimPoint estimates (cache_scripts/simpoint.sh) instead of full runs")
    args = ap.parse_args()
    cs.use_schema(args.schema)
    cs.PROFILE, cs.SIMPOINT = args.input, args.simpoint

    manifest = subprocess.run([str(cs.RUNNER), "list", args.input], capture_output=True,
                              text=True, check=True).stdout.splitlines()[2:]
    by_bench: dict[str, list[tuple[str, str]]] = {}
    for line in manifest:
        f = line.split(None, 3)
        if len(f) >= 3:
            by_bench.setdefault(f[1], []).append((f[0], f[3] if len(f) > 3 else ""))
    configs = cs.planned_caches(args.input) or cs.ALL_CONFIGS
    runs_all = [(r, b) for b, rs in by_bench.items() for r, _ in rs]
    geometry = {}
    for cfg in configs:
        rows, _ = cs.geometry(cfg, runs_all)
        g = {row[0]: f"{row[5]}x{row[6]}" for row in rows}
        geometry[cfg] = f"{g.get('L1D', '?')} / {g.get('L2', '?')}"
    engine = shutil.which("tectonic")
    for bench, runs in sorted(by_bench.items()):
        if args.bench and bench not in args.bench:
            continue
        sections = [run_section(rid, desc, {cfg: cs.run_record(cfg, rid, bench) for cfg in configs},
                                geometry) for rid, desc in runs]
        outdir = (args.out / bench) if args.out else cs.ROOT / "benchmarks" / bench / args.input / "report"
        outdir.mkdir(parents=True, exist_ok=True)
        tex_path = outdir / f"{bench}_{args.input}{'_simpoint' if args.simpoint else ''}.tex"
        tex_path.write_text(document(bench, args.input, sections, args.schema, args.simpoint))
        pdf = ""
        if engine and not args.no_pdf:
            r = subprocess.run([engine, "--outdir", str(outdir), str(tex_path)],
                               capture_output=True, text=True)
            pdf = " + pdf" if r.returncode == 0 else " (pdf FAILED)"
        print(f"{bench:10s} {args.input}: {len(runs)} run(s) -> {tex_path.relative_to(cs.ROOT) if not args.out else tex_path}{pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
