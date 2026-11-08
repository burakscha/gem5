#!/usr/bin/env bash
# Run and monitor SPEC CPU2017 workloads with the schema-10 spill detector.

set -uo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
# The repository root is one level above scripts/.
ROOT_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
# Schema 10 has its own build directory; build/RISCV keeps the schema-9 binary.
GEM5_BIN="${GEM5_BIN:-$ROOT_DIR/build/RISCV_SCHEMA10/gem5.opt}"
GEM5_CONFIG="${GEM5_CONFIG:-$ROOT_DIR/configs/deprecated/example/se.py}"
ANALYZER="$ROOT_DIR/scripts/spill_report.py"

usage() {
    cat <<'EOF'
Usage:
  ./scripts/spec_spill_runner.sh list [test|train|ref]
  ./scripts/spec_spill_runner.sh check  PROFILE CACHE [TARGET ...]
  ./scripts/spec_spill_runner.sh start  PROFILE CACHE TARGET [TARGET ...]
  ./scripts/spec_spill_runner.sh status PROFILE CACHE [TARGET ...]
  ./scripts/spec_spill_runner.sh stop   PROFILE CACHE TARGET [TARGET ...]
  ./scripts/spec_spill_runner.sh log    PROFILE CACHE RUN_ID [LINES]
  ./scripts/spec_spill_runner.sh results PROFILE CACHE [TARGET ...]

PROFILE: test, train, ref
CACHE:   SIZE or SIZE-ORG
           SIZE  standard (L1D 64KiB, L1I 32KiB, L2 2MiB)
                 small    (L1D 4kB,   L1I 32kB,  L2 32kB)
           ORG   <N>way L1D N-way, L2 8-way; N a power of two that leaves at
                        least one set (e.g. small-2way = no ORG, own run dirs)
                 dm   direct-mapped L1D + L2
                 nway L1D 8-way, L2 16-way
                 fa   fully associative L1D + L2 (FALRU)
           no ORG: L1D 2-way, L2 8-way (se.py defaults, schema-7 runs)
           L1I is 2-way in every profile.
TARGET:  run ID, benchmark name, or "all"

Examples:
  ./scripts/spec_spill_runner.sh list test
  ./scripts/spec_spill_runner.sh check test standard all
  ./scripts/spec_spill_runner.sh start test standard gcc perlbench
  ./scripts/spec_spill_runner.sh status test standard all
  ./scripts/spec_spill_runner.sh log test standard gcc 40
  ./scripts/spec_spill_runner.sh results test standard gcc
  ./scripts/spec_spill_runner.sh stop test standard gcc

Results are never overwritten. Every start creates a timestamped directory
benchmarks/<benchmark>/<input>/m5out/<cache>/<run_id>_<HHMM_DDMMYYYY> and
updates the "latest_*" links (index: benchmarks/<benchmark>/m5out_<benchmark>/).
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

valid_profile() {
    case "$1" in test|train|ref) return 0 ;; *) return 1 ;; esac
}

valid_cache() {
    [[ "$1" =~ ^(standard|small)(-(dm|fa|nway|([0-9]+)way))?$ ]] || return 1
    local n="${BASH_REMATCH[4]}"
    # N-way: a power of two; gem5 itself rejects one that leaves no full set.
    [[ -z "$n" ]] || (( n > 0 && (n & (n - 1)) == 0 ))
}

# Fields: run_id | benchmark | input_set | input_description | binary |
#         program_options | required_paths | optional_omnet_ini |
#         optional_run_dir
# program_options may end in "< FILE": FILE is the program's standard input,
# as in SPEC's command lines (passed to se.py as --input). Without a run_dir
# the program runs in the gem5 root and its paths are relative to it. With
# one, it runs in a private copy of that directory (SPEC's run directory)
# and program_options are SPEC's own command line, relative to that copy.
# Fields are separated by the ASCII unit separator, not a tab: read treats
# tabs as whitespace and would merge an empty field into the next one.
record() {
    printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s\n' "$@"
}

