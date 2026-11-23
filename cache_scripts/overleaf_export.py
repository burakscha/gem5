#!/usr/bin/env python3
"""Export the metric-schema-10 results as an Overleaf-ready folder of LaTeX
reports (source and PDF), in the layout and author block of the counter
reference (general_reports/definitions/counter_reference_schema10.tex):

    overleaf_schema10/
      README.md                          what is where, how to open it in Overleaf
      counter_reference_schema10.tex/pdf every counter and formula
      overall_test.tex/pdf               test input: every run, every configuration
      overall_ref_simpoint.tex/pdf       ref input (SimPoint estimates): the same
      overall_test_vs_ref.tex/pdf        per benchmark: test against ref
      <benchmark>/<benchmark>_test.tex/pdf, _ref_simpoint, _train
                                         one benchmark, one input, all configurations

A benchmark's report of an input is written only when every run of the
benchmark has finished in every configuration (train is still running); run
the script again to add the rest. Only ASCII goes into the LaTeX sources
(Turkish letters as accent commands), so they compile with pdfLaTeX on
Overleaf as well as with tectonic here.

    cache_scripts/overleaf_export.py
    cache_scripts/overleaf_export.py --out DIR --no-pdf
"""

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_status as cs  # noqa: E402
import input_report as ir  # noqa: E402

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
# (input, SimPoint, file tag, label)
INPUTS = [("test", False, "test", "test"), ("ref", True, "ref_simpoint", "ref (SimPoint)"),
          ("train", False, "train", "train")]
SIMPOINT_NOTE = (r"Ref values are SimPoint estimates: per run up to 30 simulation points of "
                 r"100M instructions, each after a 500M-instruction warmup, weighted by SimPoint; "
                 r"a counter of the whole ROI is $N \cdot \sum_i w_i c_i / n_i \,/\, \sum_i w_i$ "
                 r"($N$ the ROI length from the qemu profile, $n_i$ and $c_i$ the instructions and "
                 r"the counter of point $i$, $w_i$ its weight).")
DASH = ir.DASH


def descriptions(inp: str) -> dict[str, str]:
    """run ID -> the runner's description of its input (e.g. 'inp.in')."""
    out = subprocess.run([str(cs.RUNNER), "list", inp], capture_output=True, text=True,
                         check=True).stdout.splitlines()[2:]
    desc = {}
    for line in out:
        f = line.split(None, 3)
        if len(f) >= 3:
            desc[f[0]] = f[3] if len(f) > 3 else ""
    return desc


def complete(data: dict, i: int) -> bool:
    return all(ir.done(data["records"][c][i]) for c in ir.CONFIGS)


def bench_runs(data: dict, bench: str) -> list[int]:
    return [i for i, (_, b) in enumerate(data["runs"]) if b == bench]


def table(spec: str, header: list[str], rows: list[str], foot: list[str] | None = None,
          pre: str = "") -> str:
    return ir.longtable(spec, header, rows, foot or [], pre_header=pre)


def config_rows(data: dict) -> str:
    rows = []
    for c in ir.CONFIGS:
        g = data["geometry"][c]
        rows.append(rf"\ct{{{c}}} & {ir.geometry_cell(g.get('L1D'))} & "
                    rf"{ir.geometry_cell(g.get('L2'))} \\")
    return "\n".join(rows)


