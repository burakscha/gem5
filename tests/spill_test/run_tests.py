#!/usr/bin/env python3
"""Build and run the SpillDetector's deterministic RISC-V integration tests."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
DEFAULT_AS = Path(
    "/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as"
)
DEFAULT_LD = Path(
    "/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld"
)
DEFAULT_NM = Path(
    "/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-nm"
)


@dataclass(frozen=True)
class Case:
    name: str
    rois: tuple[dict[str, int], ...]
    global_loads: int
    global_stores: int
    tiny_l1: bool = False
    eviction: dict[str, int] = field(default_factory=dict)
    exact_symbols: tuple[tuple[str, str], ...] = ()


BASE_ZERO = {
    "roi_spill_events": 0,
    "roi_spill_load_insts": 0,
    "roi_spill_store_insts": 0,
    "roi_spill_mem_insts": 0,
    "roi_repeated_spill_load_insts": 0,
}


def roi(loads: int, stores: int, candidates: int, **overrides: int) -> dict[str, int]:
    result = {
        **BASE_ZERO,
        "roi_load_insts": loads,
        "roi_store_insts": stores,
        "roi_candidate_stack_store_insts": candidates,
        "roi_nonspill_reuse": 0,
    }
    result.update(overrides)
    return result


CASES = (
    Case(
        "tc1_callee_save",
        (roi(6, 6, 6, roi_spill_events=6, roi_spill_load_insts=6,
             roi_spill_store_insts=6, roi_spill_mem_insts=12),),
        6, 6,
    ),
    Case(
        "tc2_reg_pressure",
        (roi(8, 8, 8, roi_spill_events=8, roi_spill_load_insts=8,
             roi_spill_store_insts=8, roi_spill_mem_insts=16),),
        8, 8,
    ),
    Case(
        "tc3_loop_spill",
        (roi(15, 15, 15, roi_spill_events=15, roi_spill_load_insts=15,
             roi_spill_store_insts=15, roi_spill_mem_insts=30),),
        15, 15,
    ),
    Case(
        "tc4a_spill_evicted_by_nonspill",
        (roi(1, 2, 1, roi_spill_events=1, roi_spill_load_insts=1,
             roi_spill_store_insts=1, roi_spill_mem_insts=2),),
        1, 2, True, {"spillLoadEvictedByNonSpill": 1},
    ),
    Case(
        "tc4b_nonspill_evicted_by_spill",
        (roi(1, 2, 1, roi_nonspill_reuse=1),),
        1, 2, True, {"nonSpillLoadEvictedBySpill": 1},
    ),
    Case(
        "tc4c_nonspill_evicted_by_nonspill",
        (roi(1, 2, 0, roi_nonspill_reuse=1),),
        1, 2, True, {"nonSpillLoadEvictedByNonSpill": 1},
    ),
    Case(
        "tc4d_spill_evicted_by_spill",
        (roi(1, 2, 2, roi_spill_events=1, roi_spill_load_insts=1,
             roi_spill_store_insts=1, roi_spill_mem_insts=2),),
        1, 2, True, {"spillLoadEvictedBySpill": 1},
    ),
    Case(
        "tc4e_spillstore_evicted_by_nonspill",
        (roi(0, 3, 2),), 0, 3, True,
        {"spillStoreEvictedByNonSpill": 1},
    ),
    Case(
        "tc4f_nonspillstore_evicted_by_spill",
        (roi(0, 3, 1),), 0, 3, True,
        {"nonSpillStoreEvictedBySpill": 1},
    ),
    Case(
        "tc4g_nonspillstore_evicted_by_nonspill",
        (roi(0, 3, 0),), 0, 3, True,
        {"nonSpillStoreEvictedByNonSpill": 1},
    ),
    Case(
        "tc4h_spillstore_evicted_by_spill",
        (roi(0, 3, 3),), 0, 3, True,
        {"spillStoreEvictedBySpill": 1},
    ),
    Case(
        "tc5_repeated_reload",
        (roi(3, 1, 1, roi_spill_events=1, roi_spill_load_insts=3,
             roi_spill_store_insts=1, roi_spill_mem_insts=4,
             roi_repeated_spill_load_insts=2),),
        3, 1,
    ),
    Case("tc6_unmatched_store", (roi(0, 1, 1),), 0, 1),
    Case(
        "tc7_store_generations",
        (roi(2, 2, 2, roi_spill_events=2, roi_spill_load_insts=2,
             roi_spill_store_insts=2, roi_spill_mem_insts=4),),
        2, 2,
    ),
    Case(
        "tc8_address_base", (roi(1, 1, 0, roi_nonspill_reuse=1),), 1, 1,
    ),
    Case(
        "tc9_roi_scope",
        (roi(1, 1, 1, roi_spill_events=1, roi_spill_load_insts=1,
             roi_spill_store_insts=1, roi_spill_mem_insts=2),),
        3, 3,
    ),
    Case("tc10_negative_pairs", (roi(2, 2, 2),), 2, 2),
    Case(
        "tc11_split_line",
        (roi(1, 1, 1, roi_spill_events=1, roi_spill_load_insts=1,
             roi_spill_store_insts=1, roi_spill_mem_insts=2,
             roi_spill_load_l1_accesses=2,
             roi_spill_store_l1_accesses=2,
             roi_candidate_store_l1_accesses=2,
             roi_spill_load_split_insts=1,
             roi_spill_store_split_insts=1,
             roi_spill_load_extra_fragments=1,
             roi_spill_store_extra_fragments=1),),
        1, 1,
    ),
    Case(
        "tc12_multiple_roi",
        (
            roi(1, 1, 1, roi_spill_events=1, roi_spill_load_insts=1,
                roi_spill_store_insts=1, roi_spill_mem_insts=2),
            roi(2, 1, 1, roi_spill_events=1, roi_spill_load_insts=2,
                roi_spill_store_insts=1, roi_spill_mem_insts=3,
                roi_repeated_spill_load_insts=1),
        ),
        3, 2,
    ),
    Case("tc13_no_roi", (), 1, 1),
    Case(
        "tc14_exact_pc_map",
        (roi(2, 2, 1, roi_spill_events=1, roi_spill_load_insts=1,
             roi_spill_store_insts=1, roi_spill_mem_insts=2),),
        2, 2, False, {}, (("store", "exact_store"), ("load", "exact_load")),
    ),
)


INT_FIELD = re.compile(r"^#\s+([A-Za-z0-9_]+)\s*:\s*([0-9]+)")
ROI_HEADER = re.compile(r"^# ROI SUMMARY.*workid=([0-9]+).*sequence=([0-9]+)")
STAT_LINE = re.compile(r"^(\S+)\s+([-+0-9.eE]+)(?:\s|$)")


def run(command: list[str], *, stdout: Path | None = None,
        stderr: Path | None = None) -> None:
    out_handle = stdout.open("w") if stdout else None
    err_handle = stderr.open("w") if stderr else None
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdout=out_handle or subprocess.DEVNULL,
            stderr=err_handle or subprocess.DEVNULL,
            check=False,
            text=True,
        )
    finally:
        if out_handle:
            out_handle.close()
        if err_handle:
            err_handle.close()
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")


def parse_spill_log(path: Path) -> tuple[list[dict[str, int]], dict[str, int]]:
    rois: list[dict[str, int]] = []
    global_values: dict[str, int] = {}
    current: dict[str, int] | None = None
    in_global = False
    for line in path.read_text().splitlines():
        roi_match = ROI_HEADER.match(line)
        if roi_match:
            current = {
                "workid": int(roi_match.group(1)),
                "sequence": int(roi_match.group(2)),
            }
            rois.append(current)
            in_global = False
            continue
        if line.startswith("# GLOBAL SUMMARY"):
            current = None
            in_global = True
            continue
        field_match = INT_FIELD.match(line)
        if not field_match:
            continue
        key, value = field_match.group(1), int(field_match.group(2))
        if current is not None:
            current[key] = value
        elif in_global:
            global_values[key] = value
    return rois, global_values


def parse_stats(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in path.read_text().splitlines():
        match = STAT_LINE.match(line)
        if match:
            try:
                result[match.group(1)] = float(match.group(2))
            except ValueError:
                pass
    return result


def stat(stats: dict[str, float], suffix: str, cache: str = "system.cpu.dcache") -> int:
    matches = [int(value) for key, value in stats.items()
               if key == f"{cache}.{suffix}"]
    if len(matches) != 1:
        raise AssertionError(
            f"missing or ambiguous cache stat {cache}.{suffix}: {matches}"
        )
    return matches[0]


def check_equal(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def validate_case(case: Case, rois: list[dict[str, int]],
                  global_values: dict[str, int], stats: dict[str, float]) -> None:
    check_equal(len(rois), len(case.rois), f"{case.name} ROI count")
    for index, (actual, expected) in enumerate(zip(rois, case.rois), start=1):
        check_equal(actual.get("metric_schema", -1), 4,
                    f"{case.name} ROI {index} schema")
        for key, value in expected.items():
            check_equal(actual.get(key, -1), value,
                        f"{case.name} ROI {index} {key}")

        candidates = actual["roi_candidate_stack_store_insts"]
        confirmed = actual["roi_spill_store_insts"]
        check_equal(actual["roi_unconfirmed_candidate_store_insts"],
                    candidates - confirmed,
                    f"{case.name} ROI {index} unconfirmed candidates")
        check_equal(actual["roi_spill_mem_insts"],
                    actual["roi_spill_load_insts"] + confirmed,
                    f"{case.name} ROI {index} spill memory identity")
        for population in ("spill_load", "spill_store", "candidate_store"):
            accesses = actual[f"roi_{population}_l1_accesses"]
            outcomes = (actual[f"roi_{population}_l1_hits"] +
                        actual[f"roi_{population}_l1_misses"])
            check_equal(outcomes, accesses,
                        f"{case.name} ROI {index} {population} L1 outcomes")
            check_equal(actual[f"roi_{population}_l2_hits"] +
                        actual[f"roi_{population}_l2_misses"],
                        actual[f"roi_{population}_l1_misses"],
                        f"{case.name} ROI {index} {population} L2 accesses")

    check_equal(global_values.get("metric_schema", -1), 4,
                f"{case.name} global schema")
    check_equal(global_values.get("total_load_insts", -1), case.global_loads,
                f"{case.name} global loads")
    check_equal(global_values.get("total_store_insts", -1), case.global_stores,
                f"{case.name} global stores")
    if global_values.get("total_instructions", 0) <= 0:
        raise AssertionError(f"{case.name}: total_instructions was not emitted")

    load_l1_hits = sum(item["roi_spill_load_l1_hits"] for item in rois)
    load_l1_misses = sum(item["roi_spill_load_l1_misses"] for item in rois)
    candidate_l1_hits = sum(item["roi_candidate_store_l1_hits"] for item in rois)
    candidate_l1_misses = sum(item["roi_candidate_store_l1_misses"] for item in rois)
    check_equal(stat(stats, "spillLoadHits"), load_l1_hits,
                f"{case.name} dcache spill-load hits")
    check_equal(stat(stats, "spillLoadMisses"), load_l1_misses,
                f"{case.name} dcache spill-load misses")
    check_equal(stat(stats, "spillStoreHits"), candidate_l1_hits,
                f"{case.name} dcache candidate-store hits")
    check_equal(stat(stats, "spillStoreMisses"), candidate_l1_misses,
                f"{case.name} dcache candidate-store misses")
    load_l2_hits = sum(item["roi_spill_load_l2_hits"] for item in rois)
    load_l2_misses = sum(item["roi_spill_load_l2_misses"] for item in rois)
    candidate_l2_hits = sum(item["roi_candidate_store_l2_hits"] for item in rois)
    candidate_l2_misses = sum(item["roi_candidate_store_l2_misses"] for item in rois)
    check_equal(stat(stats, "spillLoadHits", "system.l2"), load_l2_hits,
                f"{case.name} L2 spill-load hits")
    check_equal(stat(stats, "spillLoadMisses", "system.l2"), load_l2_misses,
                f"{case.name} L2 spill-load misses")
    check_equal(stat(stats, "spillStoreHits", "system.l2"), candidate_l2_hits,
                f"{case.name} L2 candidate-store hits")
    check_equal(stat(stats, "spillStoreMisses", "system.l2"), candidate_l2_misses,
                f"{case.name} L2 candidate-store misses")

    for suffix, expected in case.eviction.items():
        check_equal(stat(stats, suffix), expected,
                    f"{case.name} eviction {suffix}")


def execute_case(case: Case, args: argparse.Namespace, workspace: Path) -> None:
    case_dir = TEST_ROOT / case.name
    source = case_dir / f"{case.name}.S"
    if not source.is_file():
        raise RuntimeError(f"missing source: {source}")

    build_dir = workspace / case.name
    build_dir.mkdir(parents=True)
    obj = build_dir / f"{case.name}.o"
    binary = build_dir / f"{case.name}.riscv"
    outdir = build_dir / "m5out"
    run([str(args.assembler), "-o", str(obj), str(source)])
    run([str(args.linker), "-o", str(binary), str(obj)])

    command = [
        str(args.gem5),
        f"--outdir={outdir}",
        str(ROOT / "configs/deprecated/example/se.py"),
        f"--cmd={binary}",
        "--cpu-type=TimingSimpleCPU",
        "--caches",
        "--l2cache",
    ]
    if case.exact_symbols:
        nm_result = subprocess.run(
            [str(args.nm), "-n", str(binary)], cwd=ROOT, check=True,
            capture_output=True, text=True,
        )
        addresses = {}
        for line in nm_result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3:
                addresses[parts[2]] = int(parts[0], 16)
        pc_map = build_dir / "spill_pc_map.txt"
        records = []
        for kind, symbol in case.exact_symbols:
            if symbol not in addresses:
                raise AssertionError(f"symbol missing from binary: {symbol}")
            records.append(f"{kind} {addresses[symbol]:#x}")
        pc_map.write_text("\n".join(records) + "\n")
        command.extend(("--param", f"system.cpu[0].spill_pc_map='{pc_map}'"))
    if case.tiny_l1:
        command.extend(("--l1d_size=64B", "--l1d_assoc=1", "--cacheline_size=64"))
    stdout = build_dir / "stdout.txt"
    stderr = build_dir / "stderr.txt"
    try:
        run(command, stdout=stdout, stderr=stderr)
        spill_log = outdir / "riscv_spill_stats.txt"
        stats_file = outdir / "stats.txt"
        if not spill_log.is_file() or not stats_file.is_file():
            raise AssertionError("gem5 did not produce spill log and stats.txt")
        rois, global_values = parse_spill_log(spill_log)
        validate_case(case, rois, global_values, parse_stats(stats_file))
        if case.rois:
            expected_classification = (
                "compiler_pc_map_store_reload_match" if case.exact_symbols
                else "heuristic_stack_store_reload_match"
            )
            if (f"# classification     : {expected_classification}"
                    not in spill_log.read_text()):
                raise AssertionError(
                    f"{case.name}: missing classification {expected_classification}"
                )
    except Exception:
        print(f"\nArtifacts for failed case: {build_dir}", file=sys.stderr)
        if stderr.exists():
            print("--- gem5 stderr (tail) ---", file=sys.stderr)
            print("\n".join(stderr.read_text(errors="replace").splitlines()[-40:]),
                  file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="*", help="case directory names (default: all)")
    parser.add_argument("--gem5", type=Path, default=ROOT / "build/RISCV/gem5.opt")
    parser.add_argument("--assembler", type=Path, default=DEFAULT_AS)
    parser.add_argument("--linker", type=Path, default=DEFAULT_LD)
    parser.add_argument("--nm", type=Path, default=DEFAULT_NM)
    parser.add_argument("--keep", type=Path,
                        help="keep all generated artifacts in this directory")
    args = parser.parse_args()

    selected = [case for case in CASES if not args.cases or case.name in args.cases]
    unknown = set(args.cases) - {case.name for case in CASES}
    if unknown:
        parser.error(f"unknown cases: {', '.join(sorted(unknown))}")
    for tool in (args.gem5, args.assembler, args.linker, args.nm):
        if not tool.is_file():
            parser.error(f"not found: {tool}")

    temp_context = None
    if args.keep:
        workspace = args.keep.resolve()
        workspace.mkdir(parents=True, exist_ok=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="gem5-spill-tests-")
        workspace = Path(temp_context.name)

    failures = 0
    print(f"Running {len(selected)} spill integration cases")
    for case in selected:
        try:
            execute_case(case, args, workspace)
            print(f"PASS  {case.name}")
        except Exception as error:
            failures += 1
            print(f"FAIL  {case.name}: {error}", file=sys.stderr)

    if temp_context is not None and failures == 0:
        temp_context.cleanup()
    elif temp_context is not None:
        print(f"Failed-run workspace retained until process exit: {workspace}",
              file=sys.stderr)

    if failures:
        print(f"{failures}/{len(selected)} cases failed", file=sys.stderr)
        return 1
    print(f"All {len(selected)} cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
