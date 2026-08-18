#!/bin/bash
# analyze_eviction_cases.sh
#
# "Kim kimi evict etti" defterinin 4 temel case'ini (load/store ayrımı
# olmadan, toplanmış) her biten benchmark için sayı + yüzde olarak basar.
#
#   Case 1: kovan=spill     -> kovulan=spill      (spill kendi kendini yiyor)
#   Case 2: kovan=spill     -> kovulan=non-spill  (spill, normal veriyi kovuyor)
#   Case 3: kovan=non-spill -> kovulan=spill      (normal trafik, spill'i kovuyor)
#   Case 4: kovan=non-spill -> kovulan=non-spill  (kontrol grubu, spilling'le ilgisiz)
#
# Yüzde = case_i / (case1+case2+case3+case4) * 100
#   (yani "izlenebilen tüm eviction-kaynaklı miss'lerin kaçta kaçı bu case")
#
# Kullanım:
#   cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks
#   bash analyze_eviction_cases.sh

cd "$(dirname "$0")" || exit 1

printf "%-11s %-30s %14s %14s %14s %14s\n" \
  "BENCH" "TIER" "C1:spl->spl" "C2:spl->non" "C3:non->spl" "C4:non->non"
printf "%-11s %-30s %14s %14s %14s %14s\n" \
  "" "" "(kendi-yeme)" "(collateral)" "(spill kayıp)" "(kontrol)"
printf '%s\n' "------------------------------------------------------------------------------------------------------------------"

for d in */m5out_*_sc_evict*; do
    [ -d "$d" ] || continue
    bench=$(echo "$d" | cut -d/ -f1)
    outdir=$(basename "$d")
    log="$d/nohup.log"
    stats="$d/stats.txt"

    # Sadece tamamlanmış koşumları göster
    [ -f "$log" ] && grep -q "Exiting @ tick" "$log" 2>/dev/null || continue
    [ -f "$stats" ] || continue

    read -r sL_s sL_ns sS_s sS_ns nL_s nL_ns nS_s nS_ns <<EOF
$(grep "^system.cpu.dcache\." "$stats" | awk '
  /spillLoadEvictedBySpill /       {a=$2}
  /spillLoadEvictedByNonSpill /    {b=$2}
  /spillStoreEvictedBySpill /      {c=$2}
  /spillStoreEvictedByNonSpill /   {d=$2}
  /nonSpillLoadEvictedBySpill /    {e=$2}
  /nonSpillLoadEvictedByNonSpill / {f=$2}
  /nonSpillStoreEvictedBySpill /   {g=$2}
  /nonSpillStoreEvictedByNonSpill /{h=$2}
  END{print a,b,c,d,e,f,g,h}
')
EOF

    awk -v bench="$bench" -v outdir="$outdir" \
        -v sL_s="$sL_s" -v sL_ns="$sL_ns" -v sS_s="$sS_s" -v sS_ns="$sS_ns" \
        -v nL_s="$nL_s" -v nL_ns="$nL_ns" -v nS_s="$nS_s" -v nS_ns="$nS_ns" '
    BEGIN {
        c1 = sL_s + sS_s          # spill -> spill
        c2 = nL_s + nS_s          # spill -> non-spill
        c3 = sL_ns + sS_ns        # non-spill -> spill
        c4 = nL_ns + nS_ns        # non-spill -> non-spill
        total = c1 + c2 + c3 + c4
        if (total == 0) total = 1   # sıfıra bölmeyi engelle

        p1 = 100*c1/total; p2 = 100*c2/total; p3 = 100*c3/total; p4 = 100*c4/total

        printf "%-11s %-30s %8d (%4.1f%%) %8d (%4.1f%%) %8d (%4.1f%%) %10d (%4.1f%%)\n", \
            bench, outdir, c1, p1, c2, p2, c3, p3, c4, p4
    }'
done
