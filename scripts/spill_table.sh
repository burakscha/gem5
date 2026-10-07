#!/usr/bin/env bash
# Print one numbered row per SPEC benchmark: instruction counts, spill counts,
# the spill ratios against both the ROI and the whole run, and the cache
# hit/miss behaviour of the same window.
#
#   ./scripts/spill_table.sh                       # test / standard
#   ./scripts/spill_table.sh --profile train --cache small
#   ./scripts/spill_table.sh --csv table.csv       # also write a CSV
#   ./scripts/spill_table.sh --wide                # add the cache count columns
#
# Reads two files per completed run:
#   riscv_spill_stats.txt  ROI SUMMARY blocks + GLOBAL SUMMARY (metric schema 7)
#   stats.txt              gem5 statistics; workbegin/workend dump and reset
#                          them, so the ROI occupies its own block(s)

set -uo pipefail

# Force a dot decimal separator: a comma one would corrupt the CSV output.
export LC_ALL=C

ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PROFILE=test
CACHE=standard
CSV=""
WIDE=0

while (( $# > 0 )); do
    case "$1" in
        --profile) PROFILE="${2:?--profile needs a value}"; shift 2 ;;
        --cache)   CACHE="${2:?--cache needs a value}";     shift 2 ;;
        --csv)     CSV="${2:?--csv needs a path}";          shift 2 ;;
        --wide)    WIDE=1; shift ;;
        -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) printf 'unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done

# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------

# Sum a "# <name> : <value>" field across every ROI SUMMARY block, or read it
# from the GLOBAL SUMMARY block when $2 is "global".
spill_field() {
    local file="$1" name="$2" scope="${3:-roi}"
    awk -v want="$name" -v scope="$scope" '
        /^# GLOBAL SUMMARY/ { in_global = 1 }
        /^# ROI SUMMARY/    { in_global = 0 }
        {
            if (match($0, /^#[ \t]+[A-Za-z0-9_]+[ \t]*:[ \t]*[0-9]+/)) {
                key = $2
                val = $4
                if (key == want) {
                    if (scope == "global" && in_global) total = val
                    else if (scope == "roi" && !in_global) total += val
                }
            }
        }
        END { printf "%d", total + 0 }
    ' "$file"
}

# Sum a gem5 statistic over the ROI blocks of stats.txt. workbegin and workend
# each dump+reset, so with N regions the file holds 2N+1 blocks and the ROI
# ones sit at the odd indices. Anything else (an older binary, an aborted run)
# falls back to summing every block, which is the whole-run total.
stats_field() {
    local file="$1" name="$2" roi_count="$3"
    awk -v want="$name" -v rois="$roi_count" '
        /^-+ Begin Simulation Statistics/ { block++; next }
        $1 == want { value[block] += $2; seen[block] = 1 }
        END {
            expected = 2 * rois + 1
            if (rois > 0 && block == expected) {
                for (i = 2; i <= 2 * rois; i += 2) total += value[i]
            } else {
                for (i in value) total += value[i]
            }
            printf "%d", total + 0
        }
    ' "$file"
}

pct() {  # pct <numerator> <denominator>
    awk -v n="$1" -v d="$2" 'BEGIN { if (d > 0) printf "%.3f", 100*n/d; else printf "n/a" }'
}

# --------------------------------------------------------------------------
# Collect
# --------------------------------------------------------------------------
rows=()
skipped=()

for bench_dir in "$ROOT_DIR"/benchmarks/*/; do
    bench="$(basename "$bench_dir")"
    run_root="$bench_dir/m5out_$bench"
    [[ -d "$run_root" ]] || continue
    for link in "$run_root"/latest_"${PROFILE}"_"${CACHE}"_*; do
        [[ -e "$link" ]] || continue
        run_id="${link##*/latest_${PROFILE}_${CACHE}_}"
        dir="$(readlink -f "$link")"
        status="$(cat "$dir/.runner/status" 2>/dev/null || echo UNKNOWN)"
        if [[ "$status" != COMPLETED ]]; then
            skipped+=("$run_id: $status")
            continue
        fi
        log="$dir/riscv_spill_stats.txt"
        stats="$dir/stats.txt"
        if [[ ! -f "$log" || ! -f "$stats" ]]; then
            skipped+=("$run_id: output files missing")
            continue
        fi

        roi_count="$(grep -c '^# ROI SUMMARY' "$log")"

        total_insts="$(spill_field "$log" total_insts global)"
        total_load="$(spill_field "$log" total_load global)"
        total_store="$(spill_field "$log" total_store global)"

        roi_insts="$(spill_field "$log" roi_total_insts)"
        roi_load="$(spill_field "$log" roi_load)"
        roi_store="$(spill_field "$log" roi_store)"

        spill_event="$(spill_field "$log" spill_event)"
        spill_load="$(spill_field "$log" spill_load)"
        spill_store="$(spill_field "$log" spill_store)"
        spill_total=$(( spill_load + spill_store ))

        l1d_hit="$(stats_field "$stats" system.cpu.dcache.demandHits::total "$roi_count")"
        l1d_miss="$(stats_field "$stats" system.cpu.dcache.demandMisses::total "$roi_count")"
        l1i_hit="$(stats_field "$stats" system.cpu.icache.demandHits::total "$roi_count")"
        l1i_miss="$(stats_field "$stats" system.cpu.icache.demandMisses::total "$roi_count")"
        l2_hit="$(stats_field "$stats" system.l2.demandHits::total "$roi_count")"
        l2_miss="$(stats_field "$stats" system.l2.demandMisses::total "$roi_count")"
        # Whatever misses the L2 is served by main memory.
        dram=$l2_miss
        l1_acc=$(( l1d_hit + l1d_miss + l1i_hit + l1i_miss ))

        rows+=("$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
            "$run_id" "$total_insts" "$roi_insts" "$spill_event" "$spill_load" "$spill_store" "$spill_total" \
            "$(pct "$spill_event" "$roi_insts")" "$(pct "$spill_event" "$total_insts")" \
            "$(pct "$spill_total" "$roi_insts")" "$(pct "$spill_total" "$total_insts")" \
            "$total_load" "$roi_load" "$(pct "$roi_load" "$total_load")" "$(pct "$spill_load" "$roi_load")" \
            "$total_store" "$roi_store" "$(pct "$roi_store" "$total_store")" "$(pct "$spill_store" "$roi_store")" \
            "$l1d_hit" "$l1d_miss" "$(pct "$l1d_miss" $((l1d_hit + l1d_miss)))" \
            "$l1i_miss" "$(pct "$l1i_miss" $((l1i_hit + l1i_miss)))" \
            "$l2_hit" "$l2_miss" "$(pct "$dram" "$l1_acc")")")
    done
