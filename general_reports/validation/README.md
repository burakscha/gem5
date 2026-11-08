# Validation of the stack classification

Evidence that the SpillDetector's classes match what the compiler actually
generated. Raw logs are large and live, gzipped, under `logs/` (not tracked);
the files here are the readable results and the scripts that produce them.

| File | What it is |
| --- | --- |
| `gcc_dP_ground_truth_2026-10-07.txt` | The schema-7 heuristic against GCC's own spill annotations: per-class breakdown, precision and recall for `probe.c`, mcf and lbm. |
| `schema8_validation_2026-10-08.txt` | The schema-8 detector with its stack PC maps on the same mcf and lbm windows, and why the numbers differ by a handful of events. |
| `probe.c` | Small program with one function per kind of stack traffic (real spills, stack arguments, a memory-resident local, callee saves). |
| `compare_modes.py` | Joins verbose schema-7 detector logs (`SPILL,` lines) with per-PC ground-truth classes. |
| `count_classes.py` | Events and reloads per class from a verbose schema-8 log (`STACK,` lines). |

## Where the ground truth comes from

1. **GCC labels its own spill code.** Re-running a binary's SPEC compile
   commands with `-S -dP` prints, above every assembly instruction, the RTL it
   came from. A memory operand whose attributes name `%sfp` is a slot of the
   register allocator's spill area; a frame-related insn (`insn/f`) is a
   prologue save or epilogue restore. To see it yourself:

   ```bash
   ./scripts/build_stack_pc_map.py --keep /tmp/mcf_dP --out /tmp/mcf.map benchmarks/mcf/mcf_r.riscv
   grep -B3 '%sfp' /tmp/mcf_dP/psimplex.dP.s | head -20
   ```

   e.g. `sd a2,40(sp)` with `[15 %sfp+-32584 S8 A64]`: a spill store.
2. **The labels are tied to runtime PCs.** A local symbol is placed before
   every sp/s0-relative load/store with its class, the objects are linked
   with the original command, and the result must be byte-identical
   (`.text`, `.data`, `.rodata`) to the simulated binary, so the PCs are
   valid for it.
3. **Two simulations of the same window.** One with the heuristic in verbose
   mode (every pair it reports, with store and load PC), one in exact mode
   with only the `%sfp` PCs. `compare_modes.py` joins both with the PC
   classes: precision = share of heuristic pairs that are compiler spills,
   recall = share of compiler spills the heuristic also reports.

Result (2026-10-07): recall 100% everywhere; precision 75% (probe), 39%
(mcf, where 60% of the pairs were callee saves) and 100% (lbm). That is why
schema 8 splits the traffic into spill / csave / other_stack.

## Reproducing the 2026-10-07 tables from the archived logs

```bash
R=logs/validation_raw/2026-10-07_gcc_dP
python3 general_reports/validation/compare_modes.py $R/mcf_pc_classes.txt <(zcat $R/mcf_heur.txt.gz) <(zcat $R/mcf_exact.txt.gz)
```

The archived logs were produced with the schema-7 gem5 build (commit
e0a12aa4e3); the classes in `*_pc_classes.txt` come from the `-dP` rebuilds.
