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
    # Additional se.py options, e.g. cache geometry for the outcome tests.
    extra_args: tuple[str, ...] = ()
    # Also compare the detector ROI with gem5's own ROI statistics, under
    # se.py and under the stdlib (see check_gem5_roi_crosscheck).
    roi_crosscheck: bool = False


BASE_ZERO = {
    "spill_load": 0,
    "spill_event": 0,
    "repeat_spill_load": 0,
}


def roi(loads: int, stores: int, spill_stores: int, **overrides: int) -> dict[str, int]:
    """Expected ROI counters.

    `spill_stores` is the write side: every SP/FP-relative stack store in the
    ROI, reloaded or not. `spill_event` counts only the ones read back again,
    so it is supplied per case and is never larger than `spill_stores`.
    """
    result = {
        **BASE_ZERO,
        "roi_load": loads,
        "roi_store": stores,
        "spill_store": spill_stores,
        "diag_nonspill_reuse": 0,
    }
    result.update(overrides)
    result["spill_event"] = result["spill_load"] - result["repeat_spill_load"]
    result["total_spill_insts"] = result["spill_store"] + result["spill_load"]
    result["spill_store_unpaired"] = result["spill_store"] - result["spill_event"]
    return result


CASES = (
    Case(
        "tc1_callee_save",
        (roi(6, 6, 6, spill_load=6),),
        6, 6,
    ),
    Case(
        "tc2_reg_pressure",
        (roi(8, 8, 8, spill_load=8),),
        8, 8,
    ),
    Case(
        "tc3_loop_spill",
        (roi(15, 15, 15, spill_load=15),),
        15, 15,
    ),
    Case(
        "tc4a_spill_evicted_by_nonspill",
        (roi(1, 2, 1, spill_load=1),),
        1, 2, True, {"spillLoadEvictedByNonSpill": 1},
    ),
    Case(
        "tc4b_nonspill_evicted_by_spill",
        (roi(1, 2, 1, diag_nonspill_reuse=1),),
        1, 2, True, {"nonSpillLoadEvictedBySpill": 1},
    ),
    Case(
        "tc4c_nonspill_evicted_by_nonspill",
        (roi(1, 2, 0, diag_nonspill_reuse=1),),
        1, 2, True, {"nonSpillLoadEvictedByNonSpill": 1},
    ),
    Case(
        "tc4d_spill_evicted_by_spill",
        (roi(1, 2, 2, spill_load=1),),
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
        (roi(3, 1, 1, spill_load=3,
             repeat_spill_load=2),),
        3, 1,
    ),
    Case("tc6_unmatched_store", (roi(0, 1, 1),), 0, 1),
    Case(
        "tc7_store_generations",
        (roi(2, 2, 2, spill_load=2),),
        2, 2,
    ),
    Case(
        "tc8_address_base", (roi(1, 1, 0, diag_nonspill_reuse=1),), 1, 1,
    ),
    Case(
        "tc9_roi_scope",
        (roi(1, 1, 1, spill_load=1),),
        3, 3,
    ),
    Case("tc10_negative_pairs", (roi(2, 2, 2),), 2, 2),
    Case(
        "tc11_split_line",
        (roi(1, 1, 1, spill_load=1,
             spill_load_l1_accesses=2,
             spill_store_l1_accesses=2,
             spill_load_split_insts=1,
             spill_store_split_insts=1,
             spill_load_extra_fragments=1,
             spill_store_extra_fragments=1,
             diag_paired_store_l1_accesses=2,
             diag_paired_store_split_insts=1,
             diag_paired_store_extra_fragments=1),),
        1, 1,
    ),
    Case(
        "tc12_multiple_roi",
        (
            roi(1, 1, 1, spill_load=1),
            roi(2, 1, 1, spill_load=2,
                repeat_spill_load=1),
        ),
        3, 2,
    ),
    Case("tc13_no_roi", (), 1, 1),
    Case(
        "tc14_exact_pc_map",
        (roi(2, 2, 1, spill_load=1),),
        2, 2, False, {}, (("store", "exact_store"), ("load", "exact_load")),
    ),
    Case(
        "tc15_gem5_roi_crosscheck",
        (roi(4, 4, 4, spill_load=4, roi_total_insts=19),),
        6, 8, roi_crosscheck=True,
    ),
    Case(
        "tc16_non_stack",
        (roi(1, 1, 0, roi_total_insts=7),),
        1, 1,
    ),
    Case(
        "tc17_cache_outcomes",
        (roi(36, 3, 3, spill_load=3, roi_total_insts=145,
             spill_store_l1_hits=1, spill_store_l1_misses=2,
             spill_store_l2_hits=0, spill_store_l2_misses=2,
             spill_load_l1_hits=1, spill_load_l1_misses=2,
             spill_load_l2_hits=1, spill_load_l2_misses=1),),
        36, 4,
        extra_args=("--l1d_size=64B", "--l1d_assoc=1",
                    "--l2_size=1kB", "--l2_assoc=1"),
    ),
    Case(
        "tc18_long_distance",
        (roi(1, 1, 1, spill_load=1, roi_total_insts=120007,
             reuse_log2_16=1),),
        1, 1,
    ),
)


