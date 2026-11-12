#!/usr/bin/env python3
"""Results report of one input set (metric schema 10): spill ratios and the
cache miss rates of every configuration, in the layout of the counter
reference (general_reports/definitions/counter_reference_schema10.tex).

It writes report.tex (and report.pdf) with
  - the cache configurations and which runs are still missing;
  - the program counters and ratios of every run, once: they do not depend
    on the cache (the script measures how far the configurations differ);
  - one miss-rate table per configuration, from the least to the most
    associative;
  - a last page comparing two benchmarks over the configurations.
Every table has its formulas and explanations under it, with Turkish
glosses in parentheses. Only completed runs give numbers, so the report
can be rebuilt at any time.

    cache_scripts/input_report.py                       (test input)
    cache_scripts/input_report.py --input train
    cache_scripts/input_report.py --input ref --simpoint
    cache_scripts/input_report.py --compare leela mcf --out DIR --no-pdf
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_status as cs  # noqa: E402

# From the least to the most associative.
CONFIGS = ["small-dm", "small-2way", "small-4way", "small-8way", "small-fa"]
REFERENCE = "small-2way"   # the program tables show this configuration's values
DASH = r"\textemdash"
TEX_ESCAPE = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
              "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
              "^": r"\textasciicircum{}"}
# The T1 Latin Modern fonts take the Turkish letters only as accent commands.
TURKISH = {"ş": r"\c{s}", "Ş": r"\c{S}", "ğ": r"\u{g}", "Ğ": r"\u{G}", "ı": r"{\i}",
           "İ": r"\.{I}", "ö": r'\"o', "Ö": r'\"O', "ü": r'\"u', "Ü": r'\"U',
           "ç": r"\c{c}", "Ç": r"\c{C}", "â": r"\^a"}
INPUT_TITLE = {"test": "test", "train": "train", "ref": "ref"}


def tex(s) -> str:
    return "".join(TEX_ESCAPE.get(ch, ch) for ch in str(s))


def tr(s: str) -> str:
    """A Turkish gloss, in parentheses and italics."""
    return rf"(\textit{{{s}}})"


def hd(*lines: str) -> str:
    """A table header cell of several short lines."""
    return r"\begin{tabular}[b]{@{}c@{}}" + r"\\".join(lines) + r"\end{tabular}"


def pc(part, whole) -> str:
    return DASH if part is None or not whole else f"{100.0 * part / whole:.2f}"


def mio(v) -> str:
    return DASH if v is None else f"{v / 1e6:,.1f}"


def short(cfg: str) -> str:
    return cfg.replace("small-", "")


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def collect(inp: str, simpoint: bool) -> dict:
    cs.use_schema(10)
    cs.PROFILE, cs.SIMPOINT = inp, simpoint
    runs = cs.workloads()
    records = {c: [cs.run_record(c, rid, b) for rid, b in runs] for c in CONFIGS}
    geometry = {}
    for c in CONFIGS:
        rows, _ = cs.geometry(c, runs)
        geometry[c] = {row[0]: row for row in rows}
    return {"runs": runs, "records": records, "geometry": geometry}


def done(r: dict) -> bool:
    return r["state"] == "COMPLETED"


def program_record(data: dict, i: int) -> dict | None:
    """The run's values from the reference configuration, else the first
    configuration that completed it."""
    recs = data["records"]
    for c in [REFERENCE, *CONFIGS]:
        if done(recs[c][i]):
            return recs[c][i]
    return None


def spread(data: dict) -> dict:
    """How far the program counters differ between the configurations."""
    same, differ, rel, pts, worst = 0, [], 0.0, 0.0, ("", "")
    for i, (rid, _) in enumerate(data["runs"]):
        rs = [data["records"][c][i] for c in CONFIGS if done(data["records"][c][i])]
        if len(rs) < 2:
            continue
        cnts = [cs.counts(r) for r in rs]
        if len({tuple(c[k] for k in cs.COUNT_COLUMNS) for c in cnts}) == 1:
            same += 1
            continue
        differ.append(rid)
        tot = [c["total_insts"] for c in cnts]
        rel = max(rel, (max(tot) - min(tot)) / max(tot))
        for name, a, b in cs.RATIOS:
            vals = [100.0 * c[a] / c[b] for c in cnts if c[b]]
            if vals and max(vals) - min(vals) > pts:
                pts, worst = max(vals) - min(vals), (rid, name)
    return {"same": same, "differ": differ, "rel": rel, "pts": pts, "worst": worst}


# --------------------------------------------------------------------------
# LaTeX pieces
# --------------------------------------------------------------------------
def longtable(spec: str, header: list[str], rows: list[str], foot: list[str],
              pre_header: str = "") -> str:
    head = (pre_header + "\n" if pre_header else "") + " & ".join(header) + r" \\"
    tail = ("\\midrule\n" + "\n".join(foot) + "\n") if foot else ""
    return (f"\\begin{{longtable}}{{{spec}}}\n\\toprule\n{head}\n\\midrule\n\\endfirsthead\n"
            f"\\toprule\n{head}\n\\midrule\n\\endhead\n\\bottomrule\n\\endlastfoot\n"
            + "\n".join(rows) + "\n" + tail + "\\end{longtable}\n")


def notes(items: list[tuple[str, str]]) -> str:
    """The explanation block under a table: name, text."""
    body = "\n".join(rf"{name} & {text} \\" for name, text in items)
    return ("{\\footnotesize\\renewcommand{\\arraystretch}{1.0}\n"
            "\\begin{tabularx}{\\textwidth}{@{}>{\\raggedright\\arraybackslash}p{27mm} "
            ">{\\raggedright\\arraybackslash}X@{}}\n" + body + "\n\\end{tabularx}\\par}\n")


POOL_NOTES = [
    ("pooled", r"$\sum$ numerators $/ \sum$ denominators over the completed runs: large runs "
               "dominate " + tr("bütün koşular birlikte; büyük koşular baskın") + "."),
    ("mean", "Average of the per-run percentages: every run weighs the same "
             + tr("koşu değerlerinin ortalaması; her koşu eşit ağırlıkta") + "."),
]


def pooled_mean(fracs: list[dict], keys: list[str]) -> tuple[list[str], list[str]]:
    pooled, mean = [], []
    for k in keys:
        pooled.append(pc(sum(f[k][0] for f in fracs), sum(f[k][1] for f in fracs)))
        vals = [100.0 * f[k][0] / f[k][1] for f in fracs if f[k][1]]
        mean.append(f"{sum(vals) / len(vals):.2f}" if vals else DASH)
    return pooled, mean


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------
def geometry_cell(row: list[str] | None) -> str:
    if not row:
        return DASH
    _, size, _, lines, organisation, sets, ways, _, policy = row
    if sets == "1":
        text = f"{size}, fully associative ({lines} lines), {policy}"
    elif ways == "1":
        text = f"{size}, direct-mapped ({sets} sets)"
    else:
        text = f"{size}, {organisation} ({sets} sets), {policy}"
    return tex(text)


def overview(data: dict, inp: str, simpoint: bool, stamp: str) -> str:
    runs, recs = data["runs"], data["records"]
    rows = []
    for c in CONFIGS:
        g = data["geometry"][c]
        n = sum(done(r) for r in recs[c])
        rows.append(" & ".join([rf"\ct{{{c}}}", geometry_cell(g.get("L1D")),
                                geometry_cell(g.get("L2")), f"{n} / {len(runs)}"]) + r" \\")
    missing = []
    for i, (rid, _) in enumerate(runs):
        states = {c: recs[c][i]["state"].lower() for c in CONFIGS if not done(recs[c][i])}
        if states:
            kinds = sorted(set(states.values()))
            where = ("all configurations" if len(states) == len(CONFIGS)
                     else ", ".join(short(c) for c in states))
            missing.append(rf"\ct{{{tex(rid)}}} ({'/'.join(kinds)} in {where})")
    l1i = geometry_cell(data["geometry"][REFERENCE].get("L1I"))
    source = ("SimPoint estimates of the full runs (\\ct{cache\\_scripts/simpoint.sh})"
              if simpoint else "full simulations of every run")
    pending = ("Not finished yet, shown as " + DASH + ": " + "; ".join(missing) + "."
               if missing else "Every run has finished.")
    return rf"""