manifest() {
    local profile="$1"
    case "$profile" in
      test)
        record cactuBSSN cactuBSSN test spec_test.par \
          benchmarks/cactuBSSN/cactuBSSN_r.riscv \
          'benchmarks/cactuBSSN/spec_test.par' \
          'benchmarks/cactuBSSN/spec_test.par' ''
        record parest parest test test.prm \
          benchmarks/parest/parest_r.riscv \
          'benchmarks/parest/test.prm' \
          'benchmarks/parest/test.prm' ''
        record deepsjeng deepsjeng test test.txt \
          benchmarks/deepsjeng/deepsjeng_r.riscv \
          'benchmarks/deepsjeng/test.txt' \
          'benchmarks/deepsjeng/test.txt' ''
        record leela leela test test.sgf \
          benchmarks/leela/leela_r.riscv \
          'benchmarks/leela/test.sgf' \
          'benchmarks/leela/test.sgf' ''
        record namd namd test 'apoa1.input, 1 iteration' \
          benchmarks/namd/namd_r.riscv \
          '--input benchmarks/namd/apoa1.input --iterations 1 --output {OUTDIR}/apoa1.output' \
          'benchmarks/namd/apoa1.input' ''
        record lbm lbm test '20 steps, 100_100_130_cf_a.of' \
          benchmarks/lbm/lbm_r.riscv \
          '20 {OUTDIR}/reference.dat 0 1 benchmarks/lbm/100_100_130_cf_a.of' \
          'benchmarks/lbm/100_100_130_cf_a.of' ''
        record nab nab test 'hkrdenq, 1000 iterations' \
          benchmarks/nab/nab_r.riscv \
          'hkrdenq 1930344093 1000' \
          'hkrdenq/hkrdenq.pdb;hkrdenq/hkrdenq.prm' ''
        record xz xz test 'cpu2006docs.tar.xz, 4 MB, level 0' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1548636 1555348 0' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_4m_l1 xz test 'cpu2006docs.tar.xz, 4 MB, level 1' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1462248 -1 1' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_4m_l2 xz test 'cpu2006docs.tar.xz, 4 MB, level 2' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1428548 -1 2' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_4m_l3e xz test 'cpu2006docs.tar.xz, 4 MB, level 3e' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1034828 -1 3e' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_4m_l4 xz test 'cpu2006docs.tar.xz, 4 MB, level 4' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1061968 -1 4' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_4m_l4e xz test 'cpu2006docs.tar.xz, 4 MB, level 4e' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 4 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 1034588 -1 4e' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_1m_l0 xz test 'cpu2006docs.tar.xz, 1 MB, level 0' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 1 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 650156 -1 0' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_1m_l1 xz test 'cpu2006docs.tar.xz, 1 MB, level 1' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 1 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 639996 -1 1' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_1m_l2 xz test 'cpu2006docs.tar.xz, 1 MB, level 2' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 1 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 637616 -1 2' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_1m_l3e xz test 'cpu2006docs.tar.xz, 1 MB, level 3e' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 1 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 628996 -1 3e' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_1m_l4 xz test 'cpu2006docs.tar.xz, 1 MB, level 4' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 1 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 631912 -1 4' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record xz_1m_l4e xz test 'cpu2006docs.tar.xz, 1 MB, level 4e' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/cpu2006docs.tar.xz 1 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 629064 -1 4e' \
          'benchmarks/xz/cpu2006docs.tar.xz' ''
        record imagick imagick test 'test_input.tga, short filter chain' \
          benchmarks/imagick/imagick_r.riscv \
          '-limit disk 0 benchmarks/imagick/test_input.tga -shear 25 -resize 640x480 -negate -alpha Off {OUTDIR}/test_output.tga' \
          'benchmarks/imagick/test_input.tga' ''
        record blender blender test 'cube.blend, frame 1' \
          benchmarks/blender/blender_r.riscv \
          'benchmarks/blender/cube.blend --render-output {OUTDIR}/cube_ --threads 1 -b -F RAWTGA -s 1 -e 1 -a' \
          'benchmarks/blender/cube.blend' ''
        record povray povray test SPEC-benchmark-test.ini \
          benchmarks/povray/povray_r.riscv \
          'benchmarks/povray/SPEC-benchmark-test.ini' \
          'benchmarks/povray/SPEC-benchmark-test.ini' ''
        record omnetpp omnetpp test 'omnetpp_test.ini, sim-time-limit=0.003s' \
          benchmarks/omnetpp/omnetpp_r.riscv \
          '-c General -r 0 {OUTDIR}/omnetpp.ini' \
          'benchmarks/omnetpp/omnetpp_test.ini;benchmarks/omnetpp/ned' \
          benchmarks/omnetpp/omnetpp_test.ini
        record xalancbmk xalancbmk test 'test.xml + xalanc.xsl' \
          benchmarks/xalancbmk/xalancbmk_r.riscv \
          '-v benchmarks/xalancbmk/test.xml benchmarks/xalancbmk/xalanc.xsl' \
          'benchmarks/xalancbmk/test.xml;benchmarks/xalancbmk/xalanc.xsl' ''
        # SPEC test: one encode pass. BuckBunny_test.yuv is SPEC's
        # BuckBunny.264 decoded natively by ldecod_r (156 frames, 215,654,400
        # bytes; native and RISC-V ldecod_r output proved bit-identical on the
        # train video). --dumpyuv 50 writes frame_<N>.yuv to the cwd (gem5
        # root), as SPEC's validation expects.
        record x264 x264 test 'BuckBunny.yuv encode, 156 frames' \
          benchmarks/x264/x264_r.riscv \
          '--dumpyuv 50 --frames 156 -o {OUTDIR}/BuckBunny_New.264 benchmarks/x264/BuckBunny_test.yuv 1280x720' \
          'benchmarks/x264/BuckBunny_test.yuv' ''
        record gcc gcc test 't1.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/t1.c -O3 -finline-limit=50000 -o {OUTDIR}/t1.s' \
          'benchmarks/gcc/t1.c' ''
        record mcf mcf test inp.in \
          benchmarks/mcf/mcf_r.riscv \
          'benchmarks/mcf/inp.in' \
          'benchmarks/mcf/inp.in' ''
        record perlbench_makerand perlbench test makerand.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I. -I./lib makerand.pl' \
          'benchmarks/perlbench/makerand.pl;benchmarks/perlbench/lib' '' \
          benchmarks/perlbench
        # SPEC's second test invocation, test.pl, is left out: its t/TEST
        # forks and execs a new perl for each of its 316 tests, which a
        # one-CPU SE-mode gem5 cannot run. (The earlier perlbench_test entry
        # ran it from the gem5 root, where it stopped after one test: ~16M
        # instructions, not a valid result.)
        # Fortran benchmarks (built 2026-10-08 with ROI markers; see
        # scripts/spec_roi/). Each runs in a copy of its directory, which
        # holds SPEC's test and all/ inputs, with SPEC's own arguments.
        record bwaves_1 bwaves test bwaves_1.in \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_1 < bwaves_1.in' \
          'benchmarks/bwaves/bwaves_1.in' '' \
          benchmarks/bwaves
        record bwaves_2 bwaves test bwaves_2.in \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_2 < bwaves_2.in' \
          'benchmarks/bwaves/bwaves_2.in' '' \
          benchmarks/bwaves
        record exchange2 exchange2 test 'puzzles.txt, argument 0' \
          benchmarks/exchange2/exchange2_r.riscv \
          '0' \
          'benchmarks/exchange2/puzzles.txt' '' \
          benchmarks/exchange2
        record fotonik3d fotonik3d test 'yee.dat, OBJ.dat' \
          benchmarks/fotonik3d/fotonik3d_r.riscv \
          '' \
          'benchmarks/fotonik3d/yee.dat;benchmarks/fotonik3d/OBJ.dat' '' \
          benchmarks/fotonik3d
        record roms roms test ocean_benchmark0.in.x \
          benchmarks/roms/roms_r.riscv \
          '< ocean_benchmark0.in.x' \
          'benchmarks/roms/ocean_benchmark0.in.x;benchmarks/roms/varinfo.dat' '' \
          benchmarks/roms
        record wrf wrf test namelist.input \
          benchmarks/wrf/wrf_r.riscv \
          '' \
          'benchmarks/wrf/namelist.input;benchmarks/wrf/wrfinput_d01' '' \
          benchmarks/wrf
        record cam4 cam4 test 'atm_in, drv_in' \
          benchmarks/cam4/cam4_r.riscv \
          '' \
          'benchmarks/cam4/atm_in;benchmarks/cam4/drv_in' '' \
          benchmarks/cam4
        ;;
      train)
        record cactuBSSN cactuBSSN train spec_train.par \
          benchmarks/cactuBSSN/cactuBSSN_r.riscv \
          'benchmarks/cactuBSSN/spec_train.par' \
          'benchmarks/cactuBSSN/spec_train.par' ''
        record parest parest train train.prm \
          benchmarks/parest/parest_r.riscv \
          'benchmarks/parest/train.prm' \
          'benchmarks/parest/train.prm' ''
        record deepsjeng deepsjeng train train.txt \
          benchmarks/deepsjeng/deepsjeng_r.riscv \
          'benchmarks/deepsjeng/train.txt' \
          'benchmarks/deepsjeng/train.txt' ''
        record leela leela train train.sgf \
          benchmarks/leela/leela_r.riscv \
          'benchmarks/leela/train.sgf' \
          'benchmarks/leela/train.sgf' ''
        record namd namd train 'apoa1.input, 7 iterations' \
          benchmarks/namd/namd_r.riscv \
          '--input benchmarks/namd/apoa1.input --iterations 7 --output {OUTDIR}/apoa1.output' \
          'benchmarks/namd/apoa1.input' ''
        record lbm lbm train '300 steps, 100_100_130_cf_b.of' \
          benchmarks/lbm/lbm_r.riscv \
          '300 {OUTDIR}/reference.dat 0 1 benchmarks/lbm/100_100_130_cf_b.of' \
          'benchmarks/lbm/100_100_130_cf_b.of' ''
        record nab nab train 'aminos, 1000 iterations' \
          benchmarks/nab/nab_r.riscv \
          'aminos 391519156 1000' \
          'aminos/aminos.pdb;aminos/aminos.prm' ''
        record nab_gcn4dna nab train 'gcn4dna, 300 iterations' \
          benchmarks/nab/nab_r.riscv \
          'gcn4dna 1850041461 300' \
          'gcn4dna/gcn4dna.pdb;gcn4dna/gcn4dna.prm' ''
        record xz xz train 'IMG_2560.cr2.xz, level 4' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/IMG_2560.cr2.xz 40 ec03e53b02deae89b6650f1de4bed76a012366fb3d4bdc791e8633d1a5964e03004523752ab008eff0d9e693689c53056533a05fc4b277f0086544c6c3cbbbf6 40822692 40824404 4' \
          'benchmarks/xz/IMG_2560.cr2.xz' ''
        record xz_combined xz train 'input.combined.xz, level 8' \
          benchmarks/xz/xz_r.riscv \
          'benchmarks/xz/input.combined.xz 40 a841f68f38572a49d86226b7ff5baeb31bd19dc637a922a972b2e6d1257a890f6a544ecab967c313e370478c74f760eb229d4eef8a8d2836d233d3e9dd1430bf 6356684 -1 8' \
          'benchmarks/xz/input.combined.xz' ''
        record imagick imagick train 'train_input.tga, 8 filters' \
          benchmarks/imagick/imagick_r.riscv \
          '-limit disk 0 benchmarks/imagick/train_input.tga -resize 320x240 -shear 31 -edge 140 -negate -flop -resize 900x900 -edge 10 {OUTDIR}/train_output.tga' \
          'benchmarks/imagick/train_input.tga' ''
        record blender blender train 'sh5_reduced.blend, frame 234' \
          benchmarks/blender/blender_r.riscv \
          'benchmarks/blender/sh5_reduced.blend --render-output {OUTDIR}/sh5_ --threads 1 -b -F RAWTGA -s 234 -e 234 -a' \
          'benchmarks/blender/sh5_reduced.blend' ''
        record povray povray train SPEC-benchmark-train.ini \
          benchmarks/povray/povray_r.riscv \
          'benchmarks/povray/SPEC-benchmark-train.ini' \
          'benchmarks/povray/SPEC-benchmark-train.ini' ''
        record omnetpp omnetpp train 'omnetpp_train.ini, sim-time-limit=0.15s' \
          benchmarks/omnetpp/omnetpp_r.riscv \
          '-c General -r 0 {OUTDIR}/omnetpp.ini' \
          'benchmarks/omnetpp/omnetpp_train.ini;benchmarks/omnetpp/ned' \
          benchmarks/omnetpp/omnetpp_train.ini
        # xalanc_train.xsl is SPEC's train xalanc.xsl; xalanc.xsl is the
        # test/ref one, whose namespace does not match allbooks.xml.
        record xalancbmk xalancbmk train 'allbooks.xml + train xalanc.xsl' \
          benchmarks/xalancbmk/xalancbmk_r.riscv \
          '-v benchmarks/xalancbmk/allbooks.xml benchmarks/xalancbmk/xalanc_train.xsl' \
          'benchmarks/xalancbmk/allbooks.xml;benchmarks/xalancbmk/xalanc_train.xsl' ''
        # SPEC train: one encode pass. BuckBunny_train.yuv is SPEC's train
        # BuckBunny.264 decoded natively by ldecod_r (142 frames; md5 equal to
        # the RISC-V ldecod_r output under gem5).
        record x264 x264 train 'BuckBunny.yuv encode, 142 frames' \
          benchmarks/x264/x264_r.riscv \
          '--dumpyuv 50 --frames 142 -o {OUTDIR}/BuckBunny_New.264 benchmarks/x264/BuckBunny_train.yuv 1280x720' \
          'benchmarks/x264/BuckBunny_train.yuv' ''
        record gcc_200 gcc train '200.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/200.c -O3 -finline-limit=50000 -o {OUTDIR}/200.s' \
          'benchmarks/gcc/200.c' ''
        record gcc_scilab gcc train 'scilab.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/scilab.c -O3 -finline-limit=50000 -o {OUTDIR}/scilab.s' \
          'benchmarks/gcc/scilab.c' ''
        record gcc gcc train 'train01.c, -O3' \
          benchmarks/gcc/gcc_r.riscv \
          'benchmarks/gcc/train01.c -O3 -finline-limit=50000 -o {OUTDIR}/train01.s' \
          'benchmarks/gcc/train01.c' ''
        record mcf mcf train inp_train.in \
          benchmarks/mcf/mcf_r.riscv \
          'benchmarks/mcf/inp_train.in' \
          'benchmarks/mcf/inp_train.in' ''
        record perlbench_scrabbl perlbench train 'scrabbl.pl < scrabbl.in' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I. -I./lib scrabbl.pl < scrabbl.in' \
          'benchmarks/perlbench/scrabbl.pl;benchmarks/perlbench/scrabbl.in;benchmarks/perlbench/lib' '' \
          benchmarks/perlbench
        record perlbench_suns perlbench train suns.pl \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I. -I./lib suns.pl' \
          'benchmarks/perlbench/suns.pl;benchmarks/perlbench/lib' '' \
          benchmarks/perlbench
        record perlbench_diffmail perlbench train 'diffmail.pl 2 550 15 24 23 100' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./lib diffmail.pl 2 550 15 24 23 100' \
          'benchmarks/perlbench/diffmail.pl;benchmarks/perlbench/lib' '' \
          benchmarks/perlbench
        record perlbench_perfect perlbench train 'perfect.pl b 3' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./lib perfect.pl b 3' \
          'benchmarks/perlbench/perfect.pl;benchmarks/perlbench/lib' '' \
          benchmarks/perlbench
        record perlbench_splitmail perlbench train 'splitmail.pl 535 13 25 24 1091 1' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./lib splitmail.pl 535 13 25 24 1091 1' \
          'benchmarks/perlbench/splitmail.pl;benchmarks/perlbench/lib' '' \
          benchmarks/perlbench
        # Fortran benchmarks (added 2026-10-15): SPEC train invocations, each in
        # a private copy of benchmarks/<bench>/train/inputs/ (SPEC's train +
        # all inputs) with SPEC's own relative command line.
        record bwaves_1 bwaves train 'bwaves_1.in' \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_1 < bwaves_1.in' \
          'benchmarks/bwaves/train/inputs/bwaves_1.in' '' \
          benchmarks/bwaves/train/inputs
        record bwaves_2 bwaves train 'bwaves_2.in' \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_2 < bwaves_2.in' \
          'benchmarks/bwaves/train/inputs/bwaves_2.in' '' \
          benchmarks/bwaves/train/inputs
        record exchange2 exchange2 train 'puzzles.txt, argument 1' \
          benchmarks/exchange2/exchange2_r.riscv \
          '1' \
          'benchmarks/exchange2/train/inputs/puzzles.txt' '' \
          benchmarks/exchange2/train/inputs
        record fotonik3d fotonik3d train 'yee.dat, OBJ.dat' \
          benchmarks/fotonik3d/fotonik3d_r.riscv \
          '' \
          'benchmarks/fotonik3d/train/inputs/yee.dat;benchmarks/fotonik3d/train/inputs/OBJ.dat' '' \
          benchmarks/fotonik3d/train/inputs
        record roms roms train 'ocean_benchmark1.in.x' \
          benchmarks/roms/roms_r.riscv \
          '< ocean_benchmark1.in.x' \
          'benchmarks/roms/train/inputs/ocean_benchmark1.in.x;benchmarks/roms/train/inputs/varinfo.dat' '' \
          benchmarks/roms/train/inputs
        record wrf wrf train 'namelist.input (train)' \
          benchmarks/wrf/wrf_r.riscv \
          '' \
          'benchmarks/wrf/train/inputs/namelist.input;benchmarks/wrf/train/inputs/wrfinput_d01' '' \
          benchmarks/wrf/train/inputs
        record cam4 cam4 train 'atm_in, drv_in (train)' \
          benchmarks/cam4/cam4_r.riscv \
          '' \
          'benchmarks/cam4/train/inputs/atm_in;benchmarks/cam4/train/inputs/drv_in' '' \
          benchmarks/cam4/train/inputs
        ;;
      ref)
        # SPEC refrate, every invocation (runcpu --fake --nobuild, 2026-10-15).
        # Each runs in a private copy of benchmarks/<bench>/ref/inputs/ (SPEC's
        # refrate + all inputs, cache_scripts/make_input_dirs.py ref) with
        # SPEC's own relative command line.
        record cactuBSSN cactuBSSN ref 'spec_ref.par' \
          benchmarks/cactuBSSN/cactuBSSN_r.riscv \
          'spec_ref.par' \
          'benchmarks/cactuBSSN/ref/inputs/spec_ref.par' '' \
          benchmarks/cactuBSSN/ref/inputs
        record parest parest ref 'ref.prm' \
          benchmarks/parest/parest_r.riscv \
          'ref.prm' \
          'benchmarks/parest/ref/inputs/ref.prm' '' \
          benchmarks/parest/ref/inputs
        record deepsjeng deepsjeng ref 'ref.txt' \
          benchmarks/deepsjeng/deepsjeng_r.riscv \
          'ref.txt' \
          'benchmarks/deepsjeng/ref/inputs/ref.txt' '' \
          benchmarks/deepsjeng/ref/inputs
        record leela leela ref 'ref.sgf' \
          benchmarks/leela/leela_r.riscv \
          'ref.sgf' \
          'benchmarks/leela/ref/inputs/ref.sgf' '' \
          benchmarks/leela/ref/inputs
        record namd namd ref 'apoa1.input, 65 iterations' \
          benchmarks/namd/namd_r.riscv \
          '--input apoa1.input --output apoa1.ref.output --iterations 65' \
          'benchmarks/namd/ref/inputs/apoa1.input' '' \
          benchmarks/namd/ref/inputs
        record lbm lbm ref '3000 steps, 100_100_130_ldc.of' \
          benchmarks/lbm/lbm_r.riscv \
          '3000 reference.dat 0 0 100_100_130_ldc.of' \
          'benchmarks/lbm/ref/inputs/100_100_130_ldc.of' '' \
          benchmarks/lbm/ref/inputs
        record nab nab ref '1am0, 122 iterations' \
          benchmarks/nab/nab_r.riscv \
          '1am0 1122214447 122' \
          'benchmarks/nab/ref/inputs/1am0' '' \
          benchmarks/nab/ref/inputs
        record xz_cld xz ref 'cld.tar.xz, 160 MB, level 6' \
          benchmarks/xz/xz_r.riscv \
          'cld.tar.xz 160 19cf30ae51eddcbefda78dd06014b4b96281456e078ca7c13e1c0c9e6aaea8dff3efb4ad6b0456697718cede6bd5454852652806a657bb56e07d61128434b474 59796407 61004416 6' \
          'benchmarks/xz/ref/inputs/cld.tar.xz' '' \
          benchmarks/xz/ref/inputs
        record xz_cpu2006docs xz ref 'cpu2006docs.tar.xz, 250 MB, level 6e' \
          benchmarks/xz/xz_r.riscv \
          'cpu2006docs.tar.xz 250 055ce243071129412e9dd0b3b69a21654033a9b723d874b2015c774fac1553d9713be561ca86f74e4f16f22e664fc17a79f30caa5ad2c04fbc447549c2810fae 23047774 23513385 6e' \
          'benchmarks/xz/ref/inputs/cpu2006docs.tar.xz' '' \
          benchmarks/xz/ref/inputs
        record xz_combined xz ref 'input.combined.xz, 250 MB, level 7' \
          benchmarks/xz/xz_r.riscv \
          'input.combined.xz 250 a841f68f38572a49d86226b7ff5baeb31bd19dc637a922a972b2e6d1257a890f6a544ecab967c313e370478c74f760eb229d4eef8a8d2836d233d3e9dd1430bf 40401484 41217675 7' \
          'benchmarks/xz/ref/inputs/input.combined.xz' '' \
          benchmarks/xz/ref/inputs
        record imagick imagick ref 'refrate_input.tga, 6 filters' \
          benchmarks/imagick/imagick_r.riscv \
          '-limit disk 0 refrate_input.tga -edge 41 -resample 181% -emboss 31 -colorspace YUV -mean-shift 19x19+15% -resize 30% refrate_output.tga' \
          'benchmarks/imagick/ref/inputs/refrate_input.tga' '' \
          benchmarks/imagick/ref/inputs
        record blender blender ref 'sh3_no_char.blend, frame 849' \
          benchmarks/blender/blender_r.riscv \
          'sh3_no_char.blend --render-output sh3_no_char_ --threads 1 -b -F RAWTGA -s 849 -e 849 -a' \
          'benchmarks/blender/ref/inputs/sh3_no_char.blend' '' \
          benchmarks/blender/ref/inputs
        record povray povray ref 'SPEC-benchmark-ref.ini' \
          benchmarks/povray/povray_r.riscv \
          'SPEC-benchmark-ref.ini' \
          'benchmarks/povray/ref/inputs/SPEC-benchmark-ref.ini' '' \
          benchmarks/povray/ref/inputs
        record omnetpp omnetpp ref 'omnetpp.ini (refrate)' \
          benchmarks/omnetpp/omnetpp_r.riscv \
          '-c General -r 0' \
          'benchmarks/omnetpp/ref/inputs/omnetpp.ini;benchmarks/omnetpp/ref/inputs/ned' '' \
          benchmarks/omnetpp/ref/inputs
        record xalancbmk xalancbmk ref 't5.xml + xalanc.xsl' \
          benchmarks/xalancbmk/xalancbmk_r.riscv \
          '-v t5.xml xalanc.xsl' \
          'benchmarks/xalancbmk/ref/inputs/t5.xml;benchmarks/xalancbmk/ref/inputs/xalanc.xsl' '' \
          benchmarks/xalancbmk/ref/inputs
        # x264: SPEC's three invocations. BuckBunny.yuv is the refrate
        # BuckBunny.264 decoded natively by ldecod_r (1250 frames). Pass 2
        # reads pass 1's x264_stats.log(.mbtree), which must be in the input
        # directory first (from a qemu run of pass 1).
        record x264_pass1 x264 ref 'pass 1, 1000 frames' \
          benchmarks/x264/x264_r.riscv \
          '--pass 1 --stats x264_stats.log --bitrate 1000 --frames 1000 -o BuckBunny_New.264 BuckBunny.yuv 1280x720' \
          'benchmarks/x264/ref/inputs/BuckBunny.yuv' '' \
          benchmarks/x264/ref/inputs
        record x264_pass2 x264 ref 'pass 2, 1000 frames' \
          benchmarks/x264/x264_r.riscv \
          '--pass 2 --stats x264_stats.log --bitrate 1000 --dumpyuv 200 --frames 1000 -o BuckBunny_New.264 BuckBunny.yuv 1280x720' \
          'benchmarks/x264/ref/inputs/BuckBunny.yuv;benchmarks/x264/ref/inputs/x264_stats.log;benchmarks/x264/ref/inputs/x264_stats.log.mbtree' '' \
          benchmarks/x264/ref/inputs
        record x264_seek x264 ref 'frames 500-1749 (seek 500, 1250 frames)' \
          benchmarks/x264/x264_r.riscv \
          '--seek 500 --dumpyuv 200 --frames 1250 -o BuckBunny_New.264 BuckBunny.yuv 1280x720' \
          'benchmarks/x264/ref/inputs/BuckBunny.yuv' '' \
          benchmarks/x264/ref/inputs
        record gcc_pp_O3 gcc ref 'gcc-pp.c -O3 -finline-limit=0 -fif-conversion -fif-conversion2' \
          benchmarks/gcc/gcc_r.riscv \
          'gcc-pp.c -O3 -finline-limit=0 -fif-conversion -fif-conversion2 -o gcc-pp.opts-O3_-finline-limit_0_-fif-conversion_-fif-conversion2.s' \
          'benchmarks/gcc/ref/inputs/gcc-pp.c' '' \
          benchmarks/gcc/ref/inputs
        record gcc_pp_O2 gcc ref 'gcc-pp.c -O2 -finline-limit=36000 -fpic' \
          benchmarks/gcc/gcc_r.riscv \
          'gcc-pp.c -O2 -finline-limit=36000 -fpic -o gcc-pp.opts-O2_-finline-limit_36000_-fpic.s' \
          'benchmarks/gcc/ref/inputs/gcc-pp.c' '' \
          benchmarks/gcc/ref/inputs
        record gcc_smaller gcc ref 'gcc-smaller.c -O3 -fipa-pta' \
          benchmarks/gcc/gcc_r.riscv \
          'gcc-smaller.c -O3 -fipa-pta -o gcc-smaller.opts-O3_-fipa-pta.s' \
          'benchmarks/gcc/ref/inputs/gcc-smaller.c' '' \
          benchmarks/gcc/ref/inputs
        record gcc_ref32_O5 gcc ref 'ref32.c -O5' \
          benchmarks/gcc/gcc_r.riscv \
          'ref32.c -O5 -o ref32.opts-O5.s' \
          'benchmarks/gcc/ref/inputs/ref32.c' '' \
          benchmarks/gcc/ref/inputs
        record gcc_ref32_O3 gcc ref 'ref32.c -O3 -fselective-scheduling -fselective-scheduling2' \
          benchmarks/gcc/gcc_r.riscv \
          'ref32.c -O3 -fselective-scheduling -fselective-scheduling2 -o ref32.opts-O3_-fselective-scheduling_-fselective-scheduling2.s' \
          'benchmarks/gcc/ref/inputs/ref32.c' '' \
          benchmarks/gcc/ref/inputs
        record mcf mcf ref 'inp.in (refrate)' \
          benchmarks/mcf/mcf_r.riscv \
          'inp.in' \
          'benchmarks/mcf/ref/inputs/inp.in' '' \
          benchmarks/mcf/ref/inputs
        record perlbench_checkspam perlbench ref 'checkspam.pl 2500 5 25 11 150 1 1 1 1' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./lib checkspam.pl 2500 5 25 11 150 1 1 1 1' \
          'benchmarks/perlbench/ref/inputs/checkspam.pl;benchmarks/perlbench/ref/inputs/lib' '' \
          benchmarks/perlbench/ref/inputs
        record perlbench_diffmail perlbench ref 'diffmail.pl 4 800 10 17 19 300' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./lib diffmail.pl 4 800 10 17 19 300' \
          'benchmarks/perlbench/ref/inputs/diffmail.pl;benchmarks/perlbench/ref/inputs/lib' '' \
          benchmarks/perlbench/ref/inputs
        record perlbench_splitmail perlbench ref 'splitmail.pl 6400 12 26 16 100 0' \
          benchmarks/perlbench/perlbench_r.riscv \
          '-I./lib splitmail.pl 6400 12 26 16 100 0' \
          'benchmarks/perlbench/ref/inputs/splitmail.pl;benchmarks/perlbench/ref/inputs/lib' '' \
          benchmarks/perlbench/ref/inputs
        # Fortran benchmarks.
        record bwaves_1 bwaves ref 'bwaves_1.in' \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_1 < bwaves_1.in' \
          'benchmarks/bwaves/ref/inputs/bwaves_1.in' '' \
          benchmarks/bwaves/ref/inputs
        record bwaves_2 bwaves ref 'bwaves_2.in' \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_2 < bwaves_2.in' \
          'benchmarks/bwaves/ref/inputs/bwaves_2.in' '' \
          benchmarks/bwaves/ref/inputs
        record bwaves_3 bwaves ref 'bwaves_3.in' \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_3 < bwaves_3.in' \
          'benchmarks/bwaves/ref/inputs/bwaves_3.in' '' \
          benchmarks/bwaves/ref/inputs
        record bwaves_4 bwaves ref 'bwaves_4.in' \
          benchmarks/bwaves/bwaves_r.riscv \
          'bwaves_4 < bwaves_4.in' \
          'benchmarks/bwaves/ref/inputs/bwaves_4.in' '' \
          benchmarks/bwaves/ref/inputs
        record exchange2 exchange2 ref 'puzzles.txt, argument 6' \
          benchmarks/exchange2/exchange2_r.riscv \
          '6' \
          'benchmarks/exchange2/ref/inputs/puzzles.txt' '' \
          benchmarks/exchange2/ref/inputs
        record fotonik3d fotonik3d ref 'yee.dat, OBJ.dat' \
          benchmarks/fotonik3d/fotonik3d_r.riscv \
          '' \
          'benchmarks/fotonik3d/ref/inputs/yee.dat;benchmarks/fotonik3d/ref/inputs/OBJ.dat' '' \
          benchmarks/fotonik3d/ref/inputs
        record roms roms ref 'ocean_benchmark2.in.x' \
          benchmarks/roms/roms_r.riscv \
          '< ocean_benchmark2.in.x' \
          'benchmarks/roms/ref/inputs/ocean_benchmark2.in.x;benchmarks/roms/ref/inputs/varinfo.dat' '' \
          benchmarks/roms/ref/inputs
        record wrf wrf ref 'namelist.input (refrate)' \
          benchmarks/wrf/wrf_r.riscv \
          '' \
          'benchmarks/wrf/ref/inputs/namelist.input;benchmarks/wrf/ref/inputs/wrfinput_d01' '' \
          benchmarks/wrf/ref/inputs
        record cam4 cam4 ref 'atm_in, drv_in (refrate)' \
          benchmarks/cam4/cam4_r.riscv \
          '' \
          'benchmarks/cam4/ref/inputs/atm_in;benchmarks/cam4/ref/inputs/drv_in' '' \
          benchmarks/cam4/ref/inputs
        ;;
    esac
}