INT_FIELD = re.compile(r"^#\s+([A-Za-z0-9_]+)\s*:\s*([0-9]+)")
REUSE_FIELD = re.compile(r"^#\s+reuse_log2\[\s*([0-9]+)\]\s*:\s*([0-9]+)")
ROI_HEADER = re.compile(r"^# ROI SUMMARY.*workid=([0-9]+).*sequence=([0-9]+)")
STAT_LINE = re.compile(r"^(\S+)\s+([-+0-9.eE]+)(?:\s|$)")
ROI_TICKS = re.compile(r"^ROI_TICKS \[([0-9, ]*)\]", re.MULTILINE)


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
        reuse_match = REUSE_FIELD.match(line)
        if reuse_match and current is not None:
            current[f"reuse_log2_{int(reuse_match.group(1))}"] = int(
                reuse_match.group(2))
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
    """Sum every statistics block in stats.txt.

    workbegin/workend dump AND reset the gem5 statistics, so stats.txt holds
    pre-ROI, per-ROI and post-ROI blocks instead of one cumulative block.
    Summing them reproduces the whole-simulation totals these tests assert on.
    """
    result: dict[str, float] = {}
    for line in path.read_text().splitlines():
        match = STAT_LINE.match(line)
        if match:
            try:
                result[match.group(1)] = (result.get(match.group(1), 0.0) +
                                          float(match.group(2)))
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


def parse_stat_blocks(path: Path) -> list[dict[str, float]]:
    """Split stats.txt into its dump blocks, in file order."""
    blocks: list[dict[str, float]] = []
    for line in path.read_text().splitlines():
        if "Begin Simulation Statistics" in line:
            blocks.append({})
            continue
        match = STAT_LINE.match(line)
        if blocks and match:
            try:
                blocks[-1][match.group(1)] = float(match.group(2))
            except ValueError:
                pass
    return blocks