\section{{Overview}}

This report gives the results of the SPEC CPU2017 \ct{{{inp}}} input ({source})
with metric schema 10: spills are detected from runtime effective addresses
alone (runtime-detected stack store--load reuse, spill-like memory traffic;
\textit{{derleyicinin spill kodu olmak zorunda değil}}). Every counter and
formula is defined in \ct{{counter\_reference\_schema10.pdf}}
(\ct{{general\_reports/definitions/}}). Data as of {stamp}.

The same program runs on five cache configurations of equal capacity (L1D
4~KiB, L2 32~KiB, 64~B lines); only the organisation changes. The L1I is the
same everywhere: {l1i}.

\tablehead{{1}}{{Cache configurations, from the least to the most associative
\trgloss{{en az ilişkiliden en çok ilişkiliye}}.}}

{{\small
\begin{{tabularx}}{{\textwidth}}{{@{{}}l X X r@{{}}}}
\toprule
\textbf{{Configuration}} & \textbf{{L1D}} & \textbf{{L2}} & \textbf{{Runs done}} \\
\midrule
{chr(10).join(rows)}
\bottomrule
\end{{tabularx}}
}}

{pending}

How the report is built: Tables 2 and 3 describe the program and do not depend
on the cache, so they are shown once. Tables 4--8 give the miss rates, one table
per configuration. The last page compares two benchmarks across the
configurations. All ratios are percentages: 18.45 means 18.45 of every 100
\trgloss{{yüzde değerler}}.
"""


def program_counts(data: dict, sp: dict) -> str:
    runs = data["runs"]
    keys = cs.COUNT_COLUMNS
    rows, sums = [], {k: 0 for k in keys}
    for i, (rid, _) in enumerate(runs):
        r = program_record(data, i)
        if r is None:
            rows.append(" & ".join([tex(rid), *([DASH] * len(keys))]) + r" \\")
            continue
        c = cs.counts(r)
        for k in keys:
            sums[k] += c[k]
        rows.append(" & ".join([tex(rid), *(mio(c[k]) for k in keys)]) + r" \\")
    header = ["run", hd("total", "insts"), hd("total", "load"), hd("total", "store"),
              hd("ROI", "insts"), hd("ROI", "load"), hd("ROI", "store"),
              hd("spill", "store"), hd("spill", "event"), hd("spill", "load")]
    foot = [" & ".join(["total", *(mio(sums[k]) for k in keys)]) + r" \\"]
    differ = sp["differ"]
    if differ:
        identity = (f"In {sp['same']} runs the counters are identical in all five "
                    f"configurations. In {len(differ)} runs "
                    f"({', '.join(rf'{chr(92)}ct{{{tex(d)}}}' for d in differ)}) they differ "
                    f"by at most {sp['rel']:.1e} of the instructions; no ratio of Table 3 "
                    f"moves by more than {sp['pts']:.3f} percentage points, below the two "
                    "decimals shown. The likely causes are the run paths, whose length "
                    "depends on the configuration name and which the program sees in its "
                    "arguments, and the simulated time that some programs read.")
    else:
        identity = "The counters are identical in all five configurations."
    return rf"""
