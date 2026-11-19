# Register-spill results, metric schema 10 (Overleaf export)

Exported 2026-11-19 10:30 by `cache_scripts/overleaf_export.py`; run it again to refresh.
Every `.tex` file is a standalone document (pdfLaTeX or XeLaTeX) next to its PDF.

In Overleaf: New Project -> Upload Project -> the zip of this folder. Overleaf
compiles one main document at a time; choose it under Menu -> Main document.

| File | Content |
|---|---|
| `counter_reference_schema10` | every counter, formula and spill condition, with a worked example |
| `overall_test` | test input: program counters and ratios of every run, miss rates per configuration, a two-benchmark comparison |
| `overall_ref_simpoint` | ref input (SimPoint estimates): the same |
| `overall_test_vs_ref` | per benchmark, test against ref: program ratios and miss rates of every configuration |
| `<benchmark>/<benchmark>_<input>` | one benchmark and input: counts, ratios, configurations, miss rates of all five configurations |

Benchmark reports:

| Input | Benchmarks |
|---|---|
| test | 23: cactuBSSN, parest, deepsjeng, leela, namd, lbm, nab, xz, imagick, blender, povray, omnetpp, xalancbmk, x264, gcc, mcf, perlbench, bwaves, exchange2, fotonik3d, roms, wrf, cam4 |
| ref_simpoint | 23: cactuBSSN, parest, deepsjeng, leela, namd, lbm, nab, xz, imagick, blender, povray, omnetpp, xalancbmk, x264, gcc, mcf, perlbench, bwaves, exchange2, fotonik3d, roms, wrf, cam4 |
| train | 4: bwaves, exchange2, fotonik3d, cam4 |

Not yet (a run of the benchmark has not finished in every configuration):

- train: cactuBSSN, parest, deepsjeng, leela, namd, lbm, nab, xz, imagick, blender, povray, omnetpp, xalancbmk, x264, gcc, mcf, perlbench, roms, wrf
