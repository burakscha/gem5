#!/usr/bin/env python3
"""Build the stack PC map that lets the SpillDetector classify stack traffic.

For one SPEC binary this writes <binary minus .riscv>.stack_pc_map with:

  spill_store / spill_load  register-allocator spill code. Taken from GCC
                            itself: every compile command of the binary's
                            SPEC build is re-run with `-S -dP`, which prints
                            each instruction's RTL. A memory operand whose
                            attributes name the LRA spill area (%sfp) is a
                            spill or a reload.
  csave_store               callee-saved register saves, ra included. Taken
                            from the binary's CFI (.eh_frame): wherever a
                            register's rule becomes "saved at CFA-N", the
                            store that wrote that slot is a callee save.

The rebuilt objects are only used to read PCs off. The script links them with
the original command and refuses to write a map unless .text, .data and
.rodata are byte-identical to the simulated binary, so every PC is valid for
it. The labels it inserts are local symbols and do not change any code.

usage:
  scripts/build_stack_pc_map.py benchmarks/mcf/mcf_r.riscv
  scripts/build_stack_pc_map.py --all            # every benchmarks/*/*.riscv
"""

from __future__ import annotations

import argparse
import bisect
import calendar
import collections
import concurrent.futures
import datetime
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT.parent / "cpu2017"
TOOLCHAIN = Path("/cta/research/level0/RISCV/bin")
CROSS = "riscv64-unknown-linux-gnu-"

# --------------------------------------------------------------------------
# 1. -dP annotation: label every sp/s0-relative load/store with its class
# --------------------------------------------------------------------------
MEMOP = re.compile(
    r"^\t(c\.)?(f?s[dwhb]|f?l[dwhb]u?)\t[^,]+,(-?\d+)?\((sp|s0)\)\s*#\s*(\d+)\s")
FUNC = re.compile(r"^([A-Za-z_][\w.$]*):\s*$")
RTL_HEADER = re.compile(r"^#\((\w+(?:/\w+)?) (\d+) ")
# MEM attributes look like "[3 %sfp+-56 S8 A64]", "[1 p8+0 S8 A128]" or
# "[0 MEM <char[1:8]> [(void *)&buf]+0 S8 A64]" (one level of nesting).
MEM_ATTRS = re.compile(r"\[(\d+) ((?:[^\[\]]|\[[^\]]*\])*?)\s*S\d+ A\d+")
STORE_MNEMONIC = re.compile(r"(c\.)?f?s[dwhb]$")
LABEL_PREFIX = "__stk_"


def classify_rtl(text: str) -> str:
    """Class of a memory instruction from its -dP RTL dump.

    SPILL        MEM attributes name the LRA spill area (%sfp)
    CALLEE_SAVE  frame-related insn (insn/f): prologue save / epilogue restore
    POINTER      MEM reached through a pointer (p->f, *p)
    NAMED        MEM attributes name a declaration (local or parameter)
    OUT_ARG      MEM without a declaration (outgoing stack arguments)
    OTHER        no RTL or no MEM attributes found
    """
    mem = MEM_ATTRS.search(text)
    expr = mem.group(2).strip() if mem else None
    if expr is not None and "%sfp" in expr:
        return "SPILL"
    if text.startswith("#(insn/f"):
        return "CALLEE_SAVE"
    if expr is None:
        return "OTHER"
    if expr == "":
        return "OUT_ARG"
    if "->" in expr or expr.startswith("*"):
        return "POINTER"
    return "NAMED"


def annotate(src: Path, dst: Path) -> collections.Counter:
    """Copy a `-S -dP` file, putting `__stk_<CLASS>_<S|L>_<n>:` before every
    sp/s0-relative load/store. Streams, so multi-GB dumps are fine."""
    counts: collections.Counter = collections.Counter()
    # -dP prints each insn's RTL right before its assembly line, so the
    # latest block seen for a UID is the right one. UIDs restart in every
    # function; resetting at function labels only bounds memory.
    rtl: dict[str, list[str]] = {}
    cur: list[str] | None = None
    n = 0
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            if FUNC.match(line):
                rtl, cur = {}, None
            header = RTL_HEADER.match(line)
            if header:
                cur = [line]
                rtl[header.group(2)] = cur
            elif line.startswith("#") and cur is not None:
                cur.append(line)
            mem = MEMOP.match(line)
            if mem:
                cls = classify_rtl("".join(rtl.get(mem.group(5), ())))
                kind = "S" if STORE_MNEMONIC.match(mem.group(2)) else "L"
                counts[f"{cls}_{kind}"] += 1
                fout.write(f"{LABEL_PREFIX}{cls}_{kind}_{n}:\n")
                n += 1
            fout.write(line)
    return counts