# A target is a run ID, a benchmark name or "all". A target that is a run ID
# of the input set means that run only, even when it is also a benchmark name
# (train's "gcc" run must not take gcc_200 and gcc_scilab along, nor "nab"
# nab_gcn4dna, nor "xz" xz_combined); otherwise it means every run of the
# benchmark. RUN_IDS (space separated, padded) holds the input set's run IDs.
matches_targets() {
    local run_id="$1" benchmark="$2"
    shift 2
    local target
    (( $# == 0 )) && return 0
    for target in "$@"; do
        [[ "$target" == all || "$target" == "$run_id" ]] && return 0
        [[ "$target" == "$benchmark" && "${RUN_IDS:-}" != *" $target "* ]] && return 0
    done
    return 1
}

selected_manifest() {
    local profile="$1"
    shift
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local RUN_IDS=" $(manifest "$profile" | cut -d$'\x1f' -f1 | tr '\n' ' ')"
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        matches_targets "$run_id" "$benchmark" "$@" || continue
        record "$run_id" "$benchmark" "$input_set" "$input_desc" "$binary" \
            "$options" "$required" "$omnet_ini" "$run_src"
    done < <(manifest "$profile")
}

# Where a run's output goes: one directory per benchmark, input set and cache
# configuration, so runs of different inputs never share a directory:
#   benchmarks/<benchmark>/<input>/m5out/<cache>/<run_id>_<HHMM_DDMMYYYY>
# benchmarks/<benchmark>/<input>/report/ holds the input's reports. (Runs
# before 2026-10-15 lie in benchmarks/<benchmark>/m5out_<benchmark>/.)
run_outbase() {
    printf '%s/benchmarks/%s/%s/m5out/%s' "$ROOT_DIR" "$1" "$2" "$3"
}

# The latest_<profile>_<cache>_<run_id> links that find a run's newest output
# stay in one index directory per benchmark, whichever tree the run is in.
run_base() {
    local benchmark="$1"
    printf '%s/benchmarks/%s/m5out_%s' "$ROOT_DIR" "$benchmark" "$benchmark"
}

# One symlink per (profile, cache, run_id) pointing at that combination's most
# recent run, so lookups stay O(1) without scanning every run directory.
latest_link() {
    local profile="$1" cache="$2" benchmark="$3" run_id="$4"
    printf '%s/latest_%s_%s_%s' "$(run_base "$benchmark")" "$profile" "$cache" "$run_id"
}

latest_dir() {
    local link
    link="$(latest_link "$1" "$2" "$3" "$4")"
    [[ -L "$link" || -d "$link" ]] || return 1
    readlink -f "$link"
}

format_duration() {
    local seconds="${1:-0}"
    (( seconds < 0 )) && seconds=0
    printf '%02d:%02d:%02d' "$((seconds / 3600))" \
        "$(((seconds % 3600) / 60))" "$((seconds % 60))"
}

file_value() {
    local file="$1" value=''
    if [[ -r "$file" ]]; then
        IFS= read -r value < "$file" || true
    fi
    printf '%s' "$value"
}

read_state() {
    local outdir="$1" state pid host
    [[ -n "$outdir" && -d "$outdir" ]] || { printf PENDING; return; }
    state="$(file_value "$outdir/.runner/status")"
    pid="$(file_value "$outdir/.runner/worker.pid")"
    if [[ "$state" == RUNNING ]]; then
        # /cta/users is shared between hosts: a run started on another host
        # has a PID that cannot be checked from here, so trust its status.
        host="$(file_value "$outdir/.runner/host")"
        if [[ -n "$host" && "$host" != "$(hostname)" ]]; then
            printf RUNNING
            return
        fi
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            printf RUNNING
        else
            printf INTERRUPTED
        fi
        return
    fi
    if [[ -n "$state" ]]; then
        printf '%s' "$state"
    elif [[ -f "$outdir/riscv_spill_stats.txt" ]] &&
         grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*10$' "$outdir/riscv_spill_stats.txt"; then
        printf COMPLETED
    else
        printf UNKNOWN
    fi
}

validate_paths() {
    local binary="$1" required="$2" missing=0 path
    [[ -x "$ROOT_DIR/$binary" ]] || {
        printf '  MISSING executable: %s\n' "$binary" >&2
        missing=1
    }
    IFS=';' read -r -a required_paths <<< "$required"
    for path in "${required_paths[@]}"; do
        [[ -z "$path" || -e "$ROOT_DIR/$path" ]] && continue
        printf '  MISSING input:      %s\n' "$path" >&2
        missing=1
    done
    return "$missing"
}

# The private run directory of a run_dir workload, standing in for SPEC's,
# so parallel runs never share a file they write. Small files are copied (a
# program may rewrite them); large files (cam4: 281 MB of NetCDF input) and
# directories (perlbench: lib/) are read-only inputs and are linked. Results
# and binaries are left out.
prepare_run_dir() {
    local src="$ROOT_DIR/$1" dst="$2" entry
    mkdir -p "$dst"
    for entry in "$src"/*; do
        case "${entry##*/}" in
          m5out_*|reports|test|train|ref|*.riscv|*.stack_pc_map) continue ;;
        esac
        if [[ -d "$entry" ]] || (( $(stat -c %s "$entry") > 4194304 )); then
            ln -s "$entry" "$dst/"
        else
            cp -a "$entry" "$dst/"
        fi
    done
}

