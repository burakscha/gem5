#!/usr/bin/env python3
"""Build benchmarks/<bench>/<input>/inputs/: one SPEC run directory per
benchmark and input set, holding exactly what SPEC copies into its run
directory for that size: data/<size>/input (copied; small, and the names
repeat across sizes with other contents) and data/all/input (linked; shared
and large). The runner runs a workload with such a run_dir in a private copy
of it, with SPEC's own relative command line.

    cache_scripts/make_input_dirs.py ref                 # every benchmark
    cache_scripts/make_input_dirs.py train bwaves wrf    # selected ones
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT.parent / "cpu2017" / "benchspec" / "CPU"
SIZES = {"test": "test", "train": "train", "ref": "refrate"}


def spec_dir(bench: str) -> Path:
    found = [d for d in SPEC.glob(f"*.{bench}_r") if d.is_dir()]
    if not found:
        raise SystemExit(f"no SPEC directory for {bench}")
    return found[0]


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in SIZES:
        print(__doc__)
        return 2
    size = sys.argv[1]
    benches = sys.argv[2:] or sorted(p.name for p in (ROOT / "benchmarks").iterdir()
                                     if any(p.glob("*.riscv")))
    for bench in benches:
        src = spec_dir(bench) / "data"
        dst = ROOT / "benchmarks" / bench / size / "inputs"
        dst.mkdir(parents=True, exist_ok=True)
        copied = linked = 0
        own = src / SIZES[size] / "input"
        for f in sorted(own.iterdir()) if own.is_dir() else []:
            target = dst / f.name
            if target.exists() or target.is_symlink():
                continue
            if f.is_dir():
                shutil.copytree(f, target)
            else:
                shutil.copy2(f, target)
            copied += 1
        shared = src / "all" / "input"
        for f in sorted(shared.iterdir()) if shared.is_dir() else []:
            target = dst / f.name
            if target.exists() or target.is_symlink():
                continue
            os.symlink(f, target)
            linked += 1
        print(f"{bench:10s} {size}: {copied} copied ({SIZES[size]}/input), "
              f"{linked} linked (all/input) -> {dst.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