# --------------------------------------------------------------------------
# One benchmark, one input
# --------------------------------------------------------------------------
def bench_report(data: dict, bench: str, inp: str, simpoint: bool, label: str,
                 desc: dict[str, str], stamp: str) -> str:
    idx = bench_runs(data, bench)
    spec = SPEC_NAMES.get(bench, bench)
    multi = len(idx) > 1
    runs_text = ", ".join(rf"\ct{{{ir.tex(data['runs'][i][0])}}} ({ir.tex(desc.get(data['runs'][i][0], ''))})"
                          for i in idx)

    # Table 1: counts, Table 2: ratios (from the reference configuration).
    keys = ["total_insts", "roi_total_insts", "roi_load", "roi_store", "roi_spill_store",
            "roi_spill_event", "roi_spill_load"]
    count_rows, ratio_rows, fracs = [], [], []
    sums = {k: 0 for k in keys}
    ratio_keys = [name for name, _, _ in cs.RATIOS]
    for i in idx:
        rid = data["runs"][i][0]
        c = cs.counts(ir.program_record(data, i))
        for k in keys:
            sums[k] += c[k]
        count_rows.append(" & ".join([ir.tex(rid), *(ir.mio(c[k]) for k in keys)]) + r" \\")
        f = {name: (c[a], c[b]) for name, a, b in cs.RATIOS}
        fracs.append(f)
        ratio_rows.append(" & ".join([ir.tex(rid), *(ir.pc(*f[k]) for k in ratio_keys)]) + r" \\")
    count_foot = [" & ".join(["total", *(ir.mio(sums[k]) for k in keys)]) + r" \\"] if multi else []
    ratio_foot = []
    if multi:
        pooled, _ = ir.pooled_mean(fracs, ratio_keys)
        ratio_foot = [" & ".join(["pooled", *pooled]) + r" \\"]
    count_head = ["run", ir.hd("total", "insts"), ir.hd("ROI", "insts"), ir.hd("ROI", "load"),
                  ir.hd("ROI", "store"), ir.hd("spill", "store"), ir.hd("spill", "event"),
                  ir.hd("spill", "load")]
    count_notes = [
        ("total insts", "The whole simulation" + (" (whole program, from the qemu profile)"
                                                  if simpoint else "") + " " + ir.tr("tüm simülasyon") + "."),
        ("ROI insts, load, store", r"Only between \ct{m5\_work\_begin} and \ct{m5\_work\_end} "
         + ir.tr("sadece ROI içinde") + "."),
        ("spill store", r"\ct{roi\_spill\_store}: stores inside the ROI to the process stack, "
         "not atomic, no fault; read back or not "
         + ir.tr("spill koşullarını sağlayan store'lar, geri okunsun okunmasın") + "."),
        ("spill event", r"\ct{roi\_spill\_event}: spill stores read back at least once; one per "
         "store " + ir.tr("en az bir kez geri okunan spill store'lar") + "."),
        ("spill load", r"\ct{roi\_spill\_load}: loads that read a spill store back; repeats "
         "count " + ir.tr("spill store'u geri okuyan load'lar, tekrarlar dahil") + "."),
    ] + ([("total", "Sum over the runs " + ir.tr("koşuların toplamı") + ".")] if multi else [])

    # Table 4: miss rates, one block of five configurations per run.
    n1, n2 = len(ir.L1_KEYS), len(ir.L2_KEYS)
    miss_rows = []
    per_cfg = {c: [] for c in ir.CONFIGS}
    for k, i in enumerate(idx):
        rid = data["runs"][i][0]
        if multi:
            if k:
                miss_rows.append(r"\midrule")
            miss_rows.append(rf"\multicolumn{{{n1 + n2 + 1}}}{{@{{}}l}}{{\textbf{{{ir.tex(rid)}}}}} \\")
        for c in ir.CONFIGS:
            f = cs.miss_fractions(data["records"][c][i])
            per_cfg[c].append(f)
            miss_rows.append(" & ".join([rf"\ct{{{ir.short(c)}}}",
                                         *(ir.pc(*f[key]) for key in ir.L1_KEYS + ir.L2_KEYS)]) + r" \\")
    if multi:
        miss_rows.append(r"\midrule")
        miss_rows.append(rf"\multicolumn{{{n1 + n2 + 1}}}{{@{{}}l}}{{\textbf{{all runs, pooled}}}} \\")
        for c in ir.CONFIGS:
            pooled, _ = ir.pooled_mean(per_cfg[c], ir.L1_KEYS + ir.L2_KEYS)
            miss_rows.append(" & ".join([rf"\ct{{{ir.short(c)}}}", *pooled]) + r" \\")
    pre = (rf"& \multicolumn{{{n1}}}{{c}}{{\textbf{{L1D miss rate (\%)}}}} & "
           rf"\multicolumn{{{n2}}}{{c}}{{\textbf{{L2 local miss rate (\%)}}}} \\" + "\n"
           rf"\cmidrule(lr){{2-{n1 + 1}}}\cmidrule(l){{{n1 + 2}-{n1 + n2 + 1}}}")
    miss_notes = ([("dm ... fa", "The five configurations, from direct-mapped to fully "
                    "associative (Table 3) " + ir.tr("konfigürasyonlar") + ".")]
                  + ir.MISS_NOTES
                  + ([("all runs, pooled", r"$\sum$ misses $/ \sum$ accesses over the runs "
                       + ir.tr("koşular birlikte") + ".")] if multi else [])
                  + [(DASH, "No access of that kind " + ir.tr("o türde access yok") + ".")])

    return rf"""
\section{{{ir.tex(spec)}, \ct{{{inp}}} input}}

This report gives the register-spill behaviour and the cache miss rates of
\ct{{{ir.tex(spec)}}} for the SPEC CPU2017 \ct{{{inp}}} input
({len(idx)} run{'s' if multi else ''}: {runs_text}) under five cache
configurations of equal capacity (L1D 4~KiB, L1I 32~KiB, L2 32~KiB, 64~B lines,
LRU); only the organisation of L1D and L2 changes. Spills are detected from
runtime effective addresses alone (metric schema 10, spill-like memory traffic
\trgloss{{derleyicinin spill kodu olmak zorunda değil}}); every counter and
formula is defined in \ct{{counter\_reference\_schema10.pdf}}. {SIMPOINT_NOTE if simpoint else ''}
Data as of {stamp}.

Tables 1 and 2 describe the program and do not depend on the cache
\trgloss{{cache'ten bağımsız}}; they show the values of \ct{{{ir.REFERENCE}}}.
Table 4 gives the miss rates of every configuration.

\tablehead{{1}}{{Instruction counts, in millions \trgloss{{milyon komut}}.}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.6pt}}
{table("@{}l" + "r" * len(keys) + "@{}", count_head, count_rows, count_foot)}}}
{ir.notes(count_notes)}
\tablehead{{2}}{{Program ratios, in percent ($\times 100$).}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.6pt}}
{table("@{}l" + "r" * len(ratio_keys) + "@{}", ["run", *(ir.hd(*ir.RATIO_HEAD[k]) for k in ratio_keys)], ratio_rows, ratio_foot)}}}
{ir.notes(ir.RATIO_NOTES + ([("pooled", r"$\sum$ numerators $/ \sum$ denominators over the runs "
                                          + ir.tr("koşular birlikte") + ".")] if multi else []))}
\tablehead{{3}}{{Cache configurations \trgloss{{cache konfigürasyonları}}; L1I is the same
everywhere: {ir.geometry_cell(data["geometry"][ir.REFERENCE].get("L1I"))}.}}

{{\small
\begin{{tabularx}}{{\textwidth}}{{@{{}}l >{{\raggedright\arraybackslash}}X >{{\raggedright\arraybackslash}}X@{{}}}}
\toprule
\textbf{{Configuration}} & \textbf{{L1D}} & \textbf{{L2}} \\
\midrule
{config_rows(data)}
\bottomrule
\end{{tabularx}}
}}

\tablehead{{4}}{{Miss rates by configuration, in percent of the accesses
\trgloss{{access'lerin yüzdesi}}.}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.4pt}}\renewcommand{{\arraystretch}}{{1.05}}
{table("@{}l" + "r" * (n1 + n2) + "@{}", ["config", *ir.L1_HEAD, *ir.L2_HEAD], miss_rows, None, pre)}}}
{ir.notes(miss_notes)}"""