def block_stat(block: dict[str, float], suffix: str) -> int:
    """Value of the one statistic named `suffix` or ending in `.suffix`.

    se.py calls the core system.cpu and the stdlib
    system.processor.cores.core, so the CPU statistics are matched by suffix.
    """
    matches = [value for key, value in block.items()
               if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise AssertionError(f"missing or ambiguous stat {suffix}: {matches}")
    return int(matches[0])


def check_equal(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def check_gem5_roi_block(label: str, block: dict[str, float],
                         detector_roi: dict[str, int]) -> None:
    """gem5's ROI statistics block must cover the detector's ROI exactly.

    The single, known offset: the work_end marker commits before the stats
    dump scheduled for that tick runs, so gem5 counts the marker inside its
    ROI block, while the detector excludes both markers.
    """
    check_equal(block_stat(block, "simInsts"),
                detector_roi["roi_total_insts"] + 1,
                f"{label}: gem5 ROI simInsts == detector roi_total_insts "
                "+ work_end marker")
    check_equal(block_stat(block, "commitStats0.numLoadInsts"),
                detector_roi["roi_load"], f"{label}: gem5 ROI loads")
    check_equal(block_stat(block, "commitStats0.numStoreInsts"),
                detector_roi["roi_store"], f"{label}: gem5 ROI stores")


def check_dump_reset_layout(label: str, blocks: list[dict[str, float]],
                            detector_roi: dict[str, int],
                            global_values: dict[str, int]) -> None:
    """Checks the stats.txt layout produced by the dump+reset that
    pseudo_inst.cc adds at work_begin and work_end: pre-ROI, ROI, post-ROI."""
    check_equal(len(blocks), 3, f"{label}: stats.txt blocks (pre/ROI/post)")
    check_gem5_roi_block(label, blocks[1], detector_roi)
    # gem5's own work-item bookkeeping: one sample, as long as the ROI block.
    work_item = f"work_item_type{detector_roi['workid']}"
    check_equal(block_stat(blocks[1], f"{work_item}::samples"), 1,
                f"{label}: gem5 {work_item} samples")
    check_equal(block_stat(blocks[1], f"{work_item}::mean"),
                block_stat(blocks[1], "simTicks"),
                f"{label}: gem5 work-item ticks == ROI block simTicks")
    check_equal(sum(block_stat(block, "simInsts") for block in blocks),
                global_values["total_insts"],
                f"{label}: gem5 simInsts over all blocks == detector "
                "total_insts")


def run_stdlib(args: argparse.Namespace, case: Case, build_dir: Path,
               binary: Path, exit_on_work_items: bool) -> tuple[Path, str]:
    tag = "default" if exit_on_work_items else "no_exit"
    outdir = build_dir / f"m5out_stdlib_{tag}"
    stdout = build_dir / f"stdout_stdlib_{tag}.txt"
    run([str(args.gem5), f"--outdir={outdir}",
         str(TEST_ROOT / case.name / "stdlib_se.py"), str(binary),
         "1" if exit_on_work_items else "0"],
        stdout=stdout, stderr=build_dir / f"stderr_stdlib_{tag}.txt")
    return outdir, stdout.read_text()


def check_gem5_roi_crosscheck(case: Case, args: argparse.Namespace,
                              build_dir: Path, binary: Path,
                              outdir: Path) -> None:
    """Compares the SpillDetector ROI with gem5's own ROI in three setups."""
    expected = case.rois[0]

    # 1. se.py, the configuration every SPEC run uses.
    rois, se_globals = parse_spill_log(outdir / "riscv_spill_stats.txt")
    check_dump_reset_layout(f"{case.name} se.py",
                            parse_stat_blocks(outdir / "stats.txt"),
                            rois[0], se_globals)

    # 2. stdlib with exit_on_work_items=False: the work items stay inside
    #    C++, so the detector hook and the dump+reset run exactly as in se.py.
    std_out, _ = run_stdlib(args, case, build_dir, binary, False)
    rois, std_globals = parse_spill_log(std_out / "riscv_spill_stats.txt")
    label = f"{case.name} stdlib exit_on_work_items=False"
    check_equal(len(rois), 1, f"{label}: detector ROI count")
    for key, value in expected.items():
        check_equal(rois[0].get(key, -1), value, f"{label}: {key}")
    check_dump_reset_layout(label, parse_stat_blocks(std_out / "stats.txt"),
                            rois[0], std_globals)

    # 3. stdlib default, exit_on_work_items=True: gem5's own ROI. Python
    #    resets the stats at work begin and only dumps them at work end, so
    #    block 0 is the ROI and the final block is ROI + post-ROI.
    std_out, stdout = run_stdlib(args, case, build_dir, binary, True)
    label = f"{case.name} stdlib default"
    blocks = parse_stat_blocks(std_out / "stats.txt")
    check_equal(len(blocks), 2, f"{label}: stats.txt blocks (ROI/final)")
    check_gem5_roi_block(label, blocks[0], expected)
    ticks = ROI_TICKS.search(stdout)
    if not ticks:
        raise AssertionError(f"{label}: stdlib_se.py printed no ROI_TICKS")
    roi_ticks = [int(t) for t in ticks.group(1).split(",") if t.strip()]
    check_equal(len(roi_ticks), 1, f"{label}: stdlib ROI count")
    check_equal(roi_ticks[0], block_stat(blocks[0], "simTicks"),
                f"{label}: Simulator.get_roi_ticks() == ROI block simTicks")
    # Known limitation, asserted so it cannot change silently: in this mode
    # pseudo_inst.cc workbegin()/workend() return before the SpillDetector
    # hook, so the detector sees no ROI and only writes the global totals.
    # Update this check if the hook is moved ahead of that early return.
    rois, default_globals = parse_spill_log(std_out / "riscv_spill_stats.txt")
    check_equal(len(rois), 0,
                f"{label}: detector ROI count (hook is bypassed by design)")
    check_equal(default_globals.get("total_insts", -1),
                se_globals["total_insts"],
                f"{label}: detector total_insts same as under se.py")


def validate_case(case: Case, rois: list[dict[str, int]],
                  global_values: dict[str, int], stats: dict[str, float]) -> None:
    check_equal(len(rois), len(case.rois), f"{case.name} ROI count")
    for index, (actual, expected) in enumerate(zip(rois, case.rois), start=1):
        check_equal(actual.get("metric_schema", -1), 7,
                    f"{case.name} ROI {index} schema")
        for key, value in expected.items():
            check_equal(actual.get(key, -1), value,
                        f"{case.name} ROI {index} {key}")

        spill_store = actual["spill_store"]
        spill_load = actual["spill_load"]
        spill_event = actual["spill_event"]
        # spill_event is the paired subset of the write side, and every
        # reload past the first is a repeat, so both identities must hold.
        check_equal(spill_event, spill_load - actual["repeat_spill_load"],
                    f"{case.name} ROI {index} spill_event == spill_load - repeats")
        check_equal(actual["spill_store_unpaired"], spill_store - spill_event,
                    f"{case.name} ROI {index} spill_store_unpaired")
        if spill_event > spill_store:
            raise AssertionError(
                f"{case.name} ROI {index}: spill_event {spill_event} exceeds "
                f"spill_store {spill_store}")
        check_equal(actual["total_spill_insts"], spill_load + spill_store,
                    f"{case.name} ROI {index} spill memory identity")
        for population in ("spill_load", "spill_store", "diag_paired_store"):
            accesses = actual[f"{population}_l1_accesses"]
            outcomes = (actual[f"{population}_l1_hits"] +
                        actual[f"{population}_l1_misses"])
            check_equal(outcomes, accesses,
                        f"{case.name} ROI {index} {population} L1 outcomes")
            check_equal(accesses,
                        actual[f"{population}_l1_misses"] +
                        actual[f"{population}_l1_hits"],
                        f"{case.name} ROI {index} {population} L1 total")
            check_equal(actual[f"{population}_l2_hits"] +
                        actual[f"{population}_l2_misses"],
                        actual[f"{population}_l1_misses"],
                        f"{case.name} ROI {index} {population} L2 accesses")
        for population, insts in (("spill_load", spill_load),
                                  ("spill_store", spill_store)):
            check_equal(actual[f"{population}_l1_accesses"],
                        insts + actual[f"{population}_extra_fragments"],
                        f"{case.name} ROI {index} {population} fragment identity")

    check_equal(global_values.get("metric_schema", -1), 7,
                f"{case.name} global schema")
    check_equal(global_values.get("total_load", -1), case.global_loads,
                f"{case.name} global loads")
    check_equal(global_values.get("total_store", -1), case.global_stores,
                f"{case.name} global stores")
    if global_values.get("total_insts", 0) <= 0:
        raise AssertionError(f"{case.name}: total_insts was not emitted")

    # Both gem5 request tags now line up with a headline counter: SPILL_LOAD
    # marks exactly the spill_load population and SPILL_STORE exactly the
    # spill_store one. That equality is the point of defining spill_store as
    # the whole write side, so assert it at both cache levels.
    for level, cache in (("L1", "system.cpu.dcache"), ("L2", "system.l2")):
        suffix = "l1" if level == "L1" else "l2"
        for tag, population in (("spillLoad", "spill_load"),
                                ("spillStore", "spill_store")):
            for outcome in ("Hits", "Misses"):
                expected = sum(item[f"{population}_{suffix}_{outcome.lower()}"]
                               for item in rois)
                check_equal(stat(stats, f"{tag}{outcome}", cache), expected,
                            f"{case.name} {cache} {tag}{outcome}")

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
    command.extend(case.extra_args)
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
        if case.roi_crosscheck:
            check_gem5_roi_crosscheck(case, args, build_dir, binary, outdir)
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
