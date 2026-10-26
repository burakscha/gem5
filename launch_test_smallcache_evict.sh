#!/bin/bash
# launch_test_smallcache_evict.sh
#
# Tüm SPEC CPU2017 benchmark'larını TEST inputlarıyla, küçültülmüş cache
# konfigürasyonuyla çalıştırır.
#
# Cache boyutları:
#   L1D : 4KiB   (normal: 64KiB)
#   L1I : 32KiB  (değiştirilmedi)
#   L2  : 32KiB  (normal: 2MiB)
#
# Kullanım:
#   cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/
#   bash launch_test_smallcache_evict.sh
#
# Çıktı dizinleri: benchmarks/<bench>/m5out_test_sc_evict/
# Log: benchmarks/<bench>/m5out_test_sc_evict/nohup.log

set -euo pipefail

cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/ || exit 1

GEM5=./build/RISCV/gem5.opt
CFG=configs/deprecated/example/se.py
OPTS="--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB --l1d_size=4kB --l1i_size=32kB --l2_size=32kB"
B=benchmarks

echo "=== launch_test_smallcache_evict.sh ==="
echo "=== Cache: L1D=4kB  L1I=32kB  L2=32kB ==="
echo "=== $(date) ==="
echo ""

# ─── yardımcı fonksiyon ─────────────────────────────────────────────────
launch() {
    local label="$1"
    local outdir="$2"
    local cmd="$3"
    local options="$4"
    mkdir -p "$outdir"
    rm -f "$outdir/stats.txt" "$outdir/riscv_spill_stats.txt"
    nohup $GEM5 --outdir="$outdir" $CFG \
        --cmd="$cmd" --options="$options" \
        $OPTS \
        > "$outdir/nohup.log" 2>&1 &
    printf "  [%-20s] PID=%-6s  outdir=%s\n" "$label" "$!" "$outdir"
}

# ─── 1. deepsjeng ───────────────────────────────────────────────────────
echo "[1] deepsjeng (test)"
launch "deepsjeng" \
    "$B/deepsjeng/m5out_test_sc_evict" \
    "$B/deepsjeng/deepsjeng_r.riscv" \
    "$B/deepsjeng/test.txt"

# ─── 2. leela ───────────────────────────────────────────────────────────
echo "[2] leela (test)"
launch "leela" \
    "$B/leela/m5out_test_sc_evict" \
    "$B/leela/leela_r.riscv" \
    "$B/leela/test.sgf"

# ─── 3. namd ────────────────────────────────────────────────────────────
echo "[3] namd (test — 1 iteration)"
launch "namd" \
    "$B/namd/m5out_test_sc_evict" \
    "$B/namd/namd_r.riscv" \
    "--input $B/namd/apoa1.input --iterations 1 --output $B/namd/apoa1.test_sc.output"

# ─── 4. lbm ─────────────────────────────────────────────────────────────
echo "[4] lbm (test — 20 steps)"
launch "lbm" \
    "$B/lbm/m5out_test_sc_evict" \
    "$B/lbm/lbm_r.riscv" \
    "20 $B/lbm/reference.dat 0 1 $B/lbm/100_100_130_cf_a.of"

# ─── 5. nab ─────────────────────────────────────────────────────────────
echo "[5] nab (test — hkrdenq)"
launch "nab" \
    "$B/nab/m5out_test_sc_evict" \
    "$B/nab/nab_r.riscv" \
    "hkrdenq 1930344093 1000"

# ─── 6. xz ──────────────────────────────────────────────────────────────
echo "[6] xz (test — 1.3MB level-0)"
launch "xz" \
    "$B/xz/m5out_test_sc_evict" \
    "$B/xz/xz_r.riscv" \
    "$B/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1548636 1555348 0"