# --------------------------------------------------------------------------
# test against ref, per benchmark
# --------------------------------------------------------------------------
CMP_RATIOS = ["spill/roi", "spill_load/load", "spill_store/store", "spill_event/spill_store",
              "spill/mem"]
CMP_MISS = [("L1D_miss", ("L1D", "all")), ("spill_ld_L1miss", ("spill", "ld")),
            ("other_ld_L1miss", ("other", "ld")), ("spill_st_L1miss", ("spill", "st")),
            ("L2_local_miss", ("L2", "all"))]


def by_bench(data: dict, fn) -> dict[str, dict]:
    """benchmark -> pooled (numerator, denominator) of fn(record, i) over its
    runs, for the benchmarks whose runs all finished."""
    out = {}
    for bench in dict.fromkeys(b for _, b in data["runs"]):
        idx = bench_runs(data, bench)
        if not all(complete(data, i) for i in idx):
            continue
        parts = [fn(i) for i in idx]
        out[bench] = {k: (sum(p[k][0] for p in parts), sum(p[k][1] for p in parts))
                      for k in parts[0]}
    return out


def comparison_report(test: dict, ref: dict, stamp: str) -> str:
    def prog(data):
        def fn(i):
            c = cs.counts(ir.program_record(data, i))
            return {name: (c[a], c[b]) for name, a, b in cs.RATIOS}
        return by_bench(data, fn)

    pt, pr = prog(test), prog(ref)
    benches = [b for b in dict.fromkeys(b for _, b in test["runs"]) if b in pt and b in pr]

    def pair_rows(t, r, keys):
        rows = []
        for b in benches:
            cells = []
            for k in keys:
                cells += [ir.pc(*t[b][k]), ir.pc(*r[b][k])]
            rows.append(" & ".join([rf"\ct{{{ir.tex(b)}}}", *cells]) + r" \\")
        pooled_cells, mean_cells = [], []
        for k in keys:
            for side in (t, r):
                fr = [side[b] for b in benches]
                p, m = ir.pooled_mean(fr, [k])
                pooled_cells += p
                mean_cells += m
        foot = [" & ".join(["pooled", *pooled_cells]) + r" \\",
                " & ".join([f"mean ({len(benches)})", *mean_cells]) + r" \\"]
        return rows, foot

    def head(names):
        n = len(names)
        pre = " & ".join([""] + [rf"\multicolumn{{2}}{{c}}{{{ir.hd(*h)}}}" for h in names]) + r" \\" + "\n"
        pre += "".join(rf"\cmidrule(lr){{{2 + 2 * j}-{3 + 2 * j}}}" for j in range(n))
        return pre, ["benchmark"] + ["test", "ref"] * n

    rows, foot = pair_rows(pt, pr, CMP_RATIOS)
    pre, hdr = head([ir.RATIO_HEAD[k] for k in CMP_RATIOS])
    parts = [rf"""
\section{{Test against ref, per benchmark}}

Each value pools all runs of a benchmark in that input ($\sum$ numerators
$/ \sum$ denominators): the inputs have different runs (\ct{{xz}}: 12 test
runs, 3 ref runs). Test values come from full simulations, ref values are
SimPoint estimates. {SIMPOINT_NOTE} Only benchmarks that finished in both
inputs and all five configurations are shown ({len(benches)}). Data as of {stamp}.
The program ratios do not depend on the cache; the miss rates are given per
configuration \trgloss{{test ve ref girdilerinin benchmark bazında karşılaştırması}}.

\tablehead{{1}}{{Program ratios, test against ref, in percent.}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.2pt}}
{table("@{}l" + "r" * (2 * len(CMP_RATIOS)) + "@{}", hdr, rows, foot, pre)}}}
{ir.notes([n for n in ir.RATIO_NOTES if n[0] in ("spill/roi", "spill ld/load", "spill st/store", "spill ev/spill st", "spill/mem")] + ir.POOL_NOTES[:1] + [("mean", "Average of the benchmark values: every benchmark weighs the same " + ir.tr("benchmark değerlerinin ortalaması") + ".")])}"""]
    for n, cfg in enumerate(ir.CONFIGS, start=2):
        def miss(data, cfg=cfg):
            return by_bench(data, lambda i: cs.miss_fractions(data["records"][cfg][i]))
        mt, mr = miss(test), miss(ref)
        keys = [k for k, _ in CMP_MISS]
        rows, foot = pair_rows(mt, mr, keys)
        pre, hdr = head([h for _, h in CMP_MISS])
        parts.append(rf"""
\clearpage
\subsection*{{\ct{{{cfg}}}}}
L1D: {ir.geometry_cell(test["geometry"][cfg].get("L1D"))}; L2: {ir.geometry_cell(test["geometry"][cfg].get("L2"))}.\par
\tablehead{{{n}}}{{Miss rates of \ct{{{cfg}}}, test against ref, in percent of the accesses
\trgloss{{access'lerin yüzdesi}}.}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.2pt}}
{table("@{}l" + "r" * (2 * len(keys)) + "@{}", hdr, rows, foot, pre)}}}
{ir.notes([n for n in ir.MISS_NOTES if n[0] in ("L1D: all", "spill ld", "other ld", "spill st", "L2 local: all")] + ir.POOL_NOTES[:1] + [("mean", "Average of the benchmark values " + ir.tr("benchmark değerlerinin ortalaması") + ".")])}""")
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
STAMP = re.compile(r"Data as of \d{4}-\d{2}-\d{2} \d{2}:\d{2}\.")