# A run_dir workload starts as "<binary name>" inside its run directory, as
# in SPEC (argv[0] relative: perlbench's t/TEST runs each test as "../$^X").
# Links the binary (or the given stand-in) there and prints the name.
link_run_binary() {
    ln -sfn "${3:-$ROOT_DIR/$1}" "$2/${1##*/}"
    printf '%s' "${1##*/}"
}

# program_options without, and the file of, a trailing "< FILE" (stdin).
strip_stdin() {
    local s=" $1"
    if [[ "$s" == *' < '* ]]; then s="${s% < *}"; printf '%s' "${s# }"; else printf '%s' "$1"; fi
}
stdin_file() {
    local s=" $1"
    if [[ "$s" == *' < '* ]]; then printf '%s' "${s##* < }"; fi
}

verify_gem5_build() {
    local source
    [[ -x "$GEM5_BIN" ]] || die "gem5 binary is missing or not executable: $GEM5_BIN"
    [[ -f "$GEM5_CONFIG" ]] || die "gem5 config is missing: $GEM5_CONFIG"
    if ! grep -a -q -m1 '# detection          : runtime effective address only' "$GEM5_BIN"; then
        die "gem5 binary does not contain the schema-10 spill metrics: $GEM5_BIN"
    fi
    for source in \
        src/cpu/simple/spill_detector.cc \
        src/cpu/simple/spill_detector.hh \
        src/cpu/simple/timing.cc \
        src/mem/cache/base.hh \
        src/mem/cache/base.cc \
        src/mem/request.hh; do
        if [[ "$ROOT_DIR/$source" -nt "$GEM5_BIN" ]]; then
            die "gem5 binary is older than $source; rebuild it before launching SPEC"
        fi
    done
}