# ─── 7. imagick ─────────────────────────────────────────────────────────
echo "[7] imagick (test — tiny tga)"
launch "imagick" \
    "$B/imagick/m5out_test_sc_evict" \
    "$B/imagick/imagick_r.riscv" \
    "-limit disk 0 $B/imagick/test_input.tga -shear 25 -resize 640x480 -negate -alpha Off $B/imagick/test_output_sc.tga"

# ─── 8. blender ─────────────────────────────────────────────────────────
echo "[8] blender (test — cube.blend frame 1)"
launch "blender" \
    "$B/blender/m5out_test_sc_evict" \
    "$B/blender/blender_r.riscv" \
    "$B/blender/cube.blend --render-output $B/blender/cube_sc_evict_ --threads 1 -b -F RAWTGA -s 1 -e 1 -a"

# ─── 9. povray ──────────────────────────────────────────────────────────
echo "[9] povray (test — 50x50)"
launch "povray" \
    "$B/povray/m5out_test_sc_evict" \
    "$B/povray/povray_r.riscv" \
    "$B/povray/SPEC-benchmark-test.ini"

# ─── 10. omnetpp ────────────────────────────────────────────────────────
echo "[10] omnetpp (test — sim-time-limit=0.003s)"
mkdir -p "$B/omnetpp/m5out_test_sc_evict"
cp "$B/omnetpp/omnetpp_test.ini" "$B/omnetpp/m5out_test_sc_evict/omnetpp.ini"
ln -sfn "$(pwd)/$B/omnetpp/ned" "$B/omnetpp/m5out_test_sc_evict/ned" 2>/dev/null || true
launch "omnetpp" \
    "$B/omnetpp/m5out_test_sc_evict" \
    "$B/omnetpp/omnetpp_r.riscv" \
    "-c General -r 0 $B/omnetpp/omnetpp_test.ini"

# ─── 11. xalancbmk ──────────────────────────────────────────────────────
echo "[11] xalancbmk (test — test.xml)"
launch "xalancbmk" \
    "$B/xalancbmk/m5out_test_sc_evict" \
    "$B/xalancbmk/xalancbmk_r.riscv" \
    "-v $B/xalancbmk/test.xml $B/xalancbmk/xalanc.xsl"

# ─── 12. x264 ───────────────────────────────────────────────────────────
echo "[12] x264 (train — BuckBunny_train.264, 1.3MB)"
launch "x264" \
    "$B/x264/m5out_test_sc_evict" \
    "$B/x264/ldecod_r.riscv" \
    "-i $B/x264/BuckBunny_train.264 -o $B/x264/BuckBunny_test_sc_evict.yuv"

# ─── 13. gcc ────────────────────────────────────────────────────────────
echo "[13] gcc (test — t1.c, 69B)"
launch "gcc" \
    "$B/gcc/m5out_test_sc_evict" \
    "$B/gcc/gcc_r.riscv" \
    "$B/gcc/t1.c -O3 -finline-limit=50000 -o $B/gcc/t1_test_sc_evict.s"

# ─── 14. mcf ────────────────────────────────────────────────────────────
echo "[14] mcf (inp.in)"
launch "mcf" \
    "$B/mcf/m5out_test_sc_evict" \
    "$B/mcf/mcf_r.riscv" \
    "$B/mcf/inp.in"

# ─── 15. perlbench ──────────────────────────────────────────────────────
echo "[15] perlbench (test — test.pl)"
launch "perlbench_test" \
    "$B/perlbench/m5out_test_sc_evict" \
    "$B/perlbench/perlbench_r.riscv" \
    "-I./benchmarks/perlbench -I./benchmarks/perlbench/lib $B/perlbench/test.pl"

echo ""
echo "=== Toplam: $(ps aux | grep gem5 | grep -v grep | wc -l) gem5 process çalışıyor ==="
echo "=== $(date) ==="
echo ""
echo "Durum kontrolü:"
echo "  ps aux | grep gem5 | grep -v grep | wc -l"
echo ""
echo "Sonuçları görmek için (bitince):"
echo "  bash benchmarks/analyze_spill_cache.sh --test"