def write(path: Path, text: str, engine: str | None, log: list[str]) -> None:
    """Write a report and compile it, unless only its 'Data as of' stamp would
    change: then the file and its PDF are kept, so a refresh touches only the
    reports whose numbers changed."""
    text = ir.to_ascii(text)
    if (path.exists() and (path.with_suffix(".pdf").exists() or not engine)
            and STAMP.sub("", path.read_text()) == STAMP.sub("", text)):
        log.append(f"{path}: unchanged, kept")
        return
    path.write_text(text)
    status = "tex"
    if engine:
        r = subprocess.run([engine, "--outdir", str(path.parent), str(path)],
                           capture_output=True, text=True)
        status = "tex + pdf" if r.returncode == 0 else "tex, PDF FAILED"
        if r.returncode:
            print(r.stderr[-2000:], file=sys.stderr)
    log.append(f"{path}: {status}")


def readme(out: Path, made: dict[str, list[str]], missing: dict[str, list[str]], stamp: str) -> str:
    lines = [
        "# Register-spill results, metric schema 10 (Overleaf export)",
        "",
        f"Exported {stamp} by `cache_scripts/overleaf_export.py`; run it again to refresh.",
        "Every `.tex` file is a standalone document (pdfLaTeX or XeLaTeX) next to its PDF.",
        "",
        "In Overleaf: New Project -> Upload Project -> the zip of this folder. Overleaf",
        "compiles one main document at a time; choose it under Menu -> Main document.",
        "",
        "| File | Content |",
        "|---|---|",
        "| `counter_reference_schema10` | every counter, formula and spill condition, with a worked example |",
        "| `overall_test` | test input: program counters and ratios of every run, miss rates per configuration, a two-benchmark comparison |",
        "| `overall_ref_simpoint` | ref input (SimPoint estimates): the same |",
        "| `overall_test_vs_ref` | per benchmark, test against ref: program ratios and miss rates of every configuration |",
        "| `<benchmark>/<benchmark>_<input>` | one benchmark and input: counts, ratios, configurations, miss rates of all five configurations |",
        "",
        "Benchmark reports:",
        "",
        "| Input | Benchmarks |",
        "|---|---|",
    ]
    for tag, benches in made.items():
        lines.append(f"| {tag} | {len(benches)}: {', '.join(benches)} |")
    if any(missing.values()):
        lines += ["", "Not yet (a run of the benchmark has not finished in every configuration):", ""]
        for tag, benches in missing.items():
            if benches:
                lines.append(f"- {tag}: {', '.join(benches)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=cs.ROOT / "overleaf_schema10")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    engine = None if args.no_pdf else shutil.which("tectonic")
    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
    log: list[str] = []

    data = {}
    for inp, simpoint, tag, _ in INPUTS:
        data[tag] = ir.collect(inp, simpoint)
    made = {tag: [] for _, _, tag, _ in INPUTS}
    missing = {tag: [] for _, _, tag, _ in INPUTS}

    # Per benchmark and input.
    for inp, simpoint, tag, label in INPUTS:
        d = data[tag]
        desc = descriptions(inp)
        for bench in dict.fromkeys(b for _, b in d["runs"]):
            if not all(complete(d, i) for i in bench_runs(d, bench)):
                missing[tag].append(bench)
                continue
            bdir = out / bench
            bdir.mkdir(exist_ok=True)
            spec = ir.tex(SPEC_NAMES.get(bench, bench))
            sub = (f"{spec}: Spill Ratios and Cache Miss Rates, \\texttt{{{inp}}} input"
                   + (", SimPoint estimates" if simpoint else ""))
            write(bdir / f"{bench}_{tag}.tex",
                  ir.document(inp, simpoint, bench_report(d, bench, inp, simpoint, label, desc, stamp), sub),
                  engine, log)
            made[tag].append(bench)

    # Overall reports: one per complete input, and test against ref.
    for inp, simpoint, tag, _ in INPUTS:
        d = data[tag]
        if not all(complete(d, i) for i in range(len(d["runs"]))):
            continue
        sp = ir.spread(d)
        body = "\n".join([
            ir.overview(d, inp, simpoint, stamp),
            ir.program_counts(d, sp),
            r"\section{Program ratios}" + "\n\nThese, too, do not depend on the cache "
            r"\trgloss{cache'ten bağımsız}." + "\n" + ir.program_ratios(d),
            ir.cache_section(d),
            ir.comparison(d, ["cactuBSSN", "parest"], inp),
        ])
        write(out / f"overall_{tag}.tex", ir.document(inp, simpoint, body), engine, log)
    write(out / "overall_test_vs_ref.tex",
          ir.document("test", False, comparison_report(data["test"], data["ref_simpoint"], stamp),
                      "Results: SPEC CPU2017 \\texttt{test} Input against \\texttt{ref} "
                      "(SimPoint), per Benchmark"),
          engine, log)

    # The counter reference, as it is in the repository.
    ref_dir = cs.ROOT / "general_reports" / "definitions"
    for ext in ("tex", "pdf"):
        shutil.copy2(ref_dir / f"counter_reference_schema10.{ext}", out)
    log.append(f"{out / 'counter_reference_schema10.tex'}: copied with its PDF")

    (out / "README.md").write_text(readme(out, made, missing, stamp))

    # A zip of the folder for Overleaf's "Upload Project".
    zpath = out.parent / f"{out.name}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out.parent))
    print("\n".join(log))
    print(f"\n{len(log)} files; zip for Overleaf: {zpath}")
    failed = [line for line in log if "FAILED" in line]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
