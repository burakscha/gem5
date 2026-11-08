#!/usr/bin/env python3
"""Build and run the SpillDetector's deterministic RISC-V integration tests."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
DEFAULT_AS = Path(
    "/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-as"
)
DEFAULT_LD = Path(
    "/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-ld"
)


@dataclass(frozen=True)
class Case:
    name: str
    rois: tuple[dict[str, int], ...]
    global_loads: int
    global_stores: int
    # Additional se.py options, e.g. cache geometry for the outcome tests.
    extra_args: tuple[str, ...] = ()
    # Also compare the detector ROI with gem5's own ROI statistics, under
    # se.py and under the stdlib (see check_gem5_roi_crosscheck).
    roi_crosscheck: bool = False
    # Directory/source to assemble, when several cases share one program.
    source: str = ""
    # (interval index, interval length, warmup): run as a SimPoint point, a
    # checkpoint taken and restored by se.py (see run_simpoint).
    simpoint: tuple[int, int, int] | None = None
    # Text gem5's stderr must contain, proving the case exercised its path.
    expect_stderr: str = ""


METRIC_SCHEMA = 10
# Populations with a cache tally in the ROI summary, and the gem5 cache
# statistic that counts the same accesses (None: detector only, because a
# store is known to be a spill store only at its first reload).
POPULATIONS = (("roi_spill_store", "stackStore"), ("roi_spill_event", None),
               ("roi_spill_load", "spillLoad"))


def roi(loads: int, stores: int, spill=(0, 0, 0), **overrides: int) -> dict[str, int]:
    """Expected ROI counters.

    spill is (roi_spill_store, roi_spill_event, roi_spill_load): every store
    meeting the store conditions of a spill (to the stack, inside the ROI),
    the distinct spill stores read back at least once (one event per store),
    and every spill load, repeats included.
    """
    spill_store, spill_event, spill_load = spill
    result = {
        "roi_load": loads,
        "roi_store": stores,
        "roi_spill_store": spill_store,
        "roi_spill_event": spill_event,
        "roi_spill_load": spill_load,
        "diag_store_map_evicted": 0,
        # Pairs whose stack bytes were released (sp rose above them) between
        # the store and the load: only tc25 has one.
        "diag_load_after_stack_release": 0,
        "diag_event_after_stack_release": 0,
    }
    result.update(overrides)
    return result


TINY_L1_L2 = ("--l1d_size=64B", "--l1d_assoc=1",
              "--l2_size=1kB", "--l2_assoc=1")
SMALL = ("--l1d_size=4kB", "--l1i_size=32kB", "--l2_size=32kB")
# The organisations of the runner's small-* cache profiles
# (scripts/spec_spill_runner.sh cache_options).
ORGS = {
    "dm": SMALL + ("--l1d_assoc=1", "--l2_assoc=1"),
    "nway": SMALL + ("--l1d_assoc=8", "--l2_assoc=16"),
    "fa": SMALL + ("--l1d_tags=FALRU", "--l2_tags=FALRU"),
}


def organisation_case(org: str, load_l1_hits: int) -> Case:
    """tc20 under one organisation: both stores miss L1 and L2 (first
    touches), each reload that misses L1 hits L2."""
    misses = 2 - load_l1_hits
    return Case(
        f"tc20_cache_organization_{org}",
        (roi(11, 2, spill=(2, 2, 2),
             roi_spill_store_l1_hits=0, roi_spill_store_l1_misses=2,
             roi_spill_store_l2_hits=0, roi_spill_store_l2_misses=2,
             roi_spill_event_l1_hits=0, roi_spill_event_l1_misses=2,
             roi_spill_event_l2_hits=0, roi_spill_event_l2_misses=2,
             roi_spill_load_l1_hits=load_l1_hits, roi_spill_load_l1_misses=misses,
             roi_spill_load_l2_hits=misses, roi_spill_load_l2_misses=0),),
        11, 2, extra_args=ORGS[org], source="tc20_cache_organization",
    )

CASES = (
    Case("tc1_callee_save", (roi(6, 6, spill=(6, 6, 6)),), 6, 6),
    Case("tc2_reg_pressure", (roi(8, 8, spill=(8, 8, 8)),), 8, 8),
    Case("tc3_loop_spill", (roi(15, 15, spill=(15, 15, 15)),), 15, 15),
    Case("tc5_repeated_reload", (roi(3, 1, spill=(1, 1, 3)),), 3, 1),
    Case("tc6_unmatched_store", (roi(0, 1, spill=(1, 0, 0)),), 0, 1),
    Case("tc7_store_generations", (roi(2, 2, spill=(2, 2, 2)),), 2, 2),
    # A store through a3 and its reload pair: the base register plays no part.
    Case("tc8_address_base", (roi(1, 1, spill=(1, 1, 1)),), 1, 1),
    Case("tc9_roi_scope", (roi(1, 1, spill=(1, 1, 1)),), 3, 3),
    Case("tc10_negative_pairs", (roi(3, 3, spill=(3, 0, 0)),), 3, 3),
    Case(
        "tc11_split_line",
        (roi(1, 1, spill=(1, 1, 1),
             roi_spill_store_split_insts=1, roi_spill_event_split_insts=1,
             roi_spill_load_split_insts=1),),
        1, 1,
    ),
    Case(
        "tc12_multiple_roi",
        (roi(1, 1, spill=(1, 1, 1)), roi(2, 1, spill=(1, 1, 2))),
        3, 2,
    ),
    Case("tc13_no_roi", (), 1, 1),
    # The source still carries spill_event/csave_store labels; they must not
    # change anything, every pair is found by its address alone.
    Case("tc14_stack_pc_map", (roi(5, 5, spill=(5, 5, 5)),), 5, 5),
    Case(
        "tc15_gem5_roi_crosscheck",
        (roi(4, 4, spill=(4, 4, 4), roi_total_insts=19),),
        6, 8, roi_crosscheck=True,
    ),
    Case("tc16_non_stack", (roi(1, 1, roi_total_insts=7),), 1, 1),
    Case(
        "tc17_cache_outcomes",
        (roi(36, 3, spill=(3, 3, 3), roi_total_insts=145,
             roi_spill_store_l1_hits=1, roi_spill_store_l1_misses=2,
             roi_spill_store_l2_hits=0, roi_spill_store_l2_misses=2,
             roi_spill_event_l1_hits=1, roi_spill_event_l1_misses=2,
             roi_spill_event_l2_hits=0, roi_spill_event_l2_misses=2,
             roi_spill_load_l1_hits=1, roi_spill_load_l1_misses=2,
             roi_spill_load_l2_hits=1, roi_spill_load_l2_misses=1),),
        36, 4, extra_args=TINY_L1_L2,
    ),
    Case(
        "tc18_long_distance",
        (roi(1, 1, spill=(1, 1, 1), roi_total_insts=120007),),
        1, 1,
    ),
    Case(
        "tc19_addressing_forms",
        tuple(roi(1, 1, spill=(1, 1, 1)) for _ in range(10)),
        10, 10,
    ),
    Case("tc21_partial_width", (roi(5, 6, spill=(6, 5, 5)),), 5, 6),
    Case("tc22_byte_ownership", (roi(3, 5, spill=(5, 3, 3)),), 3, 5),
    # LR counts as a load and SC as a store; AMOs as neither.
    Case("tc23_atomics", (roi(6, 6, spill=(4, 2, 2)),), 6, 6),
    # The restore run covers the warmup (20) and the interval (40) only; the
    # warmup length is checked in gem5's warmup block (check_simpoint_interval).
    Case(
        "tc24_simpoint_interval",
        (roi(3, 2, spill=(2, 2, 2), roi_total_insts=40),),
        3, 4, simpoint=(1, 40, 20),
    ),
    # A store into a popped frame's slot stays readable: h's uninitialized
    # read pairs with it (known limitation, see the source).
    Case("tc25_frame_reuse",
         (roi(3, 4, spill=(4, 3, 3), diag_load_after_stack_release=1,
              diag_event_after_stack_release=1),), 3, 4),
    Case("tc26_stack_growth", (roi(2, 2, spill=(2, 2, 2)),), 2, 2,
         expect_stderr="Increasing stack size by one page"),
    organisation_case("dm", 0),
    organisation_case("nway", 1),
    organisation_case("fa", 2),
)


INT_FIELD = re.compile(r"^#\s+([A-Za-z0-9_]+)\s*:\s*([0-9]+)")
REUSE_FIELD = re.compile(r"^#\s+(\w+)_reuse_log2\[\s*([0-9]+)\]\s*:\s*([0-9]+)")
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
            current[f"{reuse_match.group(1)}_reuse_log2_"
                    f"{int(reuse_match.group(2))}"] = int(reuse_match.group(3))
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


def check_simpoint_interval(case: Case, outdir: Path,
                            detector_roi: dict[str, int]) -> None:
    """gem5's interval block must equal the detector ROI exactly: Python
    opens and closes both between the same two instructions, so unlike a
    marker ROI there is no offset."""
    _, interval, warmup = case.simpoint
    blocks = parse_stat_blocks(outdir / "stats.txt")
    check_equal(len(blocks), 2, f"{case.name}: stats.txt blocks (warmup/interval)")
    check_equal(block_stat(blocks[0], "simInsts"), warmup,
                f"{case.name}: gem5 warmup simInsts")
    check_equal(block_stat(blocks[1], "simInsts"), interval,
                f"{case.name}: gem5 interval simInsts")
    check_equal(detector_roi["roi_total_insts"], block_stat(blocks[1], "simInsts"),
                f"{case.name}: detector roi_total_insts == gem5 interval simInsts")
    check_equal(block_stat(blocks[1], "commitStats0.numLoadInsts"),
                detector_roi["roi_load"], f"{case.name}: gem5 interval loads")
    check_equal(block_stat(blocks[1], "commitStats0.numStoreInsts"),
                detector_roi["roi_store"], f"{case.name}: gem5 interval stores")


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
        label = f"{case.name} ROI {index}"
        check_equal(actual.get("metric_schema", -1), METRIC_SCHEMA, f"{label} schema")
        for key, value in expected.items():
            check_equal(actual.get(key, -1), value, f"{label} {key}")

        for retired in ("spill_event", "stack_store", "spill_store", "spill_load",
                        "entry_total_insts", "roi_stack_store",
                        "diag_store_first_reload_after_stack_release",
                        "diag_insts_before_roi"):
            if retired in actual:
                raise AssertionError(f"{label}: retired counter name {retired} present")
        if any("_reuse_log2_" in key for key in actual):
            raise AssertionError(f"{label}: retired reuse-distance histogram present")
        spill_store, spill_event = actual["roi_spill_store"], actual["roi_spill_event"]
        spill_load = actual["roi_spill_load"]
        # roi_spill_event <= roi_spill_store <= roi_store; a spill event can
        # be read back many times; roi_spill_load <= roi_load.
        if not spill_event <= spill_store <= actual["roi_store"]:
            raise AssertionError(f"{label}: expected roi_spill_event {spill_event} <= "
                                 f"roi_spill_store {spill_store} <= roi_store "
                                 f"{actual['roi_store']}")
        if not spill_event <= spill_load <= actual["roi_load"]:
            raise AssertionError(f"{label}: expected roi_spill_event {spill_event} <= "
                                 f"roi_spill_load {spill_load} <= roi_load {actual['roi_load']}")
        for population, insts in (("roi_spill_store", spill_store),
                                  ("roi_spill_event", spill_event),
                                  ("roi_spill_load", spill_load)):
            check_equal(actual[f"{population}_l1_hits"] +
                        actual[f"{population}_l1_misses"],
                        insts + actual[f"{population}_split_insts"],
                        f"{label} {population} L1 accesses == insts + split insts")
            check_equal(actual[f"{population}_l2_hits"] +
                        actual[f"{population}_l2_misses"],
                        actual[f"{population}_l1_misses"],
                        f"{label} {population} L2 accesses == L1 misses")
        # The read-back stores are a subset of the spill stores.
        for field in ("l1_hits", "l1_misses", "l2_hits", "l2_misses", "split_insts"):
            if actual[f"roi_spill_event_{field}"] > actual[f"roi_spill_store_{field}"]:
                raise AssertionError(f"{label}: roi_spill_event_{field} exceeds "
                                     f"roi_spill_store_{field}")
        # The stack-release diagnostic only marks some of the counted pairs.
        released_loads = actual["diag_load_after_stack_release"]
        released_stores = actual["diag_event_after_stack_release"]
        if released_loads > spill_load or released_stores > min(spill_event, released_loads):
            raise AssertionError(f"{label}: stack-release diagnostic {released_loads}/"
                                 f"{released_stores} exceeds the pairs it marks")

    check_equal(global_values.get("metric_schema", -1), METRIC_SCHEMA,
                f"{case.name} global schema")
    check_equal(global_values.get("total_load", -1), case.global_loads,
                f"{case.name} global loads")
    check_equal(global_values.get("total_store", -1), case.global_stores,
                f"{case.name} global stores")
    if global_values.get("total_insts", 0) <= 0:
        raise AssertionError(f"{case.name}: total_insts was not emitted")

    # The request flags mark exactly the stack stores and the spill loads, so
    # the gem5 cache statistics must equal the detector's outcomes at both
    # cache levels.
    for level, cache in (("l1", "system.cpu.dcache"), ("l2", "system.l2")):
        for population, stat_prefix in POPULATIONS:
            if stat_prefix is None:
                continue
            for outcome in ("hits", "misses"):
                expected = sum(item[f"{population}_{level}_{outcome}"]
                               for item in rois)
                name = f"{stat_prefix}{outcome.capitalize()}"
                check_equal(stat(stats, name, cache), expected,
                            f"{case.name} {cache}.{name}")


def se_command(args: argparse.Namespace, outdir: Path, binary: Path,
               *options: str) -> list[str]:
    return [str(args.gem5), f"--outdir={outdir}",
            str(ROOT / "configs/deprecated/example/se.py"), f"--cmd={binary}",
            *options]


TIMING = ("--cpu-type=TimingSimpleCPU", "--caches", "--l2cache")


def run_simpoint(case: Case, args: argparse.Namespace, build_dir: Path,
                 binary: Path, outdir: Path, stdout: Path, stderr: Path) -> None:
    """A SimPoint point as cache_scripts/simpoint.sh runs it: se.py takes the
    interval's checkpoint (AtomicSimpleCPU, no caches), then restores it into
    TimingSimpleCPU with caches, runs the warmup and the interval."""
    index, interval, warmup = case.simpoint
    simpoints, weights = build_dir / "simpoints.txt", build_dir / "weights.txt"
    simpoints.write_text(f"{index} 0\n")
    weights.write_text("1.0 0\n")
    cptdir = build_dir / "cpt"
    run(se_command(args, build_dir / "m5out_take", binary,
                   "--cpu-type=AtomicSimpleCPU",
                   f"--take-simpoint-checkpoints={simpoints},{weights},"
                   f"{interval},{warmup}",
                   f"--checkpoint-dir={cptdir}"),
        stdout=build_dir / "stdout_take.txt", stderr=build_dir / "stderr_take.txt")
    run(se_command(args, outdir, binary, *TIMING, *case.extra_args,
                   "--restore-with-cpu=TimingSimpleCPU",
                   "--restore-simpoint-checkpoint", "-r", "1",
                   f"--checkpoint-dir={cptdir}"),
        stdout=stdout, stderr=stderr)


def execute_case(case: Case, args: argparse.Namespace, workspace: Path) -> None:
    program = case.source or case.name
    source = TEST_ROOT / program / f"{program}.S"
    if not source.is_file():
        raise RuntimeError(f"missing source: {source}")

    build_dir = workspace / case.name
    build_dir.mkdir(parents=True)
    obj = build_dir / f"{program}.o"
    binary = build_dir / f"{program}.riscv"
    outdir = build_dir / "m5out"
    run([str(args.assembler), "-o", str(obj), str(source)])
    run([str(args.linker), "-o", str(binary), str(obj)])

    stdout = build_dir / "stdout.txt"
    stderr = build_dir / "stderr.txt"
    try:
        if case.simpoint:
            run_simpoint(case, args, build_dir, binary, outdir, stdout, stderr)
        else:
            run(se_command(args, outdir, binary, *TIMING, *case.extra_args),
                stdout=stdout, stderr=stderr)
        spill_log = outdir / "riscv_spill_stats.txt"
        stats_file = outdir / "stats.txt"
        if not spill_log.is_file() or not stats_file.is_file():
            raise AssertionError("gem5 did not produce spill log and stats.txt")
        rois, global_values = parse_spill_log(spill_log)
        validate_case(case, rois, global_values, parse_stats(stats_file))
        if case.rois and ("# detection          : runtime effective address only"
                          not in spill_log.read_text()):
            raise AssertionError(f"{case.name}: missing detection line")
        if case.roi_crosscheck:
            check_gem5_roi_crosscheck(case, args, build_dir, binary, outdir)
        if case.simpoint:
            check_simpoint_interval(case, outdir, rois[0])
        if case.expect_stderr and case.expect_stderr not in stderr.read_text(errors="replace"):
            raise AssertionError(f"{case.name}: gem5 stderr lacks {case.expect_stderr!r}")
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
    parser.add_argument("--gem5", type=Path,
                        default=ROOT / "build/RISCV_SCHEMA10/gem5.opt")
    parser.add_argument("--assembler", type=Path, default=DEFAULT_AS)
    parser.add_argument("--linker", type=Path, default=DEFAULT_LD)
    parser.add_argument("--keep", type=Path,
                        help="keep all generated artifacts in this directory")
    args = parser.parse_args()

    selected = [case for case in CASES if not args.cases or case.name in args.cases]
    unknown = set(args.cases) - {case.name for case in CASES}
    if unknown:
        parser.error(f"unknown cases: {', '.join(sorted(unknown))}")
    for tool in (args.gem5, args.assembler, args.linker):
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