# se.py options for a cache profile: SIZE picks the capacities, ORG the
# organisation of L1D and L2 (see the usage text). The options themselves are
# defined in configs/common/Options.py and applied in CacheConfig.py.
cache_options() {
    local size="${1%%-*}" org="" opts
    [[ "$1" == *-* ]] && org="${1#*-}"
    opts='--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB'
    case "$size" in
      standard) ;;   # se.py defaults: L1D 64KiB, L1I 32KiB, L2 2MiB
      small) opts+=' --l1d_size=4kB --l1i_size=32kB --l2_size=32kB' ;;
    esac
    case "$org" in
      '')   ;;       # se.py defaults: L1D 2-way, L2 8-way
      [0-9]*way) opts+=" --l1d_assoc=${org%way} --l2_assoc=8" ;;  # L1D N-way, L2 8-way
      dm)   opts+=' --l1d_assoc=1 --l2_assoc=1' ;;
      nway) opts+=' --l1d_assoc=8 --l2_assoc=16' ;;
      fa)   opts+=' --l1d_tags=FALRU --l2_tags=FALRU' ;;
    esac
    printf '%s\n' "$opts"
}

prepare_omnet_ini() {
    local source_ini="$1" outdir="$2"
    [[ -n "$source_ini" ]] || return 0
    sed -E \
        -e "s|^[[:space:]]*ned-path[[:space:]]*=.*|ned-path = $ROOT_DIR/benchmarks/omnetpp/ned|" \
        -e "s|^[[:space:]]*result-dir[[:space:]]*=.*|result-dir = $outdir|" \
        "$ROOT_DIR/$source_ini" > "$outdir/omnetpp.ini"
}

