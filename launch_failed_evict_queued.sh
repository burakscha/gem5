#!/bin/bash
# launch_failed_evict_queued.sh
#
# 5 Ağustos'ta 31 process'i birden ateşleyince muhtemelen OOM'dan 17 tanesi
# yarıda kaldı (bkz. check_evict_status.sh çıktısı). Bu script sadece o 17
# koşumu, aynı anda en fazla MAX_PARALLEL tanesi çalışacak şekilde bir
# kuyrukla yeniden başlatır -- böylece bellek tekrar taşmaz.
#
# Kullanım:
#   cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/
#   nohup bash launch_failed_evict_queued.sh > launch_failed_evict_queued.log 2>&1 &
#
# Takip: bash check_evict_status.sh

set -uo pipefail   # -e YOK: bir job başarısız olsa da kuyruk devam etsin

cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/ || exit 1

GEM5=./build/RISCV/gem5.opt
CFG=configs/deprecated/example/se.py
OPTS="--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB --l1d_size=4kB --l1i_size=32kB --l2_size=32kB"
B=benchmarks
MAX_PARALLEL=8

echo "=== launch_failed_evict_queued.sh ==="
echo "=== MAX_PARALLEL=$MAX_PARALLEL ==="
echo "=== $(date) ==="
echo ""

# Aynı anda en fazla MAX_PARALLEL job -- dolarsa biri bitene kadar bekler.
wait_for_slot() {
    while [ "$(jobs -rp | wc -l)" -ge "$MAX_PARALLEL" ]; do
        wait -n
    done
}

launch() {
    local label="$1" outdir="$2" cmd="$3" options="$4"
    wait_for_slot
    mkdir -p "$outdir"
    rm -f "$outdir/stats.txt" "$outdir/riscv_spill_stats.txt" "$outdir/nohup.log"
    nohup $GEM5 --outdir="$outdir" $CFG \
        --cmd="$cmd" --options="$options" \
        $OPTS \
        > "$outdir/nohup.log" 2>&1 &
    printf "  [%-14s] PID=%-6s  outdir=%s  ($(date +%H:%M:%S))\n" "$label" "$!" "$outdir"
}

# ── TEST tier (yarıda kalanlar) ─────────────────────────────────────────
echo "[1/17] deepsjeng (test)"
launch "deepsjeng_test" "$B/deepsjeng/m5out_test_sc_evict" \
    "$B/deepsjeng/deepsjeng_r.riscv" "$B/deepsjeng/test.txt"

echo "[2/17] leela (test)"
launch "leela_test" "$B/leela/m5out_test_sc_evict" \
    "$B/leela/leela_r.riscv" "$B/leela/test.sgf"

echo "[3/17] mcf (test)"
launch "mcf_test" "$B/mcf/m5out_test_sc_evict" \
    "$B/mcf/mcf_r.riscv" "$B/mcf/inp.in"

echo "[4/17] namd (test — 1 iteration)"
launch "namd_test" "$B/namd/m5out_test_sc_evict" \
    "$B/namd/namd_r.riscv" \
    "--input $B/namd/apoa1.input --iterations 1 --output $B/namd/apoa1.test_sc.output"

echo "[5/17] x264 (test — BuckBunny_train.264)"
launch "x264_test" "$B/x264/m5out_test_sc_evict" \
    "$B/x264/ldecod_r.riscv" \
    "-i $B/x264/BuckBunny_train.264 -o $B/x264/BuckBunny_test_sc_evict.yuv"

# ── TRAIN tier (yarıda kalanlar) ────────────────────────────────────────
echo "[6/17] blender (train — sh5_reduced.blend frame 234)"
launch "blender_train" "$B/blender/m5out_train_sc_evict" \
    "$B/blender/blender_r.riscv" \
    "$B/blender/sh5_reduced.blend --render-output $B/blender/sh5_sc_evict_ --threads 1 -b -F RAWTGA -s 234 -e 234 -a"

