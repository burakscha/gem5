#!/bin/bash
# Launch all ref/train simulations
# Must be run from: /cta/users/bkaya/riscv-spec-register-spilling/gem5/
# Usage: bash launch_ref_all.sh

GEM5=./build/RISCV/gem5.opt
CFG=configs/deprecated/example/se.py
OPTS="--cpu-type=TimingSimpleCPU --caches --mem-size=4GB"

cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/ || exit 1

echo "=== Launching all simulations from $(pwd) ==="
echo "=== $(date) ==="

# -------------------------------------------------------
# 1. cactuBSSN train
# -------------------------------------------------------
echo "[1/19] cactuBSSN train"
nohup $GEM5 \
  --outdir=benchmarks/cactuBSSN/m5out_train $CFG \
  --cmd=benchmarks/cactuBSSN/cactuBSSN_r.riscv \
  --options=benchmarks/cactuBSSN/spec_train.par \
  $OPTS \
  > benchmarks/cactuBSSN/m5out_train/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 2. parest train
# -------------------------------------------------------
echo "[2/19] parest train"
mkdir -p benchmarks/parest/m5out_train
nohup $GEM5 \
  --outdir=benchmarks/parest/m5out_train $CFG \
  --cmd=benchmarks/parest/parest_r.riscv \
  --options=benchmarks/parest/train.prm \
  $OPTS \
  > benchmarks/parest/m5out_train/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 3. deepsjeng ref  (ref.txt — same structure as train)
# -------------------------------------------------------
echo "[3/19] deepsjeng ref"
mkdir -p benchmarks/deepsjeng/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/deepsjeng/m5out_ref $CFG \
  --cmd=benchmarks/deepsjeng/deepsjeng_r.riscv \
  --options=benchmarks/deepsjeng/ref.txt \
  $OPTS \
  > benchmarks/deepsjeng/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 4. leela ref  (ref.sgf)
# -------------------------------------------------------
echo "[4/19] leela ref"
mkdir -p benchmarks/leela/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/leela/m5out_ref $CFG \
  --cmd=benchmarks/leela/leela_r.riscv \
  --options=benchmarks/leela/ref.sgf \
  $OPTS \
  > benchmarks/leela/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 5. xz ref  (cld.tar.xz, level 6, 160 MB)
# -------------------------------------------------------
echo "[5/19] xz ref"
mkdir -p benchmarks/xz/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/xz/m5out_ref $CFG \
  --cmd=benchmarks/xz/xz_r.riscv \
  '--options=benchmarks/xz/cld.tar.xz 160 19cf30ae51eddcbefda78dd06014b4b96281456e078ca7c13e1c0c9e6aaea8dff3efb4ad6b0456697718cede6bd5454852652806a657bb56e07d61128434b474 59796407 61004416 6' \
  $OPTS \
  > benchmarks/xz/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 6. lbm ref  (100_100_130_ldc.of, 3000 steps)
# -------------------------------------------------------
echo "[6/19] lbm ref"
mkdir -p benchmarks/lbm/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/lbm/m5out_ref $CFG \
  --cmd=benchmarks/lbm/lbm_r.riscv \
  '--options=3000 benchmarks/lbm/reference.dat 0 0 benchmarks/lbm/100_100_130_ldc.of' \
  $OPTS \
  > benchmarks/lbm/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 7. xalancbmk ref  (t5.xml + xalanc.xsl)
# -------------------------------------------------------
echo "[7/19] xalancbmk ref"
mkdir -p benchmarks/xalancbmk/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/xalancbmk/m5out_ref $CFG \
  --cmd=benchmarks/xalancbmk/xalancbmk_r.riscv \
  '--options=-v benchmarks/xalancbmk/t5.xml benchmarks/xalancbmk/xalanc.xsl' \
  $OPTS \
  > benchmarks/xalancbmk/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 8. x264 ref  (ldecod: decode BuckBunny.264 full file)
# -------------------------------------------------------
echo "[8/19] x264 ref (ldecod)"
mkdir -p benchmarks/x264/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/x264/m5out_ref $CFG \
  --cmd=benchmarks/x264/ldecod_r.riscv \
  '--options=-i benchmarks/x264/BuckBunny.264 -o benchmarks/x264/BuckBunny_ref.yuv' \
  $OPTS \
  > benchmarks/x264/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 9. namd ref  (apoa1.input, 65 iterations)