worker_stop_requested=0
worker_child_pid=''

worker_stop() {
    worker_stop_requested=1
    [[ -n "$worker_child_pid" ]] && kill -TERM "$worker_child_pid" 2>/dev/null || true
}

run_worker() {
    local profile="$1" cache="$2" wanted_id="$3" outdir="$4"
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local found=0 rc=0 final_state cache_args

    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        [[ "$run_id" == "$wanted_id" ]] || continue
        found=1
        break
    done < <(manifest "$profile")
    (( found == 1 )) || die "worker manifest entry not found: $wanted_id"

    mkdir -p "$outdir/.runner"
    printf '%s\n' "$$" > "$outdir/.runner/worker.pid"
    printf '%s\n' RUNNING > "$outdir/.runner/status"
    printf '%s\n' "$(date +%s)" > "$outdir/.runner/started.epoch"
    printf '%s\n' "$(date --iso-8601=seconds)" > "$outdir/.runner/started_at"
    git -C "$ROOT_DIR" rev-parse HEAD > "$outdir/.runner/gem5_commit" 2>/dev/null || true
    hostname > "$outdir/.runner/host"

    prepare_omnet_ini "$omnet_ini" "$outdir"
    options="${options//\{OUTDIR\}/$outdir}"
    local workdir="$ROOT_DIR" cmd_path="$ROOT_DIR/$binary"
    if [[ -n "$run_src" ]]; then
        workdir="$outdir/run"
        prepare_run_dir "$run_src" "$workdir"
        cmd_path="$(link_run_binary "$binary" "$workdir")"
    fi
    local -a stdin_args=()
    if [[ -n "$(stdin_file "$options")" ]]; then
        stdin_args=("--input=$workdir/$(stdin_file "$options")")
        options="$(strip_stdin "$options")"
    fi
    cache_args="$(cache_options "$cache")"
    printf 'cd %q && ' "$workdir" > "$outdir/.runner/command.sh"
    printf '%q ' "$GEM5_BIN" "--outdir=$outdir" "$GEM5_CONFIG" \
        "--cmd=$cmd_path" "--options=$options" "${stdin_args[@]}" \
        $cache_args >> "$outdir/.runner/command.sh"
    printf '\n' >> "$outdir/.runner/command.sh"

    trap worker_stop TERM INT
    cd "$workdir" || exit 1
    # options and cache_args must be split for se.py's argv interface.
    "$GEM5_BIN" "--outdir=$outdir" "$GEM5_CONFIG" \
        "--cmd=$cmd_path" "--options=$options" "${stdin_args[@]}" \
        $cache_args > "$outdir/nohup.log" 2>&1 &
    worker_child_pid=$!
    printf '%s\n' "$worker_child_pid" > "$outdir/.runner/gem5.pid"
    wait "$worker_child_pid" || rc=$?

    if (( worker_stop_requested == 1 )); then
        final_state=STOPPED
    elif (( rc != 0 )); then
        final_state=FAILED
    elif grep -Eq '(^|[[:space:]])(fatal|panic):|^<!> Error:|Program aborted|Segmentation fault' \
            "$outdir/nohup.log"; then
        final_state=FAILED
    elif grep -q 'Simulated exit code not 0' "$outdir/nohup.log"; then
        # gem5 itself exits 0 when the simulated program fails
        final_state=FAILED
    elif [[ ! -f "$outdir/riscv_spill_stats.txt" ]] ||
         ! grep -Eq '^# metric_schema[[:space:]]*:[[:space:]]*10$' \
            "$outdir/riscv_spill_stats.txt"; then
        final_state=INVALID_SCHEMA
    elif ! grep -q '^# ROI SUMMARY' "$outdir/riscv_spill_stats.txt"; then
        final_state=NO_ROI
    elif [[ ! -f "$outdir/stats.txt" ]] ||
         ! grep -q '^---------- End Simulation Statistics' "$outdir/stats.txt"; then
        final_state=INCOMPLETE
    else
        final_state=COMPLETED
    fi

    printf '%s\n' "$rc" > "$outdir/.runner/exit_code"
    printf '%s\n' "$(date +%s)" > "$outdir/.runner/finished.epoch"
    printf '%s\n' "$(date --iso-8601=seconds)" > "$outdir/.runner/finished_at"
    printf '%s\n' "$final_state" > "$outdir/.runner/status"
}

