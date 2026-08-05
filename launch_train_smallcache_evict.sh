#!/bin/bash
# launch_train_smallcache_evict.sh
#
# Tüm SPEC CPU2017 benchmark'larını TRAIN inputlarıyla, küçültülmüş cache
# konfigürasyonuyla çalıştırır.
#
# Cache boyutları:
#   L1D : 4KiB   (normal: 64KiB)
#   L1I : 32KiB  (değiştirilmedi)
#   L2  : 32KiB  (normal: 2MiB)
#
# Kullanım:
#   cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/
#   bash launch_train_smallcache_evict.sh
#
# Çıktı dizinleri: benchmarks/<bench>/m5out_train_sc_evict/
# Sonuç: bash benchmarks/analyze_spill_cache.sh --train-sc

set -euo pipefail

cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/ || exit 1

GEM5=./build/RISCV/gem5.opt
CFG=configs/deprecated/example/se.py
OPTS="--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB --l1d_size=4kB --l1i_size=32kB --l2_size=32kB"
B=benchmarks

echo "=== launch_train_smallcache_evict.sh ==="
echo "=== Cache: L1D=4kB  L1I=32kB  L2=32kB ==="
echo "=== $(date) ==="
echo ""

launch() {
    local label="$1" outdir="$2" cmd="$3" options="$4"
    mkdir -p "$outdir"
    rm -f "$outdir/stats.txt" "$outdir/riscv_spill_stats.txt"
    nohup $GEM5 --outdir="$outdir" $CFG \
        --cmd="$cmd" --options="$options" \
        $OPTS \
        > "$outdir/nohup.log" 2>&1 &
    printf "  [%-20s] PID=%-6s  outdir=%s\n" "$label" "$!" "$outdir"
}

# ── 1. deepsjeng ──────────────────────────────────────────────────────────
echo "[1] deepsjeng (train)"
launch "deepsjeng" \
    "$B/deepsjeng/m5out_train_sc_evict" \
    "$B/deepsjeng/deepsjeng_r.riscv" \
    "$B/deepsjeng/train.txt"

# ── 2. leela ──────────────────────────────────────────────────────────────
echo "[2] leela (train)"
launch "leela" \
    "$B/leela/m5out_train_sc_evict" \
    "$B/leela/leela_r.riscv" \
    "$B/leela/train.sgf"

# ── 3. namd ───────────────────────────────────────────────────────────────
echo "[3] namd (train — 7 iterations)"
launch "namd" \
    "$B/namd/m5out_train_sc_evict" \
    "$B/namd/namd_r.riscv" \
    "--input $B/namd/apoa1.input --iterations 7 --output $B/namd/apoa1.train_sc.output"

# ── 4. lbm ────────────────────────────────────────────────────────────────
echo "[4] lbm (train — 300 steps)"
launch "lbm" \
    "$B/lbm/m5out_train_sc_evict" \
    "$B/lbm/lbm_r.riscv" \
    "300 $B/lbm/reference.dat 0 1 $B/lbm/100_100_130_cf_b.of"

# ── 5. nab ────────────────────────────────────────────────────────────────
echo "[5] nab (train — aminos)"
launch "nab" \
    "$B/nab/m5out_train_sc_evict" \
    "$B/nab/nab_r.riscv" \
    "aminos 391519156 1000"

# ── 6. xz ─────────────────────────────────────────────────────────────────
echo "[6] xz (train — IMG_2560.cr2.xz 15MB level-4)"
launch "xz" \
    "$B/xz/m5out_train_sc_evict" \
    "$B/xz/xz_r.riscv" \
    "$B/xz/IMG_2560.cr2.xz 40 ec03e53b02deae89b6650f1de4bed76a012366fb3d4bdc791e8633d1a5964e03004523752ab008eff0d9e693689c53056533a05fc4b277f0086544c6c3cbbbf6 40822692 40824404 4"

# ── 7. imagick ────────────────────────────────────────────────────────────
echo "[7] imagick (train — train_input.tga, 8 filtre)"
launch "imagick" \
    "$B/imagick/m5out_train_sc_evict" \
    "$B/imagick/imagick_r.riscv" \
    "-limit disk 0 $B/imagick/train_input.tga -resize 320x240 -shear 31 -edge 140 -negate -flop -resize 900x900 -edge 10 $B/imagick/train_output_sc_evict.tga"