\section{{Program counters}}

The program counters do not depend on the cache \trgloss{{cache'ten bağımsız}}.
Tables 2 and 3 show the values of \ct{{{REFERENCE}}}. {identity}

\tablehead{{2}}{{Instruction counts, in millions \trgloss{{milyon komut}}.}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.2pt}}
{longtable("@{}l" + "r" * len(keys) + "@{}", header, rows, foot)}}}
{notes([
    ("total insts, load, store", "The whole simulation: every committed instruction, load, "
     "store " + tr("tüm simülasyon") + "."),
    ("ROI insts, load, store", r"Only between \ct{m5\_work\_begin} and \ct{m5\_work\_end} "
     + tr("sadece ROI içinde") + ". LR counts as a load and SC as a store; an AMO is "
     "neither."),
    ("spill store", r"\ct{roi\_spill\_store}: stores inside the ROI to the process stack, "
     "not atomic, no fault; read back or not "
     + tr("spill koşullarını sağlayan store'lar, geri okunsun okunmasın") + "."),
    ("spill event", r"\ct{roi\_spill\_event}: spill stores read back at least once; one per "
     "store, at its first reload " + tr("en az bir kez geri okunan spill store'lar") + "."),
    ("spill load", r"\ct{roi\_spill\_load}: loads that read a spill store back; repeats "
     "count, so it can exceed the events "
     + tr("spill store'u geri okuyan load'lar, tekrarlar dahil") + "."),
    ("total", "Sum over the completed runs " + tr("tamamlanan koşuların toplamı") + "."),
])}"""


RATIO_HEAD = {
    "roi/total": ("roi/", "total"), "load/roi": ("load/", "roi"), "store/roi": ("store/", "roi"),
    "spill/roi": ("spill/", "roi"), "spill_load/load": ("spill ld/", "load"),
    "spill_store/store": ("spill st/", "store"), "spill_event/store": ("spill ev/", "store"),
    "spill_event/spill_store": ("spill ev/", "spill st"), "spill/mem": ("spill/", "mem"),
}
RATIO_NOTES = [
    ("roi/total", r"\ct{roi\_total\_insts} / \ct{total\_insts}: share of the program that "
     "was measured " + tr("programın ne kadarı ölçüldü") + "."),
    ("load/roi", r"\ct{roi\_load} / \ct{roi\_total\_insts}: loads among the ROI instructions "
     + tr("ROI komutlarının yüzde kaçı load") + "."),
    ("store/roi", r"\ct{roi\_store} / \ct{roi\_total\_insts}: stores among the ROI "
     "instructions " + tr("yüzde kaçı store") + "."),
    ("spill/roi", r"(\ct{roi\_spill\_load} $+$ \ct{roi\_spill\_store}) / "
     r"\ct{roi\_total\_insts}: \textbf{the main metric}, spill-like instructions "
     + tr("ana metrik: stack'e yazma veya stack'ten geri okuma payı") + "."),
    ("spill ld/load", r"\ct{roi\_spill\_load} / \ct{roi\_load}: loads that read a stack-written "
     "value back " + tr("load'ların yüzde kaçı stack'ten geri okuma") + "."),
    ("spill st/store", r"\ct{roi\_spill\_store} / \ct{roi\_store}: stores to the stack, read "
     "back or not " + tr("store'ların yüzde kaçı stack'e") + "."),
    ("spill ev/store", r"\ct{roi\_spill\_event} / \ct{roi\_store}: stores whose value is read "
     "later " + tr("store'ların yüzde kaçı sonra okunan değer") + "."),
    ("spill ev/spill st", r"\ct{roi\_spill\_event} / \ct{roi\_spill\_store}: reuse rate of the "
     "stack writes " + tr("stack'e yazılanların yüzde kaçı geri kullanıldı") + "."),
    ("spill/mem", r"(\ct{roi\_spill\_load} $+$ \ct{roi\_spill\_store}) / (\ct{roi\_load} $+$ "
     r"\ct{roi\_store}): spill-like share of the memory instructions "
     + tr("bellek trafiğinin yüzde kaçı spill-like") + "."),
]


def program_ratios(data: dict) -> str:
    runs = data["runs"]
    rows, fracs = [], []
    keys = [name for name, _, _ in cs.RATIOS]
    for i, (rid, _) in enumerate(runs):
        r = program_record(data, i)
        if r is None:
            rows.append(" & ".join([tex(rid), *([DASH] * len(keys))]) + r" \\")
            continue
        c = cs.counts(r)
        f = {name: (c[a], c[b]) for name, a, b in cs.RATIOS}
        fracs.append(f)
        rows.append(" & ".join([tex(rid), *(pc(*f[k]) for k in keys)]) + r" \\")
    pooled, mean = pooled_mean(fracs, keys)
    foot = [" & ".join(["pooled", *pooled]) + r" \\", " & ".join(["mean", *mean]) + r" \\"]
    header = ["run", *(hd(*RATIO_HEAD[k]) for k in keys)]
    return rf"""