command_list() {
    local profile="${1:-}" run_id benchmark input_set input_desc binary options required omnet_ini run_src
    if [[ -n "$profile" ]]; then
        valid_profile "$profile" || die "invalid profile: $profile"
    else
        profile=test
    fi
    printf '%-23s %-13s %-15s %s\n' RUN_ID BENCHMARK INPUT_SET INPUT
    printf '%-23s %-13s %-15s %s\n' '-----------------------' '-------------' '---------------' '-----'
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        printf '%-23s %-13s %-15s %s\n' "$run_id" "$benchmark" "$input_set" "$input_desc"
    done < <(manifest "$profile")
}

command_check() {
    local profile="$1" cache="$2"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src count=0 failures=0
    verify_gem5_build
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        ((count++))
        printf '[%-23s] ' "$run_id"
        if validate_paths "$binary" "$required"; then
            printf 'OK (%s)\n' "$input_desc"
        else
            printf 'FAILED\n'
            ((failures++))
        fi
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
    printf '\nChecked: %d, failures: %d, cache: %s\n' "$count" "$failures" "$cache"
    (( failures == 0 ))
}

command_start() {
    local profile="$1" cache="$2"
    shift 2
    (( $# > 0 )) || die 'start requires a run ID, benchmark name, or all'
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local count=0 failures=0 base outdir stamp worker_pid current latest
    verify_gem5_build
    # HHMM_DDMMYYYY, e.g. mcf_1230_16092026
    stamp="$(date '+%H%M_%d%m%Y')"
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        ((count++))
        if ! validate_paths "$binary" "$required"; then
            printf '[%-23s] NOT STARTED: prerequisite failure\n' "$run_id" >&2
            ((failures++))
            continue
        fi
        latest="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        current="$(read_state "$latest")"
        if [[ "$current" == RUNNING ]]; then
            printf '[%-23s] ALREADY RUNNING: %s\n' "$run_id" "$latest"
            continue
        fi
        base="$(run_outbase "$benchmark" "$profile" "$cache")"
        outdir="$base/${run_id}_${stamp}"
        # Two runs of the same run ID within one minute (also from two hosts
        # sharing /cta/users) would otherwise land in the same directory;
        # mkdir is atomic, so exactly one of them gets each name.
        mkdir -p "$base" "$ROOT_DIR/benchmarks/$benchmark/$profile/report" "$(run_base "$benchmark")"
        local candidate="$outdir" suffix=1
        until mkdir "$candidate" 2>/dev/null; do
            suffix=$((suffix + 1))
            candidate="${outdir}_${suffix}"
        done
        outdir="$candidate"
        mkdir -p "$outdir/.runner"
        printf '%s\n' STARTING > "$outdir/.runner/status"
        printf '%s\n' "$profile" > "$outdir/.runner/profile"
        printf '%s\n' "$cache" > "$outdir/.runner/cache"
        printf '%s\n' "$run_id" > "$outdir/.runner/run_id"
        printf '%s\n' "$benchmark" > "$outdir/.runner/benchmark"
        ln -sfn "$outdir" "$(latest_link "$profile" "$cache" "$benchmark" "$run_id")"
        ln -sfn "${outdir##*/}" "$base/latest_${run_id}"
        nohup "$SCRIPT_PATH" __worker "$profile" "$cache" "$run_id" "$outdir" \
            </dev/null > "$outdir/.runner/worker.log" 2>&1 &
        worker_pid=$!
        printf '%s\n' "$worker_pid" > "$outdir/.runner/worker.pid"
        printf '[%-23s] STARTED pid=%-7s input=%s\n' \
            "$run_id" "$worker_pid" "$input_desc"
        printf '  outdir=%s\n' "$outdir"
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
    printf '\nSelected: %d, prerequisite failures: %d\n' "$count" "$failures"
}

command_status() {
    local profile="$1" cache="$2"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local count=0 state outdir pid started finished now elapsed
    printf '%-23s %-13s %-12s %-8s %-10s %s\n' RUN_ID INPUT_SET STATE PID ELAPSED INPUT
    printf '%-23s %-13s %-12s %-8s %-10s %s\n' \
        '-----------------------' '-------------' '------------' '--------' '----------' '-----'
    now="$(date +%s)"
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        ((count++))
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        state="$(read_state "$outdir")"
        pid='-'
        elapsed='-'
        if [[ -n "$outdir" ]]; then
            pid="$(file_value "$outdir/.runner/gem5.pid")"
            [[ -n "$pid" ]] || pid="$(file_value "$outdir/.runner/worker.pid")"
            [[ -n "$pid" ]] || pid='-'
            started="$(file_value "$outdir/.runner/started.epoch")"
            finished="$(file_value "$outdir/.runner/finished.epoch")"
            if [[ "$started" =~ ^[0-9]+$ ]]; then
                if [[ "$finished" =~ ^[0-9]+$ ]]; then
                    elapsed="$(format_duration "$((finished - started))")"
                else
                    elapsed="$(format_duration "$((now - started))")"
                fi
            fi
        fi
        printf '%-23s %-13s %-12s %-8s %-10s %s\n' \
            "$run_id" "$input_set" "$state" "$pid" "$elapsed" "$input_desc"
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
}

command_stop() {
    local profile="$1" cache="$2"
    shift 2
    (( $# > 0 )) || die 'stop requires a run ID, benchmark name, or all'
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local count=0 outdir state pid host
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        ((count++))
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        state="$(read_state "$outdir")"
        if [[ "$state" != RUNNING ]]; then
            printf '[%-23s] not running (state=%s)\n' "$run_id" "$state"
            continue
        fi
        # A PID is only meaningful on the host that started the run; on any
        # other host it could name an unrelated process.
        host="$(file_value "$outdir/.runner/host")"
        if [[ -n "$host" && "$host" != "$(hostname)" ]]; then
            printf '[%-23s] runs on %s; stop it there\n' "$run_id" "$host"
            continue
        fi
        pid="$(file_value "$outdir/.runner/worker.pid")"
        if [[ "$pid" =~ ^[0-9]+$ ]]; then
            kill -TERM "$pid"
            printf '[%-23s] stop requested (worker pid=%s)\n' "$run_id" "$pid"
        else
            printf '[%-23s] cannot stop: invalid worker PID\n' "$run_id" >&2
        fi
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
}

command_log() {
    local profile="$1" cache="$2" wanted_id="$3" lines="${4:-40}"
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local found=0 outdir
    [[ "$lines" =~ ^[0-9]+$ ]] || die "LINES must be an integer"
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        [[ "$run_id" == "$wanted_id" ]] || continue
        found=1
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        [[ -n "$outdir" && -f "$outdir/nohup.log" ]] || die "no log for $wanted_id"
        printf '==> %s <==\n' "$outdir/nohup.log"
        tail -n "$lines" "$outdir/nohup.log"
    done < <(manifest "$profile")
    (( found == 1 )) || die "unknown run ID: $wanted_id"
}

command_results() {
    local profile="$1" cache="$2"
    shift 2
    local run_id benchmark input_set input_desc binary options required omnet_ini run_src
    local count=0 failures=0 outdir state
    [[ -x "$ANALYZER" || -f "$ANALYZER" ]] || die "analyzer not found: $ANALYZER"
    while IFS=$'\x1f' read -r run_id benchmark input_set input_desc binary options required omnet_ini run_src; do
        ((count++))
        outdir="$(latest_dir "$profile" "$cache" "$benchmark" "$run_id" 2>/dev/null || true)"
        state="$(read_state "$outdir")"
        if [[ "$state" != COMPLETED ]]; then
            printf '[%s] result unavailable: state=%s\n' "$run_id" "$state" >&2
            ((failures++))
            continue
        fi
        printf '\n===== %s | %s | %s =====\n' "$run_id" "$input_set" "$input_desc"
        python3 "$ANALYZER" --no-files "$outdir" || ((failures++))
    done < <(selected_manifest "$profile" "$@")
    (( count > 0 )) || die "no benchmark matched the requested target(s)"
    (( failures == 0 ))
}

main() {
    local command="${1:-help}"
    shift || true
    case "$command" in
      help|-h|--help)
        usage
        ;;
      list)
        command_list "${1:-test}"
        ;;
      check|start|status|stop|results)
        (( $# >= 2 )) || { usage >&2; exit 1; }
        valid_profile "$1" || die "invalid profile: $1"
        valid_cache "$2" || die "invalid cache: $2"
        "command_$command" "$@"
        ;;
      log)
        (( $# >= 3 )) || { usage >&2; exit 1; }
        valid_profile "$1" || die "invalid profile: $1"
        valid_cache "$2" || die "invalid cache: $2"
        command_log "$@"
        ;;
      __worker)
        (( $# == 4 )) || die 'invalid worker invocation'
        valid_profile "$1" || die "invalid profile: $1"
        valid_cache "$2" || die "invalid cache: $2"
        run_worker "$@"
        ;;
      *)
        usage >&2
        die "unknown command: $command"
        ;;
    esac
}

main "$@"
