#!/usr/bin/env python3
"""Copy a RISC-V binary with every m5op instruction (custom-3 opcode 0x7b at
an m5_* symbol) replaced by a NOP, so the binary runs under qemu-user.

    patch_m5ops.py SRC DST [--gem5-compat]

--gem5-compat also makes glibc's _dl_get_origin return -1 at once. Static
glibc stores the directory of readlink("/proc/self/exe") on the heap at
start-up; under gem5 that readlink fails (/proc is redirected), so nothing is
allocated, while qemu answers it. Without the patch every later heap object
sits at a different address than in gem5, which changes which cache sets the
data map to (cache_scripts/qemu/ckpt_dump.c makes checkpoints from such runs).

DST is written to a temporary file and renamed, so qemu processes running the
old DST keep their copy.
"""
import os, shutil, struct, subprocess, sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
gem5_compat = "--gem5-compat" in sys.argv[1:]
src, dst = args[0], args[1]
P = "/cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu-"
secs = []
for line in subprocess.run([P + "readelf", "-SW", src], capture_output=True, text=True).stdout.splitlines():
    f = line.replace("[ ", "[").split()
    if len(f) > 6 and f[0].startswith("[") and f[0] != "[Nr]" and f[2] == "PROGBITS":
        secs.append((int(f[3], 16), int(f[4], 16), int(f[5], 16)))
data = bytearray(open(src, "rb").read())


def file_offset(addr):
    for va, off, size in secs:
        if va <= addr < va + size:
            return off + addr - va
    return None


patched = origin = 0
for line in subprocess.run([P + "nm", src], capture_output=True, text=True).stdout.splitlines():
    f = line.split()
    if len(f) != 3 or f[1] not in "Tt":
        continue
    o = file_offset(int(f[0], 16))
    if o is None:
        continue
    if f[2].startswith("m5_"):
        w = struct.unpack_from("<I", data, o)[0]
        if w & 0x7f == 0x7b:
            struct.pack_into("<I", data, o, 0x00000013)          # nop
            patched += 1
    elif gem5_compat and f[2] == "_dl_get_origin":
        struct.pack_into("<II", data, o, 0xfff00513, 0x00008067)  # li a0,-1 ; ret
        origin = 1
tmp = dst + ".tmp"
with open(tmp, "wb") as fo:
    fo.write(data)
shutil.copymode(src, tmp)
os.replace(tmp, dst)
print(f"{dst}: {patched} m5ops patched" + (f", _dl_get_origin {'patched' if origin else 'NOT FOUND'}"
                                          if gem5_compat else ""))