# --------------------------------------------------------------------------
# 2. Rebuild the SPEC objects through the annotator
# --------------------------------------------------------------------------
COMPILER = re.compile(r"^\s*(\S*-(gcc|g\+\+|gfortran|c\+\+))\s")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def find_build(binary: Path, spec_root: Path) -> tuple[Path, str]:
    """SPEC build directory and executable name that produced `binary`."""
    want = md5(binary)
    for build in sorted(spec_root.glob("benchspec/CPU/*/build/build_base_*")):
        for exe in build.iterdir():
            if (exe.is_file() and os.access(exe, os.X_OK) and exe.suffix == ""
                    and is_elf(exe) and md5(exe) == want):
                return build, exe.name
    raise SystemExit(f"{binary}: no SPEC build directory produced this binary "
                     f"(md5 {want}) under {spec_root}")


@dataclass
class BuildPlan:
    compiles: list[list[str]] = field(default_factory=list)
    others: list[str] = field(default_factory=list)   # ar/ranlib/link, ordered


def read_plan(make_log: Path, exe: str) -> BuildPlan:
    plan = BuildPlan()
    for line in make_log.read_text(errors="replace").splitlines():
        if COMPILER.match(line):
            tokens = shlex.split(line)
            if "-c" in tokens:
                plan.compiles.append(tokens)
            elif "-o" in tokens:
                plan.others.append(line)
        elif re.match(r"^\s*\S*(ar|ranlib)\s", line):
            plan.others.append(line)
    if not plan.compiles:
        raise SystemExit(f"{make_log}: no compile commands found")
    if not any(f"-o {exe}" in cmd or cmd.rstrip().endswith(exe)
               for cmd in plan.others):
        raise SystemExit(f"{make_log}: no link command for {exe}")
    return plan


def add_shared_compiles(plan: BuildPlan, build: Path, make_log: Path) -> int:
    """A build directory with several targets compiles the objects they share
    only under the first one (wrf: diffwrf_521 before wrf_r), so take those
    compile commands from the directory's other make.*.out logs."""
    have = {t[t.index("-o") + 1] for t in plan.compiles}
    added = 0
    for other in sorted(build.glob("make.*.out")):
        if other == make_log:
            continue
        for line in other.read_text(errors="replace").splitlines():
            if not COMPILER.match(line):
                continue
            tokens = shlex.split(line)
            if "-c" in tokens and "-o" in tokens:
                obj = tokens[tokens.index("-o") + 1]
                if obj not in have:
                    plan.compiles.append(tokens)
                    have.add(obj)
                    added += 1
    return added


def compile_annotated(tokens: list[str], cwd: Path, keep: bool):
    """-S -dP, annotate, assemble. Returns (object path, class counts)."""
    out = tokens.index("-o")
    obj = tokens[out + 1]
    raw = str(Path(obj).with_suffix(".dP.s"))
    labelled = str(Path(obj).with_suffix(".stk.s"))
    cmd = list(tokens)
    cmd[out + 1] = raw
    cmd[cmd.index("-c")] = "-S"
    cmd.insert(1, "-dP")
    run(cmd, cwd)
    counts = annotate(cwd / raw, cwd / labelled)
    target = [t for t in tokens if t.startswith(("-march=", "-mabi="))]
    run([tokens[0], *target, "-c", "-o", obj, labelled], cwd)
    if not keep:
        (cwd / raw).unlink()
        (cwd / labelled).unlink()
    return obj, counts


