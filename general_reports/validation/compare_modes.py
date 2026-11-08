"""Compare heuristic spill pairs with compiler ground truth.

usage: compare_modes.py <pcmap> <heuristic riscv_spill_stats.txt> <exact riscv_spill_stats.txt>

pcmap: "<hex pc> <CLASS>" per labelled sp/s0 memory instruction.
Both logs must be verbose (one SPILL line per reload).
"""
import collections
import sys

NAMES = {"CALLEE": "CALLEE_SAVE", "OUT": "OUT_ARG"}


def load_pcmap(path):
    out = {}
    for line in open(path):
        pc, cls = line.split()
        out[int(pc, 16)] = NAMES.get(cls, cls)
    return out


def reloads(path):
    """Yield (store_pc, store_inst, load_pc, load_inst) per SPILL line."""
    for line in open(path):
        if line.startswith("SPILL,"):
            f = line.strip().split(",")
            yield int(f[1], 16), int(f[7]), int(f[2], 16), int(f[8])


def main(pcmap_path, heur_path, exact_path):
    pcmap = load_pcmap(pcmap_path)
    cls = lambda pc: pcmap.get(pc, "UNLABELED")

    heur = list(reloads(heur_path))
    exact = list(reloads(exact_path))
    heur_events = {(s, si) for s, si, _, _ in heur}
    exact_events = {(s, si) for s, si, _, _ in exact}

    by_class_ev = collections.Counter()
    by_class_rl = collections.Counter()
    first = set()
    for s, si, l, li in heur:
        key = (cls(s), cls(l))
        by_class_rl[key] += 1
        if (s, si) not in first:
            first.add((s, si))
            by_class_ev[key] += 1

    n_ev, n_rl = len(heur_events), len(heur)
    print(f"heuristic: {n_ev:,} spill events, {n_rl:,} spill reloads")
    print(f"  {'store class':12s} {'reload class':12s} {'events':>11s} {'share':>7s} {'reloads':>11s} {'share':>7s}")
    for key, n in by_class_ev.most_common():
        r = by_class_rl[key]
        print(f"  {key[0]:12s} {key[1]:12s} {n:11,d} {100*n/n_ev:6.1f}% {r:11,d} {100*r/n_rl:6.1f}%")

    true_ev = by_class_ev[("SPILL", "SPILL")]
    true_rl = by_class_rl[("SPILL", "SPILL")]
    print(f"\nprecision (heuristic events that are compiler spills): {100*true_ev/n_ev:.1f}% events, "
          f"{100*true_rl/n_rl:.1f}% reloads")

    # Match by (store_pc, load_pc) multiplicity rather than by instruction
    # count: two runs whose argv differ execute a few more or fewer pre-ROI
    # instructions, which shifts every instruction counter by a constant.
    heur_pairs = collections.Counter((s, l) for s, _, l, _ in heur)
    exact_pairs = collections.Counter((s, l) for s, _, l, _ in exact)
    first_pairs = lambda rows: collections.Counter(
        (s, l) for (s, si, l, li), keep in zip(rows, firsts(rows)) if keep)
    both_rl = sum((exact_pairs & heur_pairs).values())
    both_ev = sum((first_pairs(exact) & first_pairs(heur)).values())
    print(f"exact (compiler spill PCs only): {len(exact_events):,} events, {len(exact):,} reloads")
    print(f"recall (compiler spills the heuristic also reports): "
          f"{100*both_ev/max(1,len(exact_events)):.2f}% events, {100*both_rl/max(1,len(exact)):.2f}% reloads")
    missed = exact_pairs - heur_pairs
    if missed:
        print(f"  missed reloads: {sum(missed.values()):,}; top (store_pc, load_pc):",
              [((hex(s), hex(l)), n) for (s, l), n in missed.most_common(5)])


def firsts(rows):
    seen = set()
    for s, si, _, _ in rows:
        yield (s, si) not in seen
        seen.add((s, si))

if __name__ == "__main__":
    main(*sys.argv[1:4])