# ── 8. blender ────────────────────────────────────────────────────────────
echo "[8] blender (train — sh5_reduced.blend frame 234)"
launch "blender" \
    "$B/blender/m5out_train_sc_evict" \
    "$B/blender/blender_r.riscv" \
    "$B/blender/sh5_reduced.blend --render-output $B/blender/sh5_sc_evict_ --threads 1 -b -F RAWTGA -s 234 -e 234 -a"

# ── 9. povray ─────────────────────────────────────────────────────────────
echo "[9] povray (train)"
launch "povray" \
    "$B/povray/m5out_train_sc_evict" \
    "$B/povray/povray_r.riscv" \
    "$B/povray/SPEC-benchmark-train.ini"

# ── 10. omnetpp ───────────────────────────────────────────────────────────
echo "[10] omnetpp (train — sim-time-limit=0.15s)"
mkdir -p "$B/omnetpp/m5out_train_sc_evict"
cp "$B/omnetpp/omnetpp_train.ini" "$B/omnetpp/m5out_train_sc_evict/omnetpp.ini"
ln -sfn "$(pwd)/$B/omnetpp/ned" "$B/omnetpp/m5out_train_sc_evict/ned" 2>/dev/null || true
launch "omnetpp" \
    "$B/omnetpp/m5out_train_sc_evict" \
    "$B/omnetpp/omnetpp_r.riscv" \
    "-c General -r 0 $B/omnetpp/omnetpp_train.ini"

# ── 11. xalancbmk ─────────────────────────────────────────────────────────
echo "[11] xalancbmk (train — allbooks.xml)"
launch "xalancbmk" \
    "$B/xalancbmk/m5out_train_sc_evict" \
    "$B/xalancbmk/xalancbmk_r.riscv" \
    "-v $B/xalancbmk/allbooks.xml $B/xalancbmk/xalanc.xsl"

# ── 12. x264 ──────────────────────────────────────────────────────────────
echo "[12] x264 (ref — BuckBunny.264)"
launch "x264" \
    "$B/x264/m5out_train_sc_evict" \
    "$B/x264/ldecod_r.riscv" \
    "-i $B/x264/BuckBunny.264 -o $B/x264/BuckBunny_train_sc_evict.yuv"

# ── 13. gcc ───────────────────────────────────────────────────────────────
echo "[13] gcc (train — train01.c 1.2MB)"
launch "gcc" \
    "$B/gcc/m5out_train_sc_evict" \
    "$B/gcc/gcc_r.riscv" \
    "$B/gcc/train01.c -O3 -finline-limit=50000 -o $B/gcc/train01_sc_evict.s"

# ── 14. mcf ───────────────────────────────────────────────────────────────
echo "[14] mcf (train — inp_train.in 2.2MB)"
launch "mcf" \
    "$B/mcf/m5out_train_sc_evict" \
    "$B/mcf/mcf_r.riscv" \
    "$B/mcf/inp_train.in"

# ── 15. perlbench ─────────────────────────────────────────────────────────
echo "[15a] perlbench (train — scrabbl.pl)"
launch "perl_scrabbl" \
    "$B/perlbench/m5out_train_sc_evict_scrabbl" \
    "$B/perlbench/perlbench_r.riscv" \
    "-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/scrabbl.pl"

echo "[15b] perlbench (train — suns.pl)"
launch "perl_suns" \
    "$B/perlbench/m5out_train_sc_evict_suns" \
    "$B/perlbench/perlbench_r.riscv" \
    "-I./benchmarks/perlbench -I./benchmarks/perlbench/lib benchmarks/perlbench/suns.pl"

echo ""
echo "=== Toplam: $(ps aux | grep gem5 | grep -v grep | wc -l) gem5 process çalışıyor ==="
echo "=== $(date) ==="
echo ""
echo "Durum:   ps aux | grep gem5 | grep -v grep | wc -l"
echo "Sonuç:   bash benchmarks/analyze_spill_cache.sh --train-sc"