def run(cmd, cwd: Path, shell: bool = False) -> None:
    result = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=True,
                            text=True)
    if result.returncode != 0:
        shown = cmd if shell else " ".join(cmd)
        raise RuntimeError(f"command failed in {cwd}:\n{shown}\n"
                           f"{result.stderr[-2000:]}")


def section_bytes(binary: Path, section: str) -> bytes:
    with tempfile.NamedTemporaryFile() as tmp:
        subprocess.run([str(TOOLCHAIN / f"{CROSS}objcopy"), "-O", "binary",
                        f"--only-section={section}", str(binary), tmp.name],
                       check=True)
        return Path(tmp.name).read_bytes()


def section_addresses(binary: Path) -> dict[str, tuple[int, int]]:
    out = subprocess.run([str(TOOLCHAIN / f"{CROSS}readelf"), "-SW",
                          str(binary)], check=True, capture_output=True,
                         text=True).stdout
    found = {}
    for m in re.finditer(r"\]\s+(\.\S+)\s+\S+\s+([0-9a-f]+)\s+[0-9a-f]+\s+"
                         r"([0-9a-f]+)", out):
        found[m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16))
    return found


def build_timestamp(binary: Path) -> int | None:
    """SOURCE_DATE_EPOCH that reproduces the __DATE__/__TIME__ strings baked
    into `binary`, if it has exactly one of each (cactuBSSN's datestamp.c).

    GCC formats SOURCE_DATE_EPOCH in UTC, so the original local-time strings
    are converted as if they were UTC. A wrong guess only makes the
    byte-identical check below fail; it can never produce a bad map.
    """
    data = section_bytes(binary, ".rodata") + section_bytes(binary, ".data")
    dates = set(re.findall(rb"(?<![\w ])([A-Z][a-z]{2} [ \d]\d \d{4})\x00", data))
    times = set(re.findall(rb"(?<![\w:])(\d\d:\d\d:\d\d)\x00", data))
    if len(dates) != 1 or len(times) != 1:
        return None
    stamp = f"{dates.pop().decode()} {times.pop().decode()}"
    try:
        parsed = datetime.datetime.strptime(" ".join(stamp.split()),
                                            "%b %d %Y %H:%M:%S")
    except ValueError:
        return None
    return calendar.timegm(parsed.timetuple())


def rebuild(binary: Path, spec_root: Path, jobs: int, keep_dir: Path | None):
    build, exe = find_build(binary, spec_root)
    make_log = build / f"make.{exe}.out"
    if not make_log.is_file():
        make_log = build / "make.out"
    plan = read_plan(make_log, exe)
    shared = add_shared_compiles(plan, build, make_log)
    if keep_dir is not None and keep_dir.exists() and any(keep_dir.iterdir()):
        raise SystemExit(f"--keep {keep_dir}: directory exists and is not "
                         "empty; give a new path")
    work = Path(keep_dir) if keep_dir else Path(
        tempfile.mkdtemp(prefix=f"stkmap-{exe}-"))
    if work.exists():
        work.rmdir()           # empty (checked above) or fresh from mkdtemp
    shutil.copytree(build, work, symlinks=True)
    for obj in work.rglob("*.o"):
        obj.unlink()
    (work / exe).unlink(missing_ok=True)

    print(f"  build dir : {build}")
    print(f"  log       : {make_log.name} ({len(plan.compiles)} compiles"
          + (f", {shared} of them from the other make.*.out logs" if shared else "")
          + ")")
    print(f"  work dir  : {work}")
    epoch = build_timestamp(binary)
    if epoch is not None:
        os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
        print(f"  __DATE__/__TIME__ pinned via SOURCE_DATE_EPOCH={epoch}")
    else:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
    static = collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(compile_annotated, t, work, keep_dir is not None)
                   for t in plan.compiles]
        for future in concurrent.futures.as_completed(futures):
            static.update(future.result()[1])
    for cmd in plan.others:
        run(cmd, work, shell=True)
    rebuilt = work / exe

    for section in (".text", ".data", ".rodata"):
        if section_bytes(rebuilt, section) != section_bytes(binary, section):
            raise SystemExit(f"{binary}: rebuilt {section} differs; refusing "
                             f"to write a map (work dir kept: {work})")
    if section_addresses(rebuilt).get(".text") != \
            section_addresses(binary).get(".text"):
        raise SystemExit(f"{binary}: .text address/size differs")
    return build, exe, work, rebuilt, static


