#!/bin/bash
B=/cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks

# FORMAT: "bench  input_label  m5out_dir"
RUNS=(
    # --- MCF ---
    "mcf          test          m5out_test_summary"
    "mcf          train         m5out_train"
    "mcf          ref           m5out"
    # --- PERLBENCH ---
    "perlbench    test          m5out_test"
    "perlbench    train_perfect m5out_train_perfect"
    "perlbench    train_scrabbl m5out_train_scrabbl"
    "perlbench    train_suns    m5out_train_suns"
    "perlbench    ref_checkspam m5out_ref_checkspam"
    "perlbench    ref_diffmail  m5out_ref_diffmail"
    "perlbench    ref_splitmail m5out_ref_splitmail"
    # --- GCC ---
    "gcc          test          m5out_test"
    "gcc          train_200     m5out_train_200"
    "gcc          train_scilab  m5out_train_scilab"
    "gcc          train_train01 m5out_train_train01"
    "gcc          ref_pp_O3     m5out_ref_pp_O3"
    "gcc          ref_pp_O2     m5out_ref_pp_O2"
    "gcc          ref_smaller   m5out_ref_smaller"
    "gcc          ref32_O5      m5out_ref32_O5"
    "gcc          ref32_O3sel   m5out_ref32_O3sel"
    # --- NAMD ---
    "namd         test          m5out_test"
    "namd         train         m5out_train"
    "namd         ref           m5out_ref"
    # --- PAREST ---
    "parest       test          m5out_test"
    "parest       train         m5out_train"
    # --- POVRAY ---
    "povray       test          m5out_test"
    "povray       train         m5out_train"
    "povray       ref           m5out_ref"
    # --- LBM ---
    "lbm          test          m5out_test"
    "lbm          train         m5out_train"
    "lbm          ref           m5out_ref"
    # --- OMNETPP ---
    "omnetpp      test          m5out_test"
    "omnetpp      train         m5out_train"
    "omnetpp      ref           m5out_ref"
    # --- XALANCBMK ---
    "xalancbmk    test          m5out_test"
    "xalancbmk    train         m5out_train"
    "xalancbmk    ref           m5out_ref"
    # --- X264 ---
    "x264         test          m5out_test"
    "x264         train         m5out_train"
    "x264         ref           m5out_ref"
    # --- BLENDER ---
    "blender      test          m5out_test2"
    "blender      train         m5out_train"
    "blender      ref           m5out_ref"
    # --- DEEPSJENG ---
    "deepsjeng    test          m5out_test"
    "deepsjeng    train         m5out_train"
    "deepsjeng    ref           m5out_ref"
    # --- IMAGICK ---
    "imagick      test          m5out_test"
    "imagick      train         m5out_train"
    "imagick      ref           m5out_ref"
    # --- LEELA ---
    "leela        test          m5out_test"
    "leela        train         m5out_train"
    "leela        ref           m5out_ref"
    # --- NAB ---
    "nab          test          m5out_test"
    "nab          train_aminos  m5out_train_aminos"
    "nab          train_gcn4dna m5out_train_gcn4dna"
    "nab          ref           m5out_ref"
    # --- XZ ---
    "xz           test          m5out_test"
    "xz           train         m5out_train"
    "xz           ref           m5out_ref"
    # --- CACTUBSSN ---
    "cactuBSSN    test          m5out_test"
    "cactuBSSN    train         m5out_train"
)

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

echo ""
printf "${BOLD}%-14s %-16s %-10s %-10s %-8s %-8s${NC}\n" \
    "BENCHMARK" "INPUT" "STATUS" "RATE" "Sp/Ld" "Sp/St"
printf "%-14s %-16s %-10s %-10s %-8s %-8s\n" \
    "---------" "-----" "------" "----" "-----" "-----"

done_count=0; running_count=0; not_run=0
prev_bench=""

for entry in "${RUNS[@]}"; do
    read -r bench input outd <<< "$entry"
    log="$B/$bench/$outd/nohup.log"
    stats="$B/$bench/$outd/riscv_spill_stats.txt"

    # Separator line between benchmarks
    if [ "$bench" != "$prev_bench" ] && [ -n "$prev_bench" ]; then
        printf "%-14s\n" ""
    fi
    prev_bench="$bench"

    # Also check legacy log files (e.g. namd_test_run.log, gcc_test_run.log)
    legacy_log="$B/$bench/${bench}_test_run.log"
    [ ! -f "$log" ] && [ -f "$legacy_log" ] && log="$legacy_log"

    stats_size=$(wc -c < "$stats" 2>/dev/null || echo "0")
    is_running=$(ps aux | grep gem5 | grep -v grep | grep "$outd" | wc -l)

    stats_size="${stats_size//[[:space:]]/}"
    if [ "${stats_size:-0}" -gt 10 ] 2>/dev/null; then
        # Stats file has content → DONE
        spill_rate=$(grep "# spill_rate" "$stats" 2>/dev/null | awk '{print $NF}')
        roi_spills=$(grep "# roi_spills" "$stats" 2>/dev/null | awk '{print $NF}')
        roi_loads=$(grep "# roi_loads"  "$stats" 2>/dev/null | awk '{print $NF}')
        roi_stores=$(grep "# roi_stores" "$stats" 2>/dev/null | awk '{print $NF}')

        if [ -n "$spill_rate" ] && [ -n "$roi_loads" ] && [ "$roi_loads" -gt 0 ] 2>/dev/null; then
            sp_ld=$(awk "BEGIN {printf \"%.2f%%\", $roi_spills/$roi_loads*100}")
            sp_st=$(awk "BEGIN {printf \"%.2f%%\", $roi_spills/$roi_stores*100}")
            printf "${GREEN}%-14s %-16s %-10s %-10s %-8s %-8s${NC}\n" \
                "$bench" "$input" "DONE" "$spill_rate" "$sp_ld" "$sp_st"
        else
            printf "${YELLOW}%-14s %-16s %-10s${NC}\n" \
                "$bench" "$input" "DONE(no ROI)"
        fi
        ((done_count++))

    elif [ "$is_running" -gt 0 ]; then
        elapsed=$(ps aux | grep gem5 | grep -v grep | grep "$outd" | awk '{print $10}' | head -1)
        printf "${CYAN}%-14s %-16s %-10s${NC}\n" \
            "$bench" "$input" "RUNNING($elapsed)"
        ((running_count++))

    elif grep -q "REAL SIMULATION" "$log" 2>/dev/null; then
        # Ran but no spill output (crashed or no ROI hit)
        printf "${YELLOW}%-14s %-16s %-10s${NC}\n" \
            "$bench" "$input" "DONE(no ROI)"
        ((done_count++))

    else
        printf "${RED}%-14s %-16s %-10s${NC}\n" \
            "$bench" "$input" "—"
        ((not_run++))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "  gem5 processes running : %s\n" "$(ps aux | grep gem5 | grep -v grep | wc -l)"
printf "  ${GREEN}DONE${NC}    : %s\n" "$done_count"
printf "  ${CYAN}RUNNING${NC} : %s\n" "$running_count"
printf "  ${RED}NOT RUN${NC} : %s\n" "$not_run"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
