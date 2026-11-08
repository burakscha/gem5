#!/usr/bin/env python3
"""Combine the SimPoint interval runs of one workload and cache configuration
into one result that reads like a full run (cache_scripts/simpoint.sh run).

Every simulation point i ran its interval of n_i instructions (after a warmup)
with weight w_i (SimPoint's share of the ROI intervals in its cluster). A
counter c of the whole ROI of N instructions is estimated as

    C = N * sum_i w_i * c_i / n_i

for the SpillDetector's ROI counters and gem5's statistics alike, so ratios of
estimates are the weighted per-instruction ratios. N is the ROI's instruction
count from the qemu profile (bbv.info). gem5 statistics that are ratios or
averages themselves (miss rates, latencies, ipc...) are weight-averaged
instead; the tools only read counts.

The result goes to OUT (riscv_spill_stats.txt, stats.txt with a placeholder
block and the ROI block, as a SimPoint interval run writes it, simpoint.txt
with the sources and weights, .runner/ state); --link points the run's
simpoint_<input>_<cfg>_<run> link at it, where status_cache.sh --simpoint and
the reports' --simpoint find it.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

FIELD = re.compile(r"^(#\s+)([^:]+?)(\s*:\s*)(\d+)(\s.*|)$")
RATE = re.compile(r"^(#\s+)(\w+)_(event|inst)_rate(\s*:\s*)[0-9.]+%$")
STAT = re.compile(r"^(\S+)(\s+)([-+0-9.eE]+|nan|inf)(\s.*|)$")
AVERAGED = re.compile(r"(missRate|Rate\b|rate\b|avg|Avg|ipc|cpi|Latency|::mean|::stdev|"
                      r"::gmean|bw|Ratio|ratio|Frequency|Freq|Utilization|::samples)")
FIXED = ("map_", "metric_schema")


def spill_fields(path: Path) -> dict[str, dict[str, int]]:
    """{section: {name: value}} of the ROI and GLOBAL summaries."""
    out: dict[str, dict[str, int]] = {"roi": {}, "glob": {}}
    cur = None
    for line in path.read_text().splitlines():
        if line.startswith("# ROI SUMMARY"):
            cur = out["roi"]
        elif line.startswith("# GLOBAL SUMMARY"):
            cur = out["glob"]
        elif cur is not None:
            m = FIELD.match(line)
            if m:
                cur[m.group(2).strip()] = int(m.group(4))
    return out


def stat_blocks(path: Path) -> list[list[str]]:
    blocks: list[list[str]] = []
    for line in path.read_text().splitlines():
        if "Begin Simulation Statistics" in line:
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    return blocks


def stat_values(lines: list[str]) -> dict[str, float]:
    vals = {}
    for line in lines:
        m = STAT.match(line)
        if m:
            try:
                vals[m.group(1)] = float(m.group(3))
            except ValueError:
                pass
    return vals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spdir", required=True, type=Path, help="holds sp01, sp02, ... (gem5 outdirs)")
    ap.add_argument("--plan", required=True, type=Path, help="qemu2gem5.py plan output")
    ap.add_argument("--bbv-info", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--link", type=Path, help="simpoint_* link to point at OUT")
    a = ap.parse_args()

    plan = [l.split() for l in a.plan.read_text().splitlines() if l.strip()]
    info = dict(l.split() for l in a.bbv_info.read_text().splitlines())
    roi_n = int(info["roi_end_inst"]) - int(info["roi_begin_inst"])
    total_n = int(info["total_insts"])
    pts = []
    for k, (_i, inst, w, warm, idx) in enumerate(plan):
        d = a.spdir / f"sp{k + 1:02d}"
        spill, stats = d / "riscv_spill_stats.txt", d / "stats.txt"
        if not spill.is_file() or not stats.is_file():
            sys.exit(f"{d}: not finished")
        f = spill_fields(spill)
        blocks = stat_blocks(stats)
        if len(blocks) != 2:
            sys.exit(f"{stats}: {len(blocks)} statistics blocks, expected 2")
        n = f["roi"]["roi_total_insts"]
        pts.append({"dir": d, "w": float(w), "n": n, "spill": f, "blocks": blocks,
                    "stats": stat_values(blocks[1]), "inst": int(inst), "idx": int(idx)})
    wsum = sum(p["w"] for p in pts)

    def est(get) -> float:
        return roi_n * sum(p["w"] * get(p) / p["n"] for p in pts) / wsum

    # riscv_spill_stats.txt: the first point's file with every counter estimated
    roi_est = {}
    for name in pts[0]["spill"]["roi"]:
        if name.startswith(FIXED):
            roi_est[name] = pts[0]["spill"]["roi"][name]
        elif name == "roi_total_insts":
            roi_est[name] = roi_n
        elif name in ("diag_insts_before_roi", "entry_total_insts"):  # new, old name
            roi_est[name] = int(info["roi_begin_inst"])
        else:
            roi_est[name] = round(est(lambda p, k=name: p["spill"]["roi"].get(k, 0)))
    scale_glob = total_n / roi_n if roi_n else 1.0
    glob_est = {"total_insts": total_n}
    for name, roi_name in (("total_load", "roi_load"), ("total_store", "roi_store")):
        glob_est[name] = round(roi_est.get(roi_name, 0) * scale_glob)
    for name in pts[0]["spill"]["glob"]:
        if name.startswith("total_") and name.endswith("_event"):
            glob_est[name] = round(roi_est.get(name[len("total_"):], 0) * scale_glob)

    out_lines = []
    section = None
    for line in (pts[0]["dir"] / "riscv_spill_stats.txt").read_text().splitlines():
        if line.startswith("# ROI SUMMARY"):
            section = roi_est
        elif line.startswith("# GLOBAL SUMMARY"):
            section = glob_est
        m = FIELD.match(line)
        r = RATE.match(line)
        if r and section is roi_est:
            cls, kind = r.group(2), r.group(3)
            num = roi_est.get(f"{cls}_event" if kind == "event" else f"total_{cls}_insts", 0)
            line = f"{r.group(1)}{cls}_{kind}_rate{r.group(4)}{100.0 * num / roi_n:.4f}%"
        elif m and section is not None and m.group(2).strip() in section:
            line = f"{m.group(1)}{m.group(2)}{m.group(3)}{section[m.group(2).strip()]}{m.group(5)}"
        if line.startswith("# store_tracking"):
            line = line.split(":")[0] + ": SimPoint estimate (stores tracked from each interval's start, see simpoint.txt)"
        out_lines.append(line)

    # stats.txt: placeholder block + estimated ROI block (layout of the first point)
    stat_lines = []
    for line in pts[0]["blocks"][1]:
        m = STAT.match(line)
        if m and not line.startswith("-"):
            name = m.group(1)
            try:
                float(m.group(3))
            except ValueError:
                stat_lines.append(line)
                continue
            if AVERAGED.search(name):
                v = sum(p["w"] * p["stats"].get(name, 0.0) for p in pts) / wsum
            else:
                v = est(lambda p, k=name: p["stats"].get(k, 0.0))
            val = f"{v:.6f}" if AVERAGED.search(name) else f"{round(v)}"
            stat_lines.append(f"{name}{m.group(2)}{val}{m.group(4)}")
        else:
            stat_lines.append(line)
    placeholder = [pts[0]["blocks"][0][0],
                   "# SimPoint estimate: this block stands for the program before the ROI",
                   "---------- End Simulation Statistics   ----------", ""]

    out = a.out
    (out / ".runner").mkdir(parents=True, exist_ok=True)
    # The points' system (caches included) is the configuration's: its
    # config.ini gives the geometry the status views and reports show.
    for name in ("config.ini", "config.json"):
        if (pts[0]["dir"] / name).is_file():
            shutil.copy(pts[0]["dir"] / name, out / name)
    (out / "riscv_spill_stats.txt").write_text("\n".join(out_lines) + "\n")
    (out / "stats.txt").write_text("\n".join(placeholder + stat_lines) + "\n")
    rows = "\n".join(f"sp{k + 1:02d} interval {p['idx']} weight {p['w']:.6f} "
                     f"checkpoint_inst {p['inst']} interval_insts {p['n']} dir {p['dir']}"
                     for k, p in enumerate(pts))
    (out / "simpoint.txt").write_text(
        f"SimPoint estimate of run {a.run_id}: {len(pts)} simulation points, "
        f"weights sum {wsum:.6f}, ROI {roi_n} instructions (qemu), program {total_n}.\n"
        f"counter = ROI insts * sum(w_i * c_i / n_i) / sum(w_i)\n{rows}\n")
    starts, ends = [], []
    for p in pts:
        st = p["dir"] / ".runner" / "started.epoch"
        en = p["dir"] / ".runner" / "finished.epoch"
        if st.is_file():
            starts.append(int(st.read_text()))
        if en.is_file():
            ends.append(int(en.read_text()))
    now = int(time.time())
    host_seconds = sum(p["stats"].get("hostSeconds", 0.0) for p in pts)
    runner = out / ".runner"
    runner.joinpath("run_id").write_text(a.run_id + "\n")
    runner.joinpath("status").write_text("COMPLETED\n")
    runner.joinpath("started.epoch").write_text(f"{min(starts) if starts else now}\n")
    # elapsed = summed simulation time of the points, not the wall clock
    runner.joinpath("finished.epoch").write_text(
        f"{(min(starts) if starts else now) + round(host_seconds)}\n")
    runner.joinpath("simpoint").write_text(f"{len(pts)}\n")
    if a.link:
        tmp = a.link.with_name(a.link.name + ".tmp")
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        tmp.symlink_to(out)
        tmp.replace(a.link)
    print(f"{a.run_id}: {len(pts)} points combined -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