\tablehead{{3}}{{Program ratios, in percent ($\times 100$).}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.6pt}}
{longtable("@{}l" + "r" * len(keys) + "@{}", header, rows, foot)}}}
{notes(RATIO_NOTES + POOL_NOTES)}"""


L1_KEYS = ["L1D_miss", "spill_ld_L1miss", "other_ld_L1miss", "spill_st_L1miss",
           "spill_event_L1miss", "unread_st_L1miss", "other_st_L1miss"]
L2_KEYS = ["L2_local_miss", "spill_ld_L2local", "spill_st_L2local", "spill_event_L2local",
           "unread_st_L2local"]
L1_HEAD = [hd("all"), hd("spill", "ld"), hd("other", "ld"), hd("spill", "st"),
           hd("spill", "ev."), hd("unread", "st"), hd("other", "st")]
L2_HEAD = [hd("all"), hd("spill", "ld"), hd("spill", "st"), hd("spill", "ev."),
           hd("unread", "st")]
MISS_NOTES = [
    ("L1D: all", "L1D demand misses / L1D demand accesses: every load and store "
     + tr("bütün load ve store'lar") + "."),
    ("spill ld", "spill-load misses / spill-load accesses " + tr("spill load'lar") + "."),
    ("other ld", r"(\ct{ReadReq} misses $-$ spill-load misses) / (\ct{ReadReq} accesses "
     r"$-$ spill-load accesses): the loads that are not spill loads "
     + tr("spill olmayan load'lar") + "; read it next to spill ld."),
    ("spill st", "spill-store misses / spill-store accesses: every spill store "
     + tr("bütün spill store'lar") + "."),
    ("spill ev.", "spill-event misses / spill-event accesses: the spill stores read back "
     + tr("geri okunan spill store'lar") + "."),
    ("unread st", r"(spill-store $-$ spill-event misses) / (spill-store $-$ spill-event "
     "accesses): the spill stores never read back " + tr("hiç okunmayan spill store'lar")
     + "."),
    ("other st", r"(\ct{WriteReq} misses $-$ spill-store misses) / (\ct{WriteReq} accesses "
     r"$-$ spill-store accesses): the stores that are not spill stores "
     + tr("spill olmayan store'lar") + "."),
    ("L2 local: all", "L2 demand misses / L2 demand accesses: the L1D and L1I misses "
     "together " + tr("L2'ye gelen bütün istekler") + "."),
    ("L2 local: the rest", "The same kinds at L2; the denominator is that kind's L1D misses, "
     "so it can be small: read it with care "
     + tr("payda o türün L1D miss'leri; küçük olabilir") + "."),
]


def config_table(data: dict, cfg: str, number: int) -> str:
    rows, fracs = [], []
    for r in data["records"][cfg]:
        if not done(r):
            rows.append(" & ".join([tex(r["run_id"]),
                                    *([DASH] * (len(L1_KEYS) + len(L2_KEYS)))]) + r" \\")
            continue
        f = cs.miss_fractions(r)
        fracs.append(f)
        rows.append(" & ".join([tex(r["run_id"]), *(pc(*f[k]) for k in L1_KEYS),
                                *(pc(*f[k]) for k in L2_KEYS)]) + r" \\")
    pooled, mean = pooled_mean(fracs, L1_KEYS + L2_KEYS) if fracs else ([], [])
    foot = ([" & ".join(["pooled", *pooled]) + r" \\", " & ".join(["mean", *mean]) + r" \\"]
            if fracs else [])
    n1, n2 = len(L1_KEYS), len(L2_KEYS)
    pre = (rf"& \multicolumn{{{n1}}}{{c}}{{\textbf{{L1D miss rate (\%)}}}} & "
           rf"\multicolumn{{{n2}}}{{c}}{{\textbf{{L2 local miss rate (\%)}}}} \\" + "\n"
           rf"\cmidrule(lr){{2-{n1 + 1}}}\cmidrule(l){{{n1 + 2}-{n1 + n2 + 1}}}")
    g = data["geometry"][cfg]
    spec = "@{}l" + "r" * n1 + "r" * n2 + "@{}"
    return rf"""