def labelled_pcs(rebuilt: Path) -> dict[tuple[str, str], set[int]]:
    out = subprocess.run([str(TOOLCHAIN / f"{CROSS}nm"), str(rebuilt)],
                         check=True, capture_output=True, text=True).stdout
    pcs: dict[tuple[str, str], set[int]] = collections.defaultdict(set)
    label = re.compile(rf"^([0-9a-f]+) \w {LABEL_PREFIX}([A-Z_]+?)_([SL])_\d+$")
    for line in out.splitlines():
        m = label.match(line)
        if m:
            pcs[(m.group(2), m.group(3))].add(int(m.group(1), 16))
    return pcs


# --------------------------------------------------------------------------
# 3. CFI: callee-saved register save stores
# --------------------------------------------------------------------------
CALLEE_SAVED = {"ra", *(f"s{i}" for i in range(12)),
                *(f"fs{i}" for i in range(12))}
INSN = re.compile(r"^\s*([0-9a-f]+):\s+(\S+)\s+([^,\s]+),(-?\d+)\((\w+)\)")


def disassembly_stores(binary: Path):
    """Sorted PCs and, per PC, (mnemonic, reg, offset, base) of every
    register+offset store."""
    out = subprocess.run([str(TOOLCHAIN / f"{CROSS}objdump"), "-d",
                          "--no-show-raw-insn", str(binary)], check=True,
                         capture_output=True, text=True).stdout
    pcs, info = [], {}
    for line in out.splitlines():
        m = INSN.match(line)
        if m and m.group(2) in ("sd", "sw", "fsd", "fsw"):
            pc = int(m.group(1), 16)
            pcs.append(pc)
            info[pc] = (m.group(3), int(m.group(4)), m.group(5))
    return pcs, info


def cfi_csave_stores(binary: Path) -> tuple[set[int], int]:
    """Store PCs that save a callee-saved register, from .eh_frame.

    readelf's interpreted table gives, per FDE row, the CFA rule ("sp+224")
    and per register "c-N" (saved at CFA-N) or "u". When a register turns
    "c-N" at row L, the save is the last store before L that writes that
    register to CFA-N, using the CFA rule in force at the store itself.
    Returns (pcs, saves that could not be matched to a store).
    """
    store_pcs, store_info = disassembly_stores(binary)
    text = subprocess.run([str(TOOLCHAIN / f"{CROSS}readelf"),
                           "--debug-dump=frames-interp", str(binary)],
                          check=True, capture_output=True, text=True).stdout
    found: set[int] = set()
    unmatched = 0

    def resolve(rows, columns):
        nonlocal unmatched
        prev = {}
        cfa_locs = [r[0] for r in rows]
        for loc, cfa, regs in rows:
            for reg, rule in zip(columns, regs):
                if reg in CALLEE_SAVED and rule.startswith("c-") and \
                        prev.get(reg) != rule:
                    slot_from_cfa = -int(rule[2:])
                    pc = match_store(reg, slot_from_cfa, loc, rows, cfa_locs)
                    if pc is None:
                        unmatched += 1
                    else:
                        found.add(pc)
                prev[reg] = rule

    def match_store(reg, slot_from_cfa, loc, rows, cfa_locs):
        fde_start = rows[0][0]
        i = bisect.bisect_left(store_pcs, loc) - 1
        while i >= 0 and store_pcs[i] >= fde_start:
            pc = store_pcs[i]
            sreg, off, base = store_info[pc]
            if sreg == reg:
                # Use the latest CFA rule written in the store's own base
                # register: frame-pointer prologues switch the CFA to s0
                # (addi s0,sp,N) but keep saving through sp.
                j = bisect.bisect_right(cfa_locs, pc) - 1
                while j >= 0:
                    m = re.match(r"(\w+)\+(\d+)$", rows[j][1])
                    if m and m.group(1) == base:
                        if off == int(m.group(2)) + slot_from_cfa:
                            return pc
                        break
                    j -= 1
            i -= 1
        return None

    columns, rows = None, []
    for line in text.splitlines():
        if " FDE " in line:
            if columns and rows:
                resolve(rows, columns)
            columns, rows = None, []
        elif line.strip().startswith("LOC"):
            columns = line.split()[2:]
        elif columns is not None:
            parts = line.split()
            if len(parts) >= 2 and re.match(r"^[0-9a-f]{8,}$", parts[0]):
                rows.append((int(parts[0], 16), parts[1], parts[2:]))
    if columns and rows:
        resolve(rows, columns)
    return found, unmatched


