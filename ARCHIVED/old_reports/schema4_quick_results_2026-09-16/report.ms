.pl 8.27i
.po 0.45i
.ll 10.75i
.lt 10.75i
.ps 9
.vs 11
.de PP
.sp 0.12i
.ne 2
..
.de H1
.sp 0.22i
.ne 3
.ft B
.ps 14
\\$*
.ps 9
.ft R
.sp 0.06i
..
.sp 0.25i
.ft B
.ps 22
SPEC CPU2017 Spill Metrics - Schema-v4 Quick Results
.ps 10
.ft R
.br
Generated 2026-09-16 10:04 +03
.ps 9
.PP
Three short SPEC CPU2017 workloads completed successfully with the corrected gem5 spill detector.
.H1 Experimental scope
.PP
Simulator: gem5 RISC-V TimingSimpleCPU, private L1 caches, L2 cache, 4 GiB memory.
.PP
Detector: heuristic_stack_store_reload_match; metric schema 4.
.PP
gem5 commit: 62d20b39c49f.
.PP
Selection: the three fastest available small-input workloads based on earlier host-time observations. Existing valid GCC output was reused; missing Perlbench and Imagick outputs were run for this report.
.ps 8
.TS
center box tab(|);
l l r c l
.
\fBBenchmark\fP|\fBInput\fP|\fBDuration\fP|\fBState\fP|\fBClassification\fP
_
GCC|t1.c, -O3|00:00:09|COMPLETED|heuristic_stack_store_reload_match
Perlbench|test.pl|00:00:09|COMPLETED|heuristic_stack_store_reload_match
Imagick|test_input.tga, short filter chain|00:00:54|COMPLETED|heuristic_stack_store_reload_match
.TE
.ps 9
.PP
LIMITATION: These are small functional workloads, not official SPEC reportable performance runs. The heuristic identifies qualifying stack store-to-later-load reuse; it is not compiler ground truth. Conclusions apply only to these executions.
.H1 Dynamic instruction results
.ps 7
.TS
center box tab(|);
l r r r r r r r r
.
\fBBenchmark\fP|\fBROI inst\fP|\fBLoads\fP|\fBStores\fP|\fBEvents\fP|\fBSpill loads\fP|\fBConf stores\fP|\fBSpill mem\fP|\fBShare\fP
_
GCC|16,026,850|2,957,472|1,955,133|1,020,580|1,041,215|1,020,580|2,061,795|12.8646%
Perlbench|14,690,833|3,491,472|2,035,263|1,049,550|1,074,110|1,049,550|2,123,660|14.4557%
Imagick|117,737,096|20,614,195|8,988,558|2,444,450|2,466,889|2,444,450|4,911,339|4.1714%
Weighted total|148,454,779|27,063,139|12,978,954|4,514,580|4,582,214|4,514,580|9,096,794|6.1277%
.TE
.ps 9
.PP
spill memory instructions = spill load instructions + confirmed spill store instructions
.br
spill instruction share = spill memory instructions / ROI instructions
.PP
The weighted spill share is recomputed from summed populations; it is not an arithmetic mean.
.H1 Candidate and confirmed classification
.ps 8
.TS
center box tab(|);
l r r r r
.
\fBBenchmark\fP|\fBCandidate stores\fP|\fBConfirmed stores\fP|\fBUnconfirmed\fP|\fBRepeated loads\fP
_
GCC|1,103,563|1,020,580|82,983|20,635
Perlbench|1,118,231|1,049,550|68,681|24,560
Imagick|2,453,995|2,444,450|9,545|22,439
Total|4,675,789|4,514,580|161,209|67,634
.TE
.ps 9
.PP
A candidate becomes a confirmed spill store only when its first qualifying later load is observed. Further matching loads of the same store generation are repeated spill loads.
.bp
.H1 Confirmed spill-load cache behavior
.ps 7
.TS
center box tab(|);
l r r r r r r r r
.
\fBBenchmark\fP|\fBL1 hit\fP|\fBL1 miss\fP|\fBL1 hit %\fP|\fBL2 hit\fP|\fBL2 miss\fP|\fBL2 local %\fP|\fBL2/L1 %\fP|\fBDRAM/L1 %\fP
_
GCC|1,041,089|126|99.9879%|124|2|98.4127%|0.0119%|0.0002%
Perlbench|1,074,026|84|99.9922%|84|0|100.0000%|0.0078%|0.0000%
Imagick|2,463,761|3,128|99.8732%|3,102|26|99.1688%|0.1257%|0.0011%
Weighted total|4,578,876|3,338|99.9272%|3,310|28|99.1612%|0.0722%|0.0006%
.TE
.ps 9
.H1 Confirmed spill-store cache behavior
.ps 7
.TS
center box tab(|);
l r r r r r r r r
.
\fBBenchmark\fP|\fBL1 hit\fP|\fBL1 miss\fP|\fBL1 hit %\fP|\fBL2 hit\fP|\fBL2 miss\fP|\fBL2 local %\fP|\fBL2/L1 %\fP|\fBDRAM/L1 %\fP
_
GCC|1,020,064|516|99.9494%|447|69|86.6279%|0.0438%|0.0068%
Perlbench|1,048,011|1,539|99.8534%|1,491|48|96.8811%|0.1421%|0.0046%
Imagick|2,442,175|2,275|99.9069%|1,915|360|84.1758%|0.0783%|0.0147%
Weighted total|4,510,250|4,330|99.9041%|3,853|477|88.9838%|0.0853%|0.0106%
.TE
.ps 9
.H1 Candidate-store cache behavior
.ps 7
.TS
center box tab(|);
l r r r r r r r r
.
\fBBenchmark\fP|\fBL1 hit\fP|\fBL1 miss\fP|\fBL1 hit %\fP|\fBL2 hit\fP|\fBL2 miss\fP|\fBL2 local %\fP|\fBL2/L1 %\fP|\fBDRAM/L1 %\fP
_
GCC|1,102,960|603|99.9454%|508|95|84.2454%|0.0460%|0.0086%
Perlbench|1,116,309|1,922|99.8281%|1,864|58|96.9823%|0.1667%|0.0052%
Imagick|2,450,836|3,159|99.8713%|2,634|525|83.3808%|0.1073%|0.0214%
Weighted total|4,670,105|5,684|99.8784%|5,006|678|88.0718%|0.1071%|0.0145%
.TE
.ps 9
.H1 Denominators and interpretation
\(bu  L1 hit rate = L1 hits / (L1 hits + L1 misses)
.br
\(bu  L2 local hit rate = L2 hits / (L2 hits + L2 misses)
.br
\(bu  L2 rescue / L1 = L2 hits / L1 accesses
.br
\(bu  DRAM / L1 = L2 misses / L1 accesses
.PP
All weighted cache percentages are recomputed from summed hit/miss populations. Split memory instructions can produce multiple cache accesses, so cache rates use access counts rather than instruction counts.
.H1 Reproduction
.nf
\&./spec_spill_runner.sh status test standard gcc perlbench imagick
\&./spec_spill_runner.sh results test standard gcc perlbench imagick
.fi
.PP
Source m5out directories:
.br
\(bu
GCC: /cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks/gcc/m5out_spill_v4/standard/test/gcc/20260908-170008
.br
\(bu
Perlbench: /cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks/perlbench/m5out_spill_v4/standard/test/perlbench_test/20260916-095531
.br
\(bu
Imagick: /cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks/imagick/m5out_spill_v4/standard/test/imagick/20260916-095531
.br
