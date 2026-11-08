#!/usr/bin/env python3
"""Turn ckpt_dump.c's qemu state dumps into gem5 SE SimPoint checkpoints.

gem5's own route to a SimPoint checkpoint runs AtomicSimpleCPU from the
program's start to every simulation point (about 1.5M instructions/s, weeks
for a ref run). qemu gets there at hundreds of MIPS; this script writes what
it dumped as checkpoint directories that

    se.py --restore-simpoint-checkpoint -r N --checkpoint-dir DIR ...

restores exactly like the ones --take-simpoint-checkpoints makes (same
directory names, so the restore side does not change).

    qemu2gem5.py plan --simpoints S --weights W --interval I --warmup U --out PLAN
        PLAN: per simulation point, sorted by position like gem5 sorts them:
        "index checkpoint_inst weight warmup start_interval"; `cut -d' ' -f2`
        is the at= list for ckpt_dump.c.
    qemu2gem5.py convert --template CPT --plan PLAN --dumps DIR --out CPTDIR
                         [--stdin PATH]
        DIR/dump_<k> holds the dump of the plan's k-th line.

The template is any checkpoint gem5 took with the restore's system (se.py,
AtomicSimpleCPU, same --mem-size): its system sections are kept, and the
program state is replaced:
  - registers (x1-x31, f0-f31, pc, fflags/frm), the instruction count;
  - memory: one physical page per dumped page, in dump order, so pages.gz is
    the physical memory image as it stands (gem5 reads the image until it
    ends and leaves the rest zero); pages the dump left out are zero and are
    mapped lazily through the VMAs, as gem5 maps untouched pages anyway;
  - VMAs (ELF segments, brk heap, mmap areas, stack, vdso), brk and stack
    bounds; gem5's own mmap area starts above all of them;
  - open files: stdin/stdout/stderr as gem5 names them, files opened for
    reading by their path, files opened for writing go to /dev/null.
The text pages are the qemu binary's, whose m5ops are NOPs: inside a SimPoint
interval the configuration script, not the program, opens and closes the ROI.
Physical page placement differs from gem5's first-touch order; caches whose
way size is at most a page (all L1D/L2 organisations of the study) index
within the page offset and see no difference.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PAGE = 4096
GEM5_MMAP_BASE = 0x4000000000000000   # RISC-V SE Process::mmapEnd at start
MISCREG_FFLAGS, MISCREG_FRM = 120, 121
GPR = ["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2", "fp", "s1",
       "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
       "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11",
       "t3", "t4", "t5", "t6"]
FPR = (["ft%d" % i for i in range(8)] + ["fs0", "fs1"] + ["fa%d" % i for i in range(8)]
       + ["fs%d" % i for i in range(2, 12)] + ["ft%d" % i for i in range(8, 12)])
VMA_NAME = {"elf": "elf", "heap": "heap", "mmap": "anon", "stack": "stack", "vdso": "vdso"}
O_ACCMODE, O_CREAT, O_TRUNC, O_EXCL, O_CLOEXEC = 0o3, 0o100, 0o1000, 0o200, 0o2000000


def cmd_plan(a) -> int:
    weight = {}
    for line in open(a.weights):
        w, c = line.split()
        weight[int(c)] = float(w)
    pts = []
    for line in open(a.simpoints):
        idx, c = map(int, line.split())
        start = idx * a.interval
        # gem5's parseSimpointAnalysisFile: no room for the warmup -> from 0
        if start > a.warmup:
            pts.append((start - a.warmup, weight[c], a.warmup, idx))
        else:
            pts.append((0, weight[c], start, idx))
    pts.sort()
    with open(a.out, "w") as f:
        for i, (inst, w, warm, idx) in enumerate(pts):
            f.write(f"{i} {inst} {w:f} {warm} {idx}\n")
    return 0


def read_cpt(path: Path) -> tuple[list[str], list[list]]:
    head, sections, cur = [], [], None
    for line in path.read_text().splitlines():
        if line.startswith("[") and line.endswith("]"):
            cur = [line[1:-1], []]
            sections.append(cur)
        elif cur is None:
            head.append(line)
        elif line:
            cur[1].append(line)
    return head, sections


def kv(lines: list[str]) -> dict[str, str]:
    return dict(l.split("=", 1) for l in lines if "=" in l)


def set_kv(lines: list[str], key: str, value) -> None:
    for i, l in enumerate(lines):
        if l.split("=", 1)[0] == key:
            lines[i] = f"{key}={value}"
            return
    raise KeyError(key)


def le_bytes(hexstr: str, n: int) -> list[int]:
    b = bytes.fromhex(hexstr)[:n]
    return list(b) + [0] * (n - len(b))


def merge(regions: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    out: list[list] = []
    for kind, s, e in sorted(regions, key=lambda r: r[1]):
        if out and s <= out[-1][2]:
            out[-1][2] = max(out[-1][2], e)
        else:
            out.append([kind, s, e])
    return [tuple(r) for r in out]


def convert_one(template: Path, dump: Path, out: Path, stdin: str) -> None:
    head, secs = read_cpt(template / "m5.cpt")
    sec = {name: lines for name, lines in secs}
    regs = {}
    for line in (dump / "regs.txt").read_text().splitlines():
        name, _feature, value = line.split()
        regs[name] = value
    info = dict(l.split() for l in (dump / "info.txt").read_text().splitlines())
    regions = [(k, int(s, 16), int(e, 16)) for k, s, e in
               (l.split() for l in (dump / "regions.txt").read_text().splitlines())]
    pages = [int(l, 16) for l in (dump / "pages.idx").read_text().split()]

    # registers
    xc = sec["system.cpu.xc.0"]
    ints = [int(x) for x in kv(xc)["regs.integer"].split()]
    ints[:256] = sum((le_bytes(regs[r], 8) for r in GPR), [])
    ints[:8] = [0] * 8
    set_kv(xc, "regs.integer", " ".join(map(str, ints)))
    fps = sum((le_bytes(regs[r], 8) for r in FPR), [])
    set_kv(xc, "regs.floating_point", " ".join(map(str, fps)))
    pc = int.from_bytes(bytes.fromhex(regs["pc"]), "little")
    set_kv(xc, "_pc", pc)
    set_kv(xc, "_npc", pc + 4)
    set_kv(xc, "_upc", 0)
    set_kv(xc, "_nupc", 1)
    set_kv(xc, "_compressed", "false")
    isa = sec["system.cpu.isa"]
    misc = kv(isa)["miscRegFile"].split()
    misc[MISCREG_FFLAGS] = str(int.from_bytes(bytes.fromhex(regs["fflags"]), "little"))
    misc[MISCREG_FRM] = str(int.from_bytes(bytes.fromhex(regs["frm"]), "little"))
    set_kv(isa, "miscRegFile", " ".join(misc))
    set_kv(sec["system.cpu"], "instCnt", int(info["icount"]))

    # process: memory state, page table, files
    old_ws = kv(sec["system.cpu.workload"])
    stack = next(((s, e) for k, s, e in regions if k == "stack"), None)
    if stack is None:
        sys.exit(f"{dump}: no stack region")
    top = max(e for _, _, e in regions)
    if top >= GEM5_MMAP_BASE:
        sys.exit(f"{dump}: guest memory reaches gem5's mmap area ({top:#x})")
    max_stack = max(int(old_ws["maxStackSize"]), stack[1] - stack[0])
    ws: list[list] = [["system.cpu.workload", [
        f"brkPoint={int(info['brk'], 16)}",
        f"stackBase={stack[1]}",
        f"stackSize={stack[1] - stack[0]}",
        f"maxStackSize={max_stack}",
        f"stackMin={stack[0]}",
        f"nextThreadStackBase={stack[1] - max_stack}",
        f"mmapEnd={GEM5_MMAP_BASE}",
    ]]]
    vmas = merge(regions)
    ws.append(["system.cpu.workload.vmalist", [f"size={len(vmas)}"]])
    for i, (kind, s, e) in enumerate(vmas):
        ws.append([f"system.cpu.workload.vmalist.Vma{i}",
                   [f"name={VMA_NAME[kind]}", f"addrRangeStart={s}", f"addrRangeEnd={e}"]])
    ws.append(["system.cpu.workload.ptable", [f"size={len(pages)}"]])
    for i, va in enumerate(pages):
        ws.append([f"system.cpu.workload.ptable.Entry{i}",
                   [f"vaddr={va}", f"paddr={i * PAGE}", "flags=0"]])

    fd_tpl = {name: lines for name, lines in secs if name.startswith("system.cpu.workload.fdarray.")}
    n_fds = int(kv(sec["system.cpu.workload.fdarray"])["size"])
    files = {}
    for line in (dump / "fds.txt").read_text().splitlines():
        fd, pos, flags, path = line.split(" ", 3)
        files[int(fd)] = (int(pos), int(flags, 8), path)
    ws.append(["system.cpu.workload.fdarray", [f"size={n_fds}"]])
    for fd in range(n_fds):
        name = f"system.cpu.workload.fdarray.Entry{fd}"
        tpl = fd_tpl.get(name, ["class=6"])
        if fd <= 2:
            lines = list(tpl)
            if fd == 0:
                set_kv(lines, "_fileName", stdin)
                set_kv(lines, "_fileOffset", files[0][0] if stdin != "cin" and 0 in files else 0)
            ws.append([name, lines])
        elif fd in files:
            pos, flags, path = files[fd]
            if flags & O_ACCMODE:            # opened for writing: output only
                path, flags, pos = "/dev/null", flags & ~(O_CREAT | O_TRUNC | O_EXCL), 0
            ws.append([name, ["class=2", f"_closeOnExec={'true' if flags & O_CLOEXEC else 'false'}",
                              f"_flags={flags}", f"_fileName={path}", f"_fileOffset={pos}",
                              "_mode=0"]])
        else:
            ws.append([name, ["class=6"]])

    pool = sec["system.workload.mempools.pool0"]
    total = int(kv(pool)["total_pages"]) - int(kv(pool)["start_page"])
    if len(pages) > total:
        sys.exit(f"{dump}: {len(pages)} pages do not fit in {total}")
    free = [["system.workload.mempools.pool0.free_list", ["size=1"]],
            ["system.workload.mempools.pool0.free_list.free0",
             [f"base={int(kv(pool)['start_page']) + len(pages)}", f"size={total - len(pages)}"]]]

    out_secs: list[list] = []
    for name, lines in secs:
        if name.startswith("system.cpu.workload"):
            if name == "system.cpu.workload":
                out_secs += ws
            continue
        if name.startswith("system.workload.mempools.pool0.free_list"):
            if name == "system.workload.mempools.pool0.free_list":
                out_secs += free
            continue
        out_secs.append([name, lines])

    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with open(tmp / "m5.cpt", "w") as f:
        f.write("\n".join(head) + "\n")
        for name, lines in out_secs:
            f.write(f"[{name}]\n" + "".join(l + "\n" for l in lines) + "\n")
    store = kv(sec["system.physmem.store0"])["filename"]
    try:
        os.link(dump / "pages.gz", tmp / store)
    except OSError:
        shutil.copy(dump / "pages.gz", tmp / store)
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)


def cmd_convert(a) -> int:
    template = Path(a.template)
    if not (template / "m5.cpt").is_file():
        sys.exit(f"{template}: no m5.cpt")
    plan = [l.split() for l in open(a.plan) if l.strip()]
    interval = a.interval
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for k, (i, inst, w, warm, _idx) in enumerate(plan):
        dump = Path(a.dumps) / f"dump_{k:02d}"
        if not (dump / "info.txt").is_file():
            print(f"{dump}: missing, skipped", file=sys.stderr)
            continue
        name = ("cpt.simpoint_%02d_inst_%d_weight_%f_interval_%d_warmup_%d"
                % (int(i), int(inst), float(w), interval, int(warm)))
        convert_one(template, dump, Path(a.out) / name, a.stdin)
        print(name)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--simpoints", required=True)
    p.add_argument("--weights", required=True)
    p.add_argument("--interval", type=int, required=True)
    p.add_argument("--warmup", type=int, required=True)
    p.add_argument("--out", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--template", required=True)
    c.add_argument("--plan", required=True)
    c.add_argument("--dumps", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--interval", type=int, required=True)
    c.add_argument("--stdin", default="cin",
                   help="the --input se.py restores with (gem5 keeps the stdin offset "
                        "only when the names match)")
    a = ap.parse_args()
    return cmd_plan(a) if a.cmd == "plan" else cmd_convert(a)


if __name__ == "__main__":
    sys.exit(main())