# --------------------------------------------------------------------------
# 4. Driver
# --------------------------------------------------------------------------
def build_map(binary: Path, spec_root: Path, jobs: int,
              keep_dir: Path | None, out: Path | None) -> Path:
    binary = binary.resolve()
    print(f"{binary.relative_to(ROOT) if binary.is_relative_to(ROOT) else binary}")
    build, exe, work, rebuilt, static = rebuild(binary, spec_root, jobs,
                                                keep_dir)
    pcs = labelled_pcs(rebuilt)
    spill_store = pcs[("SPILL", "S")]
    spill_load = pcs[("SPILL", "L")]
    dp_csave = pcs[("CALLEE_SAVE", "S")]
    cfi_csave, unmatched = cfi_csave_stores(binary)
    if keep_dir is None:
        shutil.rmtree(work)

    # Cross-check: in code GCC compiled here, CFI saves and -dP frame-related
    # stores should be the same set. CFI additionally covers libc.
    labelled_any = set().union(*pcs.values()) if pcs else set()
    cfi_in_labelled = cfi_csave & labelled_any
    overlap = cfi_csave & spill_store
    if overlap:
        raise SystemExit(f"{binary}: {len(overlap)} PCs are both spill and "
                         "csave stores")

    out = out or binary.with_suffix(".stack_pc_map")
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# stack PC map for the SpillDetector (metric schema 8 and later)",
        f"# binary      : {binary}",
        f"# binary md5  : {md5(binary)}",
        f"# spec build  : {build}",
        f"# generated   : {stamp} by scripts/build_stack_pc_map.py",
        "# spill_*     : GCC -dP, MEM attributes naming the LRA spill area",
        "# csave_store : .eh_frame CFI register saves (callee-saved regs, ra)",
        f"# counts      : spill_store={len(spill_store)} "
        f"spill_load={len(spill_load)} csave_store={len(cfi_csave)}",
        f"# cfi check   : cfi saves in -dP code={len(cfi_in_labelled)}, "
        f"-dP frame-related stores={len(dp_csave)}, "
        f"agreeing={len(cfi_in_labelled & dp_csave)}, "
        f"unmatched cfi saves={unmatched}",
        "# static -dP classes (sp/s0-relative memory insns): " +
        ", ".join(f"{k}={v}" for k, v in sorted(static.items())),
    ]
    for kind, pc_set in (("spill_store", spill_store),
                         ("spill_load", spill_load),
                         ("csave_store", cfi_csave)):
        lines += [f"{kind} {pc:#x}" for pc in sorted(pc_set)]
    out.write_text("\n".join(lines) + "\n")
    for line in lines[7:10]:
        print("  " + line[2:])
    print(f"  wrote {out}", flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("binaries", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true",
                        help="every benchmarks/*/*.riscv")
    parser.add_argument("--spec-root", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--keep", type=Path,
                        help="keep the rebuild (dumps included) in this dir")
    parser.add_argument("--out", type=Path, help="map path (one binary only)")
    args = parser.parse_args()

    binaries = sorted((ROOT / "benchmarks").glob("*/*.riscv")) if args.all \
        else args.binaries
    if not binaries:
        parser.error("give binaries or --all")
    failures = 0
    for binary in binaries:
        try:
            build_map(binary, args.spec_root, args.jobs, args.keep, args.out)
        except (SystemExit, RuntimeError) as error:
            failures += 1
            print(f"  FAILED: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
