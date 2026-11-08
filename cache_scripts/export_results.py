#!/usr/bin/env python3
"""Freeze the cache experiment's results into files.

For one input set and metric schema it writes, into one directory:
    overview.txt           the status overview (every queued input)
    <input>_<config>.txt   per configuration: geometry and tables 1-3
    <input>_results.csv    one row per (configuration, run): counts, ratios,
                           cache miss rates and the raw ROI counters
    report_<config>/       with --pdf: scripts/spill_report.py's LaTeX report
                           (report.tex, report.pdf, results.csv) of the runs
    <input>_report.pdf     with --pdf: those reports, one page per configuration
    README.md              what the files hold and which runs are missing

The numbers come from cache_status.py, so they equal the status views.

    cache_scripts/export_results.py --input test --pdf
    cache_scripts/export_results.py --schema 9 --input train --out DIR
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_status as cs  # noqa: E402

# Raw counters copied into the CSV next to the table columns.
ROI_FIELDS_10 = [  # the canonical cache counters; the counts are table columns
    *(f"roi_{p}_{level}_{outcome}"
      for p in ("spill_store", "spill_event", "spill_load")
      for level in ("l1", "l2") for outcome in ("hits", "misses")),
    "diag_store_map_evicted", "diag_load_after_stack_release",
    "diag_event_after_stack_release",
]
ROI_FIELDS_9 = [
    "spill_event", "spill_store_unpaired", "repeat_spill_load",
    "csave_store", "csave_load", "csave_event",
    "other_stack_store", "other_stack_load", "other_stack_event",
    "stack_store", "stack_load", "stack_event",
    "spill_load_l1_hits", "spill_load_l1_misses",
    "spill_load_l2_hits", "spill_load_l2_misses",
    "spill_store_l1_hits", "spill_store_l1_misses",
    "spill_store_l2_hits", "spill_store_l2_misses",
    "diag_spill_load_pc_other_store", "diag_spill_reload_unmapped",
    "diag_nonspill_reuse", "diag_store_map_evicted",
]
STATS = [
    ("l1d_accesses", "system.cpu.dcache.demandAccesses::total"),
    ("l1d_misses", "system.cpu.dcache.demandMisses::total"),
    ("l1d_load_accesses", "system.cpu.dcache.ReadReq.accesses::total"),
    ("l1d_load_misses", "system.cpu.dcache.ReadReq.misses::total"),
    ("l1d_store_accesses", "system.cpu.dcache.WriteReq.accesses::total"),
    ("l1d_store_misses", "system.cpu.dcache.WriteReq.misses::total"),
    ("l2_hits", "system.l2.demandHits::total"),
    ("l2_misses", "system.l2.demandMisses::total"),
]


def captured(func, *args) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(*args)
    return buf.getvalue()


def ratio(part, whole) -> str:
    return "" if part is None or not whole else f"{100.0 * part / whole:.4f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--schema", type=int, default=cs.CURRENT_SCHEMA)
    ap.add_argument("--input", default="test", choices=("test", "train", "ref"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pdf", action="store_true",
                    help="also build the LaTeX/PDF report of every configuration")
    ap.add_argument("--simpoint", action="store_true",
                    help="SimPoint estimates (cache_scripts/simpoint.sh) instead of full runs")
    args = ap.parse_args()

    cs.use_schema(args.schema)
    cs.PROFILE, cs.SIMPOINT = args.input, args.simpoint
    out = args.out or (cs.ROOT / "general_reports" / "results" /
                       f"schema{args.schema}_{args.input}{'_simpoint' if args.simpoint else ''}"
                       f"_{datetime.now():%Y%m%d}")
    out.mkdir(parents=True, exist_ok=True)

    roi_fields = ROI_FIELDS_10 if args.schema >= 10 else ROI_FIELDS_9
    # Schema 10 exports no computable count (the ratios use it internally).
    sums = [] if args.schema >= 10 else ["roi_spill_insts"]
    runs = cs.workloads()
    # ref is not queued (SimPoint runs, cache_scripts/simpoint.sh): all configurations
    configs = cs.planned_caches(args.input) or cs.ALL_CONFIGS
    (out / "overview.txt").write_text(captured(cs.show_all))
    cs.PROFILE = args.input        # show_all walks every input
    header = (["input", "config", "run_id", "benchmark", "state", "started",
               "finished", "elapsed_s", *cs.COUNT_COLUMNS, *sums] +
              [h for h, _, _ in cs.RATIOS] + cs.MISS_COLUMNS + roi_fields +
              [name for name, _ in STATS] + ["run_dir"])
    missing: list[str] = []
    rows = []
    run_dirs: dict[str, list[str]] = {c: [] for c in configs}
    for cache in configs:
        (out / f"{args.input}_{cache}.txt").write_text(
            captured(cs.show_config, cache, runs))
        cs.PROFILE = args.input
        for run_id, benchmark in runs:
            r = cs.run_record(cache, run_id, benchmark)
            if r["state"] != "COMPLETED":
                missing.append(f"{cache} {run_id} ({r['state']})")
                continue
            run_dirs[cache].append(str(r["dir"]))
            c = cs.counts(r)
            m = cs.cache_misses(r)
            stats = r["stats"]
            rows.append(
                [args.input, cache, run_id, benchmark, r["state"],
                 cs.stamp(r["start"]), cs.stamp(r["end"]), r["elapsed"],
                 *(c[k] for k in cs.COUNT_COLUMNS), *(c[k] for k in sums)] +
                [ratio(c[a], c[b]) for _, a, b in cs.RATIOS] +
                [m[k].rstrip("%") if m[k] != "-" else "" for k in cs.MISS_COLUMNS] +
                [r["roi"].get(f, "") for f in roi_fields] +
                [int(stats[k]) if k in stats else "" for _, k in STATS] +
                [str(r["dir"])])
    with (out / f"{args.input}_results.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    pdfs: list[Path] = []
    if args.pdf:
        for cache in configs:
            rdir = out / f"report_{cache}"
            subprocess.run([sys.executable, str(cs.ROOT / "scripts" / "spill_report.py"),
                            "--schema", str(args.schema), "--profile", args.input,
                            "--cache", cache, "--outdir", str(rdir),
                            *(["--simpoint"] if args.simpoint else []), *run_dirs[cache]],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if (rdir / "report.pdf").is_file():
                pdfs.append(rdir / "report.pdf")
            else:
                print(f"warning: no PDF for {cache} (see {rdir})", file=sys.stderr)
        if pdfs and shutil.which("pdfunite"):
            subprocess.run(["pdfunite", *map(str, pdfs), str(out / f"{args.input}_report.pdf")],
                           check=False)

    current = args.schema == cs.CURRENT_SCHEMA
    superseded = {
        8: (f"Superseded: the current detector writes schema {cs.CURRENT_SCHEMA}. Schema 8 "
            "paired a reload with its store only at the same address and width, so it missed "
            "partial and merged reloads (up to 15% of the spill reloads in bwaves, 8.5% in "
            "leela, 3% in x264, under 0.1% in most benchmarks)."),
        9: (f"Superseded: the current detector writes schema {cs.CURRENT_SCHEMA}. Schema 9 "
            "took spill stores from the compiler's -dP map and callee saves from CFI, and "
            "required an sp/s0 base register for the other stack pairs; schema 10 finds "
            "spills from addresses alone, so its spill counts include every stack "
            "store/reload pair and are not comparable with these."),
    }
    lines = [
        f"# {args.input} results, metric schema {args.schema}",
        "",
        f"Exported {datetime.now():%Y-%m-%d %H:%M} by `cache_scripts/export_results.py "
        f"--schema {args.schema} --input {args.input}{' --simpoint' if args.simpoint else ''}`.",
        "",
        ("These are the current results." if current else
         superseded.get(args.schema, f"Superseded: the current detector writes schema "
                                     f"{cs.CURRENT_SCHEMA}.")),
        "",
        "| file | content |",
        "|---|---|",
        "| `overview.txt` | status overview (every queued input and configuration) |",
        *(f"| `{args.input}_{c}.txt` | {c}: cache geometry, tables 1-3 |" for c in configs),
        f"| `{args.input}_results.csv` | one row per configuration and run: tables 1-3 "
        "(ratios and miss rates in percent, without the sign), raw ROI counters, "
        "gem5 cache counts, run directory |",
        *([f"| `{args.input}_report.pdf` | LaTeX report, one page per configuration "
           "(`report_<config>/report.tex` is its source) |"] if pdfs else []),
        "",
        *(["Ref values are SimPoint estimates (`cache_scripts/simpoint.sh`): per run up to 30 "
           "simulation points of 100M instructions after a 500M-instruction warmup, weighted by "
           "SimPoint; every counter is ROI instructions * sum(w_i * c_i / n_i). The points and "
           "weights of a run are in its directory's `simpoint.txt`.", ""] if args.simpoint else []),
        f"Runs: {len(rows)} of {len(configs) * len(runs)} completed.",
    ]
    if missing:
        lines += ["", "Missing (no completed run of this schema):", ""]
        lines += [f"- {m}" for m in missing]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print(f"{out}: {len(rows)} runs, {len(missing)} missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
