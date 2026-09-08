#!/usr/bin/env python3
"""Report schema-v4 instruction and cache metrics from gem5 m5out folders."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


HEADER = re.compile(r"^# ROI SUMMARY")
FIELD = re.compile(r"^#\s+([A-Za-z0-9_]+)\s*:\s*([0-9]+)")
CLASSIFICATION = re.compile(r"^# classification\s*:\s*(\S+)")


def parse_log(path: Path) -> tuple[list[dict[str, int]], set[str]]:
    rois: list[dict[str, int]] = []
    classifications: set[str] = set()
    current: dict[str, int] | None = None
    for line in path.read_text().splitlines():
        if HEADER.match(line):
            current = {}
            rois.append(current)
            continue
        class_match = CLASSIFICATION.match(line)
        if current is not None and class_match:
            classifications.add(class_match.group(1))
            continue
        field_match = FIELD.match(line)
        if current is not None and field_match:
            current[field_match.group(1)] = int(field_match.group(2))
        if line.startswith("# GLOBAL SUMMARY"):
            current = None
    return rois, classifications


def summed(rois: list[dict[str, int]], key: str) -> int:
    return sum(roi.get(key, 0) for roi in rois)


def percentage(numerator: int, denominator: int) -> float | None:
    return 100.0 * numerator / denominator if denominator else None


def population(rois: list[dict[str, int]], name: str) -> dict[str, int | float | None]:
    l1_hits = summed(rois, f"roi_{name}_l1_hits")
    l1_misses = summed(rois, f"roi_{name}_l1_misses")
    l2_hits = summed(rois, f"roi_{name}_l2_hits")
    l2_misses = summed(rois, f"roi_{name}_l2_misses")
    total = l1_hits + l1_misses
    return {
        f"{name}_l1_accesses": total,
        f"{name}_l1_hits": l1_hits,
        f"{name}_l1_misses": l1_misses,
        f"{name}_l1_hit_pct": percentage(l1_hits, total),
        f"{name}_l2_accesses": l2_hits + l2_misses,
        f"{name}_l2_hits": l2_hits,
        f"{name}_l2_misses": l2_misses,
        # Conditional probability among requests that reached L2.
        f"{name}_l2_local_hit_pct": percentage(l2_hits, l2_hits + l2_misses),
        # Breakdown over the original L1-facing population.
        f"{name}_l2_rescue_pct_of_l1_total": percentage(l2_hits, total),
        f"{name}_dram_pct_of_l1_total": percentage(l2_misses, total),
    }


def analyze(m5out: Path) -> dict[str, object]:
    log = m5out / "riscv_spill_stats.txt"
    if not log.is_file():
        raise FileNotFoundError(log)
    rois, classifications = parse_log(log)
    if not rois:
        raise ValueError(f"no ROI summaries in {log}")
    schemas = {roi.get("metric_schema") for roi in rois}
    if schemas != {4}:
        raise ValueError(
            f"{log} uses schema {sorted(s for s in schemas if s is not None)}; "
            "rerun with the corrected gem5 build"
        )

    instructions = summed(rois, "roi_instructions")
    spill_loads = summed(rois, "roi_spill_load_insts")
    spill_stores = summed(rois, "roi_spill_store_insts")
    spill_memory = spill_loads + spill_stores
    result: dict[str, object] = {
        "m5out": str(m5out),
        "classification": "+".join(sorted(classifications)),
        "roi_count": len(rois),
        "roi_instructions": instructions,
        "roi_load_insts": summed(rois, "roi_load_insts"),
        "roi_store_insts": summed(rois, "roi_store_insts"),
        "roi_spill_events": summed(rois, "roi_spill_events"),
        "roi_spill_load_insts": spill_loads,
        "roi_spill_store_insts": spill_stores,
        "roi_spill_mem_insts": spill_memory,
        "spill_inst_pct": percentage(spill_memory, instructions),
        "roi_candidate_stack_store_insts": summed(
            rois, "roi_candidate_stack_store_insts"
        ),
        "roi_repeated_spill_load_insts": summed(
            rois, "roi_repeated_spill_load_insts"
        ),
    }
    result.update(population(rois, "spill_load"))
    result.update(population(rois, "spill_store"))
    result.update(population(rois, "candidate_store"))
    return result


def fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}%"
    return str(value)


def print_result(result: dict[str, object]) -> None:
    print(f"\n{result['m5out']} [{result['classification']}]")
    print(
        "  ROI instructions/load/store: "
        f"{result['roi_instructions']} / {result['roi_load_insts']} / "
        f"{result['roi_store_insts']}"
    )
    print(
        "  Spill events/load/store/memory instructions: "
        f"{result['roi_spill_events']} / {result['roi_spill_load_insts']} / "
        f"{result['roi_spill_store_insts']} / {result['roi_spill_mem_insts']}"
    )
    print(f"  Spill instructions / ROI instructions: {fmt(result['spill_inst_pct'])}")
    for name, label in (
        ("spill_load", "confirmed spill loads"),
        ("spill_store", "confirmed spill stores"),
        ("candidate_store", "candidate stores"),
    ):
        print(
            f"  {label}: L1 H/M={result[f'{name}_l1_hits']}/"
            f"{result[f'{name}_l1_misses']} "
            f"(hit={fmt(result[f'{name}_l1_hit_pct'])}); "
            f"L2 H/M={result[f'{name}_l2_hits']}/"
            f"{result[f'{name}_l2_misses']} "
            f"(local hit={fmt(result[f'{name}_l2_local_hit_pct'])}, "
            f"L2/DRAM of L1 total={fmt(result[f'{name}_l2_rescue_pct_of_l1_total'])}/"
            f"{fmt(result[f'{name}_dram_pct_of_l1_total'])})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("m5out", nargs="+", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    rows = []
    for path in args.m5out:
        try:
            row = analyze(path.resolve())
            rows.append(row)
            print_result(row)
        except Exception as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
    if args.csv:
        with args.csv.open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
