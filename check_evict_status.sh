#!/bin/bash
# check_evict_status.sh
#
# launch_test_smallcache_evict.sh + launch_train_smallcache_evict.sh
# ile başlatılan tüm (eviction-attribution enstrümanlı) koşumların
# durumunu tek bakışta gösterir.
#
# Kullanım:
#   cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/
#   bash check_evict_status.sh          # tablo
#   bash check_evict_status.sh -v       # tablo + biten koşumların 8-kutu özeti

cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks || exit 1

VERBOSE=0
[[ "${1:-}" == "-v" ]] && VERBOSE=1

RUNNING=$(pgrep -fc "build/RISCV/gem5.opt" 2>/dev/null || echo 0)
echo "=== $(date) ==="
echo "=== Şu an çalışan gem5 process sayısı: $RUNNING ==="
echo ""

printf "%-14s %-22s %-10s %s\n" "BENCH" "OUTDIR" "DURUM" "DETAY"
printf '%s\n' "--------------------------------------------------------------------------------"

done_count=0
running_count=0
other_count=0

for d in */m5out_*_sc_evict*; do
    [ -d "$d" ] || continue
    bench=$(echo "$d" | cut -d/ -f1)
    outdir_name=$(basename "$d")
    log="$d/nohup.log"
    stats="$d/stats.txt"

    if pgrep -f -- "outdir=benchmarks/$d " >/dev/null 2>&1; then
        status="RUNNING"
        pid=$(pgrep -f -- "outdir=benchmarks/$d " | head -1)
        detail="PID=$pid  $(tail -n1 "$log" 2>/dev/null | cut -c1-50)"
        running_count=$((running_count+1))
    elif [ -f "$log" ] && grep -q "Exiting @ tick" "$log" 2>/dev/null; then
        status="DONE"
        detail=$(grep "Exiting @ tick" "$log" | tail -1 | cut -c1-60)
        done_count=$((done_count+1))
    elif [ -f "$log" ]; then
        status="? (durdu)"
        detail=$(tail -n1 "$log" 2>/dev/null | cut -c1-60)
        other_count=$((other_count+1))
    else
        status="? (başlamadı)"
        detail=""
        other_count=$((other_count+1))
    fi
    printf "%-14s %-22s %-10s %s\n" "$bench" "$outdir_name" "$status" "$detail"

    if [[ $VERBOSE -eq 1 && "$status" == "DONE" && -f "$stats" ]]; then
        awk '
          /spillLoadEvictedBySpill |spillLoadEvictedByNonSpill |spillStoreEvictedBySpill |spillStoreEvictedByNonSpill |nonSpillLoadEvictedBySpill |nonSpillLoadEvictedByNonSpill |nonSpillStoreEvictedBySpill |nonSpillStoreEvictedByNonSpill / {
            printf "      %-32s %s\n", $1, $2
          }
        ' "$stats"
    fi
done

echo ""
echo "=== Özet: $done_count DONE, $running_count RUNNING, $other_count diğer ==="
echo ""
echo "Detaylı 8-kutu sayıları için: bash check_evict_status.sh -v"
echo "Tek bir benchmark'ı analiz etmek için:"
echo "  grep -E 'EvictedBy' benchmarks/<bench>/m5out_<test|train>_sc_evict*/stats.txt"