# -------------------------------------------------------
echo "[9/19] namd ref"
mkdir -p benchmarks/namd/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/namd/m5out_ref $CFG \
  --cmd=benchmarks/namd/namd_r.riscv \
  '--options=--input benchmarks/namd/apoa1.input --output benchmarks/namd/apoa1.ref.output --iterations 65' \
  $OPTS \
  > benchmarks/namd/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 10. omnetpp ref  (omnetpp.ini with sim-time 2.25s — copied to gem5 root)
# -------------------------------------------------------
echo "[10/19] omnetpp ref"
mkdir -p benchmarks/omnetpp/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/omnetpp/m5out_ref $CFG \
  --cmd=benchmarks/omnetpp/omnetpp_r.riscv \
  '--options=-c General -r 0' \
  $OPTS \
  > benchmarks/omnetpp/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 11. povray ref  (SPEC-benchmark-ref.ini)
# -------------------------------------------------------
echo "[11/19] povray ref"
mkdir -p benchmarks/povray/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/povray/m5out_ref $CFG \
  --cmd=benchmarks/povray/povray_r.riscv \
  --options=benchmarks/povray/SPEC-benchmark-ref.ini \
  $OPTS \
  > benchmarks/povray/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 12. imagick ref  (refrate_input.tga, complex filter chain)
# -------------------------------------------------------
echo "[12/19] imagick ref"
mkdir -p benchmarks/imagick/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/imagick/m5out_ref $CFG \
  --cmd=benchmarks/imagick/imagick_r.riscv \
  '--options=-limit disk 0 benchmarks/imagick/refrate_input.tga -edge 41 -resample 181% -emboss 31 -colorspace YUV -mean-shift 19x19+15% -resize 30% benchmarks/imagick/refrate_output.tga' \
  $OPTS \
  > benchmarks/imagick/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 13. nab ref  (1am0 molecule, 1am0.pdb/prm at gem5/1am0/)
# -------------------------------------------------------
echo "[13/19] nab ref"
mkdir -p benchmarks/nab/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/nab/m5out_ref $CFG \
  --cmd=benchmarks/nab/nab_r.riscv \
  '--options=1am0 1122214447 122' \
  $OPTS \
  > benchmarks/nab/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 14. blender ref  (sh3_no_char.blend, frame 849)
# -------------------------------------------------------
echo "[14/19] blender ref"
mkdir -p benchmarks/blender/m5out_ref
nohup $GEM5 \
  --outdir=benchmarks/blender/m5out_ref $CFG \
  --cmd=benchmarks/blender/blender_r.riscv \
  '--options=benchmarks/blender/sh3_no_char.blend --render-output benchmarks/blender/sh3_ --threads 1 -b -F RAWTGA -s 849 -e 849 -a' \
  $OPTS \
  > benchmarks/blender/m5out_ref/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 15. perlbench ref — 3 separate runs
# -------------------------------------------------------
echo "[15/19] perlbench ref: checkspam"
mkdir -p benchmarks/perlbench/m5out_ref_checkspam
nohup $GEM5 \
  --outdir=benchmarks/perlbench/m5out_ref_checkspam $CFG \
  --cmd=benchmarks/perlbench/perlbench_r.riscv \
  '--options=-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/checkspam.pl 2500 5 25 11 150 1 1 1 1' \
  $OPTS \
  > benchmarks/perlbench/m5out_ref_checkspam/nohup.log 2>&1 &
echo "  PID=$!"

echo "[16/19] perlbench ref: diffmail"
mkdir -p benchmarks/perlbench/m5out_ref_diffmail
nohup $GEM5 \
  --outdir=benchmarks/perlbench/m5out_ref_diffmail $CFG \
  --cmd=benchmarks/perlbench/perlbench_r.riscv \
  '--options=-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/diffmail.pl 4 800 10 17 19 300' \
  $OPTS \
  > benchmarks/perlbench/m5out_ref_diffmail/nohup.log 2>&1 &
echo "  PID=$!"

echo "[17/19] perlbench ref: splitmail"
mkdir -p benchmarks/perlbench/m5out_ref_splitmail
nohup $GEM5 \
  --outdir=benchmarks/perlbench/m5out_ref_splitmail $CFG \
  --cmd=benchmarks/perlbench/perlbench_r.riscv \
  '--options=-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/splitmail.pl 6400 12 26 16 100 0' \
  $OPTS \
  > benchmarks/perlbench/m5out_ref_splitmail/nohup.log 2>&1 &
echo "  PID=$!"

# -------------------------------------------------------
# 18. namd ref already counted above as #9
# -------------------------------------------------------

echo ""
echo "=== All launched. $(date) ==="
echo "=== Check status with: ==="
echo "  ps aux | grep gem5 | grep -v grep | wc -l"