echo "[7/17] deepsjeng (train)"
launch "deepsjeng_train" "$B/deepsjeng/m5out_train_sc_evict" \
    "$B/deepsjeng/deepsjeng_r.riscv" "$B/deepsjeng/train.txt"

echo "[8/17] gcc (train — train01.c 1.2MB)"
launch "gcc_train" "$B/gcc/m5out_train_sc_evict" \
    "$B/gcc/gcc_r.riscv" \
    "$B/gcc/train01.c -O3 -finline-limit=50000 -o $B/gcc/train01_sc_evict.s"

echo "[9/17] imagick (train — train_input.tga, 8 filtre)"
launch "imagick_train" "$B/imagick/m5out_train_sc_evict" \
    "$B/imagick/imagick_r.riscv" \
    "-limit disk 0 $B/imagick/train_input.tga -resize 320x240 -shear 31 -edge 140 -negate -flop -resize 900x900 -edge 10 $B/imagick/train_output_sc_evict.tga"

echo "[10/17] leela (train)"
launch "leela_train" "$B/leela/m5out_train_sc_evict" \
    "$B/leela/leela_r.riscv" "$B/leela/train.sgf"

echo "[11/17] mcf (train — inp_train.in 2.2MB)"
launch "mcf_train" "$B/mcf/m5out_train_sc_evict" \
    "$B/mcf/mcf_r.riscv" "$B/mcf/inp_train.in"

echo "[12/17] namd (train — 7 iterations)"
launch "namd_train" "$B/namd/m5out_train_sc_evict" \
    "$B/namd/namd_r.riscv" \
    "--input $B/namd/apoa1.input --iterations 7 --output $B/namd/apoa1.train_sc.output"

echo "[13/17] omnetpp (train — sim-time-limit=0.15s)"
mkdir -p "$B/omnetpp/m5out_train_sc_evict"
cp "$B/omnetpp/omnetpp_train.ini" "$B/omnetpp/m5out_train_sc_evict/omnetpp.ini"
ln -sfn "$(pwd)/$B/omnetpp/ned" "$B/omnetpp/m5out_train_sc_evict/ned" 2>/dev/null || true
launch "omnetpp_train" "$B/omnetpp/m5out_train_sc_evict" \
    "$B/omnetpp/omnetpp_r.riscv" "-c General -r 0 $B/omnetpp/omnetpp_train.ini"

echo "[14/17] povray (train)"
launch "povray_train" "$B/povray/m5out_train_sc_evict" \
    "$B/povray/povray_r.riscv" "$B/povray/SPEC-benchmark-train.ini"

echo "[15/17] x264 (train — ref BuckBunny.264)"
launch "x264_train" "$B/x264/m5out_train_sc_evict" \
    "$B/x264/ldecod_r.riscv" \
    "-i $B/x264/BuckBunny.264 -o $B/x264/BuckBunny_train_sc_evict.yuv"

echo "[16/17] xalancbmk (train — allbooks.xml)"
launch "xalancbmk_train" "$B/xalancbmk/m5out_train_sc_evict" \
    "$B/xalancbmk/xalancbmk_r.riscv" \
    "-v $B/xalancbmk/allbooks.xml $B/xalancbmk/xalanc.xsl"

echo "[17/17] xz (train — IMG_2560.cr2.xz 15MB level-4)"
launch "xz_train" "$B/xz/m5out_train_sc_evict" \
    "$B/xz/xz_r.riscv" \
    "$B/xz/IMG_2560.cr2.xz 40 ec03e53b02deae89b6650f1de4bed76a012366fb3d4bdc791e8633d1a5964e03004523752ab008eff0d9e693689c53056533a05fc4b277f0086544c6c3cbbbf6 40822692 40824404 4"

echo ""
echo "=== Tüm 17 job kuyruğa alındı, en fazla $MAX_PARALLEL aynı anda çalışıyor ==="
echo "=== Kalan job'ların hepsi bitene kadar bu script açık kalır (nohup ile arka planda) ==="
wait
echo ""
echo "=== TÜMÜ BİTTİ: $(date) ==="
