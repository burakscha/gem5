#!/usr/bin/env python3
"""Test, train and ref (SimPoint) results side by side, per benchmark.

A benchmark's value for an input pools all of its completed runs of that
input (sum of numerators / sum of denominators), since the inputs have
different runs (xz: 12 test, 2 train, 3 ref). Writes into one directory:
    input_comparison_<date>.tex/.pdf   program percentages (schema 10: spill
                                       shares, store classes; schema 9: compiler
                                       spill, spill + csave) and, per
                                       configuration, miss rates, as
                                       test | train | ref columns
    input_comparison_<date>.csv        the same numbers (percent, no sign)

    cache_scripts/compare_inputs.py
    cache_scripts/compare_inputs.py --schema 9 --out DIR --no-pdf
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_status as cs  # noqa: E402
import summary_tables as st  # noqa: E402
from benchmark_reports import SPEC_NAMES  # noqa: E402

# (label, input, SimPoint)
INPUTS = [("test", "test", False), ("train", "train", False), ("ref", "ref", True)]
# (title, metric keys) of the program tables, which do not depend on the cache,
# and the miss rates shown per configuration.
PROGRAM_TABLES = {
    10: [("Program: spill share (does not depend on the cache)",
          ["spill_roi", "spill_ld", "spill_mem"]),
         ("Program: spill stores and spill events (does not depend on the cache)",
          ["spill_st", "spill_ev", "match"])],
    9: [("Program, compiler spill (does not depend on the cache)",
         ["spill_roi", "spill_ld", "spill_st"]),
        ("Program, spill + csave (does not depend on the cache)",
         ["spcs_roi", "spcs_ld", "spcs_st"])],
}
CACHE_KEYS = {10: ["spill_ld_L1miss", "spill_ld_L2local", "spill_st_L1miss",
                   "spill_event_L1miss"],
              9: ["L1D_miss", "spill_ld_L1miss", "spill_st_L1miss", "L2_miss"]}


def headers() -> dict[str, str]:
    return {k: h for k, h, _, _ in st.PROGRAM} | dict(st.CACHE)


def by_benchmark(data: dict) -> dict[str, dict]:
    """benchmark -> runs, the program fractions of its completed runs (first
    completed configuration) and the cache fractions per configuration."""
    out: dict[str, dict] = {}
    configs, recs = data["configs"], data["records"]
    for i, (_, bench) in enumerate(data["runs"]):
        b = out.setdefault(bench, {"runs": 0, "prog": [], "cache": {c: [] for c in configs}})
        b["runs"] += 1
        done = [recs[c][i] for c in configs if recs[c][i]["state"] == "COMPLETED"]
        if done:
            b["prog"].append(st.program_fractions(done[0]))
        for c in configs:
            if recs[c][i]["state"] == "COMPLETED":
                b["cache"][c].append(st.cache_fractions(recs[c][i]))
    return out


def pooled(fracs: list[dict], key: str) -> float | None:
    den = sum(f[key][1] for f in fracs)
    return 100.0 * sum(f[key][0] for f in fracs) / den if den else None


def cell(v: float | None) -> str:
    return st.DASH if v is None else f"{v:.2f}\\%"


def table(title: str, cfg: str | None, keys: list[str], data: dict, benches: list[str]):
    """LaTeX table and CSV rows: one row per benchmark, test | train | ref per
    metric, then the pooled row and the mean over the benchmarks that have a
    value in every input."""
    labels = [label for label, _, _ in INPUTS]
    pick = (lambda b: b["prog"]) if cfg is None else (lambda b: b["cache"].get(cfg, []))
    values: dict[str, dict[str, list[float | None]]] = {}
    rows, csv_rows = [], []
    for bench in benches:
        vals, runs = {}, []
        for label in labels:
            b = data[label].get(bench)
            fr = pick(b) if b else []
            runs.append(f"{len(fr)}" if b else "-")
            vals[label] = [pooled(fr, k) if fr else None for k in keys]
        values[bench] = vals
        cells = [cell(vals[label][j]) for j in range(len(keys)) for label in labels]
        rows.append(" & ".join([st.tex(bench), "/".join(runs), *cells]) + r" \\")
        for j, k in enumerate(keys):
            csv_rows.append([cfg or "", bench, k, *(
                "" if vals[label][j] is None else f"{vals[label][j]:.4f}" for label in labels),
                *runs])
    # pooled over every completed run of the input; mean over common benchmarks
    common = [b for b in benches
              if all(v is not None for label in labels for v in values[b][label])]
    pool_cells, mean_cells = [], []
    for j, k in enumerate(keys):
        for label in labels:
            fr = [f for b in data[label].values() for f in pick(b)]
            pool_cells.append(cell(pooled(fr, k) if fr else None))
            ms = [values[b][label][j] for b in common]
            mean_cells.append(cell(sum(ms) / len(ms) if ms else None))
    foot = [" & ".join(["pooled", "", *pool_cells]) + r" \\",
            " & ".join([f"mean ({len(common)} benchmarks)", "", *mean_cells]) + r" \\"]
    n = len(labels)
    groups = " & ".join(f"\\multicolumn{{{n}}}{{c}}{{{st.tex(headers()[k])}}}" for k in keys)
    rules = "".join(f"\\cmidrule(lr){{{3 + n * j}-{2 + n * (j + 1)}}}" for j in range(len(keys)))
    head = (f"& & {groups} \\\\\n{rules}\nbenchmark & runs t/tr/r & "
            + " & ".join(labels * len(keys)) + r" \\")
    tex = (f"\\subsection*{{{st.tex(title)}}}\n{{\\footnotesize\n"
           f"\\begin{{longtable}}{{lc{'r' * n * len(keys)}}}\n\\toprule\n{head}\n\\midrule\n"
           f"\\endhead\n\\bottomrule\n\\endfoot\n" + "\n".join(rows)
           + "\n\\midrule\n" + "\n".join(foot) + "\n\\end{longtable}}\n")
    return tex, csv_rows


def spec_key(bench: str) -> str:
    return SPEC_NAMES.get(bench, "999." + bench)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--schema", type=int, default=cs.CURRENT_SCHEMA)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    st.use_schema(args.schema)
    schema = 10 if args.schema >= 10 else 9
    today = datetime.now()
    stamp = f"{today:%Y%m%d}"
    out = args.out or cs.ROOT / "general_reports" / "results" / f"summary_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    raw = {label: st.collect(inp, simpoint) for label, inp, simpoint in INPUTS}
    data = {label: by_benchmark(raw[label]) for label in raw}
    benches = sorted({b for d in data.values() for b in d}, key=spec_key)
    configs = [c for c in cs.ALL_CONFIGS if all(c in raw[l]["configs"] for l in raw)]
    geometry = raw["test"]["geometry"]

    tables = ([(title, None, keys) for title, keys in PROGRAM_TABLES[schema]] +
              [(f"Miss rates: {c} ({geometry[c]})", c, CACHE_KEYS[schema]) for c in configs])
    parts, csv_rows = [], []
    for i, (title, cfg, keys) in enumerate(tables):
        tex, rows = table(title, cfg, keys, data, benches)
        parts.append(("\\clearpage\n" if i >= 1 else "") + tex)
        csv_rows += rows

    notes = (r"{\footnotesize Each value pools all completed runs of the benchmark for that "
             r"input: sum of numerators / sum of denominators. \emph{runs t/tr/r} = completed "
             r"runs in test / train / ref. ref values are SimPoint estimates (up to 30 points of "
             r"100\,M instructions after a 500\,M warmup); test and train are full runs. "
             r"\emph{pooled} = all completed runs of the input together (large runs dominate); "
             r"\emph{mean} = average of the benchmark values over the benchmarks that have a value "
             r"in all three inputs, each benchmark weighted equally. A benchmark's runs differ "
             r"between inputs (e.g.\ perlbench test = makerand, train = 5 scripts, ref = 3 "
             r"scripts). Formulas: last page.\par}" "\n")
    body = notes + "".join(parts) + "\\clearpage\n" + st.legend()
    path = out / f"input_comparison_{stamp}.tex"
    path.write_text(st.document(
        "Register spill study: test vs.\\ train vs.\\ ref (SimPoint)",
        f"L1D 4\\,KiB, L1I 32\\,KiB, L2 32\\,KiB, 64\\,B lines, LRU $\\cdot$ metric schema "
        f"{args.schema} $\\cdot$ gem5 TimingSimpleCPU $\\cdot$ {today:%-d %B %Y}", body))
    engine = None if args.no_pdf else (shutil.which("tectonic") or shutil.which("pdflatex"))
    print(f"{st.shown(path)}{st.build_pdf(engine, path)}")

    csv_path = out / f"input_comparison_{stamp}.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "benchmark", "metric", "test", "train", "ref_simpoint",
                    "runs_test", "runs_train", "runs_ref"])
        w.writerows(csv_rows)
    print(st.shown(csv_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