\clearpage
\subsection*{{\ct{{{cfg}}}}}

L1D: {geometry_cell(g.get("L1D"))}; L2: {geometry_cell(g.get("L2"))};
{len(fracs)} of {len(data["records"][cfg])} runs completed.\par
\tablehead{{{number}}}{{Miss rates of \ct{{{cfg}}}, in percent of the accesses
\trgloss{{access'lerin yüzdesi}}.}}

{{\footnotesize\setlength{{\tabcolsep}}{{3.0pt}}\renewcommand{{\arraystretch}}{{0.98}}
{longtable(spec, ["run", *L1_HEAD, *L2_HEAD], rows, foot, pre_header=pre)}}}
{notes(MISS_NOTES + POOL_NOTES + [(DASH, "Run not finished, or no access of that kind "
                                  + tr("bitmemiş koşu ya da o türde access yok") + ".")])}"""


def cache_section(data: dict) -> str:
    parts = [r"""
\section{Cache miss rates by configuration}

These depend on the configuration: the program and its instructions are the
same, only the hits and misses change \trgloss{konfigürasyona göre değişir}. An
\emph{access} is one request of a load or store to a cache; an instruction
that crosses a cache line makes two \trgloss{cache'e yapılan tek istek}. A
\emph{hit} ends at that level, a \emph{miss} goes one level down (L1D $\to$
L2 $\to$ DRAM). The caches are write-allocate: a store miss first fetches the
line. An L2 rate is \emph{local}: its denominator is the L1D misses of that
kind, not all accesses \trgloss{L2 oranının paydası L1D miss'leridir}. Each of
Tables 4--8 is one configuration; the columns are the same in all of them.
"""]
    for n, cfg in enumerate(CONFIGS, start=4):
        parts.append(config_table(data, cfg, n))
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Comparison of two benchmarks
# --------------------------------------------------------------------------
CMP_L1 = [("L1D_miss", hd("L1D", "all")), ("spill_ld_L1miss", hd("spill", "ld")),
          ("other_ld_L1miss", hd("other", "ld")), ("spill_st_L1miss", hd("spill", "st")),
          ("other_st_L1miss", hd("other", "st"))]
CMP_L2 = [("L2_local_miss", hd("L2", "all")), ("spill_ld_L2local", hd("spill", "ld")),
          ("spill_st_L2local", hd("spill", "st"))]
CMP_PROGRAM = ["spill/roi", "spill_load/load", "spill_store/store",
               "spill_event/spill_store", "spill/mem"]


def comparison(data: dict, names: list[str], inp: str) -> str:
    ids = [rid for rid, _ in data["runs"]]
    idx = []
    for name in names:
        if name not in ids:
            return f"\n\\section{{Comparison}}\nNo run named \\ct{{{tex(name)}}}.\n"
        i = ids.index(name)
        if not all(done(data["records"][c][i]) for c in CONFIGS):
            return (f"\n\\section{{Comparison}}\n\\ct{{{tex(name)}}} has not finished in "
                    "every configuration yet.\n")
        idx.append(i)
    a, b = names
    ta, tb = tex(a), tex(b)
    miss = {n: {c: {k: 100.0 * v[0] / v[1] if v[1] else None
                    for k, v in cs.miss_fractions(data["records"][c][i]).items()}
                for c in CONFIGS} for n, i in zip(names, idx)}
    prog = {}
    for n, i in zip(names, idx):
        c = cs.counts(data["records"][REFERENCE][i])
        prog[n] = {name: 100.0 * c[x] / c[y] for name, x, y in cs.RATIOS}
        prog[n]["insts"] = c["roi_total_insts"]

    shares = sorted((100.0 * cs.counts(r)["roi_spill_insts"] / cs.counts(r)["roi_total_insts"],
                     r["run_id"]) for r in data["records"][REFERENCE] if done(r))
    shares.reverse()
    order = [rid for _, rid in shares]

    def rank(n):
        k = order.index(n) + 1
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(k % 10 if k % 100 not in (11, 12, 13) else 0,
                                                 "th")
        return f"{k}{suffix}"

    def weight(n, part):
        """Share of the L1D accesses (part 1) or misses (part 0) that are spill
        loads or spill stores: lowest and highest over the configurations."""
        vals = []
        for c in CONFIGS:
            f = cs.miss_fractions(data["records"][c][idx[names.index(n)]])
            total = f["L1D_miss"][part]
            vals.append(100.0 * (f["spill_ld_L1miss"][part] + f["spill_st_L1miss"][part])
                        / total if total else 0.0)
        return min(vals), max(vals)

    def span(lo_hi):
        lo, hi = (f"{v:.1f}" for v in lo_hi)
        return f"{lo}\\%" if lo == hi else f"{lo}--{hi}\\%"

    f2 = lambda v: DASH if v is None else f"{v:.2f}"
    rows = [rf"ROI instructions (millions) & {mio(prog[a]['insts'])} & {mio(prog[b]['insts'])} \\"]
    for k in CMP_PROGRAM:
        label = " ".join(RATIO_HEAD[k]).replace("/ ", "/")
        rows.append(rf"\ct{{{tex(label)}}} & {f2(prog[a][k])} & {f2(prog[b][k])} \\")
    table_program = "\n".join(rows)

    def by_config(keys):
        body = []
        for c in CONFIGS:
            body.append(" & ".join([rf"\ct{{{short(c)}}}",
                                    *(f2(miss[a][c][k]) for k, _ in keys),
                                    *(f2(miss[b][c][k]) for k, _ in keys)]) + r" \\")
        delta = lambda n, k: (None if miss[n]["small-dm"][k] is None or miss[n]["small-fa"][k]
                              is None else miss[n]["small-dm"][k] - miss[n]["small-fa"][k])
        body.append(r"\midrule")
        body.append(" & ".join([r"dm $-$ fa", *(f2(delta(a, k)) for k, _ in keys),
                                *(f2(delta(b, k)) for k, _ in keys)]) + r" \\")
        n = len(keys)
        head = (rf"& \multicolumn{{{n}}}{{c}}{{\ct{{{ta}}} (\%)}} & "
                rf"\multicolumn{{{n}}}{{c}}{{\ct{{{tb}}} (\%)}} \\" + "\n"
                rf"\cmidrule(lr){{2-{n + 1}}}\cmidrule(l){{{n + 2}-{2 * n + 1}}}" + "\n"
                + " & ".join(["config", *(h for _, h in keys), *(h for _, h in keys)]) + r" \\")
        return (f"\\begin{{tabular}}{{@{{}}l{'r' * (2 * n)}@{{}}}}\n\\toprule\n{head}\n"
                "\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}")

    def rng(n, k):
        vals = [miss[n][c][k] for c in CONFIGS if miss[n][c][k] is not None]
        return f"{min(vals):.2f}--{max(vals):.2f}\\%"

    def assoc(n, k):
        dm, fa = miss[n]["small-dm"][k], miss[n]["small-fa"][k]
        if dm is None or fa is None:
            return ""
        if dm - fa < 1.0:
            return ("it hardly changes with the organisation, which points to capacity "
                    "rather than conflict misses " + tr("çakışma değil kapasite miss'leri"))
        if fa < dm / 2:
            return ("it falls sharply with associativity: in the direct-mapped cache these "
                    "are mostly conflict misses " + tr("çoğu çakışma miss'i"))
        return "it falls with associativity"

    def dm_fa(n, k):
        return (f"{miss[n]['small-dm'][k]:.2f}\\% $\\to$ {miss[n]['small-fa'][k]:.2f}\\%")

    bullets = [
        rf"\textbf{{Program.}} \ct{{{ta}}} spends {prog[a]['spill/roi']:.2f}\% of its ROI "
        rf"instructions on spill-like traffic, \ct{{{tb}}} {prog[b]['spill/roi']:.2f}\%. "
        rf"That is {prog[a]['spill/mem']:.2f}\% of the memory instructions of \ct{{{ta}}} "
        rf"and {prog[b]['spill/mem']:.2f}\% of those of \ct{{{tb}}} "
        + tr("bellek trafiğindeki spill payı") + ". These values are the same in every "
        "configuration.",
        rf"\textbf{{Spill loads against other loads.}} Over the five configurations the spill "
        rf"loads of \ct{{{ta}}} miss L1D {rng(a, 'spill_ld_L1miss')} of the time, its other "
        rf"loads {rng(a, 'other_ld_L1miss')}; for \ct{{{tb}}} {rng(b, 'spill_ld_L1miss')} and "
        rf"{rng(b, 'other_ld_L1miss')} " + tr("spill load'lar diğer load'lardan daha az miss "
                                              "ediyor mu?") + ".",
        rf"\textbf{{Associativity.}} From \ct{{dm}} to \ct{{fa}} the spill-load miss rate of "
        rf"\ct{{{ta}}} goes {dm_fa(a, 'spill_ld_L1miss')}: {assoc(a, 'spill_ld_L1miss')}. "
        rf"That of \ct{{{tb}}} goes {dm_fa(b, 'spill_ld_L1miss')}: "
        rf"{assoc(b, 'spill_ld_L1miss')}. The overall L1D miss rate goes "
        rf"{dm_fa(a, 'L1D_miss')} for \ct{{{ta}}} and {dm_fa(b, 'L1D_miss')} for \ct{{{tb}}}.",
        rf"\textbf{{Weight of the spill traffic.}} Spill loads and spill stores make "
        rf"{span(weight(a, 1))} of the L1D accesses of \ct{{{ta}}} but "
        rf"{span(weight(a, 0))} of its L1D misses; for \ct{{{tb}}} {span(weight(b, 1))} of "
        rf"the accesses and {span(weight(b, 0))} of the misses "
        + tr("spill trafiğinin access'ler ve miss'ler içindeki payı") + ".",
        rf"\textbf{{L2.}} Of the accesses that miss L1D, L2 misses {rng(a, 'L2_local_miss')} "
        rf"for \ct{{{ta}}} and {rng(b, 'L2_local_miss')} for \ct{{{tb}}}; the spill loads that "
        rf"reach L2 miss there {rng(a, 'spill_ld_L2local')} and "
        rf"{rng(b, 'spill_ld_L2local')}.",
    ]
    return rf"""
\clearpage
\renewcommand{{\arraystretch}}{{1.0}}
\section{{Comparison of two benchmarks}}

To make the tables concrete, this page follows two benchmarks through the five
configurations \trgloss{{iki benchmark'ın konfigürasyonlar boyunca
karşılaştırması}}. By spill share (\ct{{spill/roi}}) \ct{{{ta}}} ranks
{rank(a)} and \ct{{{tb}}} {rank(b)} of the {len(order)} completed runs of the
\ct{{{inp}}} input. The rows of the cache tables go
from the least to the most associative; the last row is the change from
direct-mapped to fully associative, in percentage points
\trgloss{{yüzde puan farkı}}.

\tablehead{{9}}{{Program profile (does not depend on the cache), in percent.}}

{{\small
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
& \ct{{{ta}}} & \ct{{{tb}}} \\
\midrule
{table_program}
\bottomrule
\end{{tabular}}
}}

\tablehead{{10}}{{L1D miss rates by configuration, in percent (columns as in Tables 4--8).}}

{{\small\setlength{{\tabcolsep}}{{4pt}}
{by_config(CMP_L1)}
}}

\tablehead{{11}}{{L2 local miss rates by configuration, in percent.}}

{{\small\setlength{{\tabcolsep}}{{4pt}}
{by_config(CMP_L2)}
}}

\textbf{{Reading}} \trgloss{{okuması}}:
\begin{{itemize}}
\setlength{{\itemsep}}{{1pt}}\setlength{{\topsep}}{{2pt}}
{chr(10).join(r"\item " + b for b in bullets)}
\end{{itemize}}
"""


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
PREAMBLE = r"""% Generated by cache_scripts/input_report.py; edit the script, not this file.
% Preamble and author block of general_reports/definitions/counter_reference_schema10.tex.
\documentclass[10pt,a4paper]{article}
\usepackage[a4paper,top=16mm,bottom=16mm,left=20mm,right=20mm]{geometry}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{longtable}
\usepackage{lmodern}
\usepackage[T1]{fontenc}
\usepackage{amsmath}
\usepackage{microtype}
\usepackage{titlesec}

\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\linespread{1.06}\selectfont
\raggedbottom

\titleformat{\section}{\normalfont\large\bfseries}{\thesection.}{0.6em}{}
\titlespacing*{\section}{0pt}{12pt plus 2pt minus 2pt}{5pt}
\titleformat{\subsection}{\normalfont\normalsize\bfseries}{\thesubsection}{0.6em}{}
\titlespacing*{\subsection}{0pt}{8pt plus 2pt minus 2pt}{3pt}

\newcommand{\IEEEauthorblockN}[1]{{\normalsize #1}}
\newcommand{\IEEEauthorblockA}[1]{%
  \\[2pt]{\small\begin{tabular}[t]{@{}c@{}}#1\end{tabular}}}

\newcommand{\LongDate}{%
    \number\day\space
    \ifcase\month
    \or January\or February\or March\or April\or May\or June%
    \or July\or August\or September\or October\or November\or December%
    \fi
    \space \number\year
}

\newcommand{\ct}[1]{\texttt{#1}}
\newcommand{\trgloss}[1]{(\textit{#1})}
\setlength{\tabcolsep}{5pt}
\renewcommand{\arraystretch}{1.2}
\setlength{\LTpre}{2pt}
\setlength{\LTpost}{2pt}

\newcommand{\tablehead}[2]{%
  \nobreak{\small\textbf{Table #1.} #2}\par\nobreak\vspace{2pt}}
"""


def document(inp: str, simpoint: bool, body: str) -> str:
    what = f"SPEC CPU2017 \\texttt{{{inp}}} input" + (", SimPoint estimates" if simpoint else "")
    return PREAMBLE + rf"""
\title{{
    \Large Improving CPU Efficiency for Data-Intensive Applications \\
    \Large through Cache-Aware Spill Optimization \\[6pt]
    \large Results: Spill Ratios and Cache Miss Rates of the {what} \\[5pt]
    \normalsize gem5 TimingSimpleCPU $\cdot$ RISC-V (RV64GC)
    $\cdot$ five cache configurations $\cdot$ metric schema 10
}}

\author{{
    \IEEEauthorblockN{{L\"utfullah Burak Kaya}}
    \IEEEauthorblockA{{
        Ozyegin University \\
        burak.kaya.50711@ozu.edu.tr
    }}
    \and
    \IEEEauthorblockN{{Assistant Prof.\ Dr.\ \.{{I}}smail Akt\"urk}}
    \IEEEauthorblockA{{
        Ozyegin University \\
        ismail.akturk@ozyegin.edu.tr
    }}
}}

\date{{\small \LongDate}}

\begin{{document}}

\maketitle
\thispagestyle{{empty}}
\vspace{{-9mm}}
{body}
\end{{document}}
"""


def to_ascii(s: str) -> str:
    s = "".join(TURKISH.get(ch, ch) for ch in s)
    left = sorted({ch for ch in s if ord(ch) > 127})
    if left:
        raise SystemExit(f"characters without a LaTeX form: {left}")
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", default="test", choices=("test", "train", "ref"))
    ap.add_argument("--simpoint", action="store_true", help="ref: the SimPoint estimates")
    ap.add_argument("--compare", nargs=2, default=["cactuBSSN", "parest"],
                    metavar=("BENCH_A", "BENCH_B"), help="runs compared on the last page")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()

    now = datetime.now()
    tag = f"{args.input}{'_simpoint' if args.simpoint else ''}"
    out = args.out or cs.ROOT / "general_reports" / "results" / f"schema10_{tag}_report_{now:%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)

    data = collect(args.input, args.simpoint)
    sp = spread(data)
    body = "\n".join([
        overview(data, args.input, args.simpoint, f"{now:%Y-%m-%d %H:%M}"),
        program_counts(data, sp),
        r"\section{Program ratios}" + "\n\nThese, too, do not depend on the cache "
        r"\trgloss{cache'ten bağımsız}." + "\n" + program_ratios(data),
        cache_section(data),
        comparison(data, args.compare, args.input),
    ])
    tex_path = out / "report.tex"
    tex_path.write_text(to_ascii(document(args.input, args.simpoint, body)))
    print(tex_path)
    engine = None if args.no_pdf else shutil.which("tectonic")
    if engine:
        res = subprocess.run([engine, "--outdir", str(out), str(tex_path)],
                             capture_output=True, text=True)
        if res.returncode:
            print(res.stderr[-3000:], file=sys.stderr)
            return 1
        print(out / "report.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