done

if (( ${#skipped[@]} > 0 )); then
    printf 'Not included (%d):\n' "${#skipped[@]}"
    printf '  - %s\n' "${skipped[@]}"
    printf '\n'
fi

if (( ${#rows[@]} == 0 )); then
    printf 'No completed runs for profile=%s cache=%s.\n' "$PROFILE" "$CACHE" >&2
    printf 'Launch them with: ./scripts/launch_spill_batch.sh %s %s\n' "$PROFILE" "$CACHE" >&2
    exit 1
fi

# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
printf 'Profile=%s  cache=%s  benchmarks=%d\n\n' "$PROFILE" "$CACHE" "${#rows[@]}"

{
    if (( WIDE )); then
        printf 'ID\tBENCHMARK\tTOTAL_INSTS\tROI_INSTS\tSPILL\tSP_LOAD\tSP_STORE\tSP_TOTAL\tSPILL%%ROI\tSPILL%%ALL\tSPMEM%%ROI\tSPMEM%%ALL\tTOTAL_LD\tROI_LD\tROI_LD%%\tSPLD%%ROI_LD\tTOTAL_ST\tROI_ST\tROI_ST%%\tSPST%%ROI_ST\tL1D_HIT\tL1D_MISS\tL1D_MISS%%\tL1I_MISS\tL1I_MISS%%\tL2_HIT\tL2_MISS\tDRAM%%\n'
        printf '%s\n' "${rows[@]}" | nl -v0 -w1 -s$'\t'
    else
        printf 'ID\tBENCHMARK\tTOTAL_INSTS\tROI_INSTS\tSPILL\tSP_LOAD\tSP_STORE\tSPILL%%ROI\tSPILL%%ALL\tSPMEM%%ROI\tROI_LD%%\tSPLD%%ROI_LD\tROI_ST%%\tSPST%%ROI_ST\tL1D_MISS%%\tL1I_MISS%%\tL2_MISS%%\tDRAM%%\n'
        printf '%s\n' "${rows[@]}" | nl -v0 -w1 -s$'\t' | \
            awk -F'\t' 'BEGIN{OFS="\t"} {
                l2m = ($26 + $27 > 0) ? sprintf("%.3f", 100*$27/($26+$27)) : "n/a"
                print $1,$2,$3,$4,$5,$6,$7,$9,$10,$11,$15,$16,$19,$20,$23,$25,l2m,$28
            }'
    fi
} | column -t -s$'\t'

if [[ -n "$CSV" ]]; then
    {
        printf 'id,benchmark,total_insts,roi_insts,spill_event,spill_load,spill_store,total_spill_insts,'
        printf 'spill_pct_roi,spill_pct_all,spillmem_pct_roi,spillmem_pct_all,'
        printf 'total_load,roi_load,roi_load_pct_of_total,spill_load_pct_of_roi_load,'
        printf 'total_store,roi_store,roi_store_pct_of_total,spill_store_pct_of_roi_store,'
        printf 'l1d_hits,l1d_misses,l1d_miss_pct,l1i_misses,l1i_miss_pct,l2_hits,l2_misses,dram_pct_of_l1_accesses\n'
        printf '%s\n' "${rows[@]}" | nl -v0 -w1 -s$'\t' | tr '\t' ','
    } > "$CSV"
    printf '\nCSV: %s\n' "$CSV"
fi
