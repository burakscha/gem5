#!/usr/bin/env python3
"""
analyze_spills.py — extract spill hit/miss metrics from gem5 stats.

Usage:
  python3 analyze_spills.py [--csv out.csv] [bench1 bench2 ...]

With no bench args, scans all subdirectories of this script's directory.
Requires new gem5 build (spillLoadHits / spillLoadMisses present in stats.txt).

Outputs a two-part table to stdout; optionally writes a CSV.
"""

import os, re, sys, csv, argparse
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).parent


# ── stat file parsers ─────────────────────────────────────────────────────────

def parse_stats_txt(path):
    """Return {stat_name: numeric_value} keeping only ::total variants."""
    vals = {}
    with open(path) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            key, raw = parts[0], parts[1]
            if '::' in key:
                if not key.endswith('::total'):
                    continue
                key = key.split('::')[0]
            try:
                vals[key] = int(raw)
            except ValueError:
                try:
                    vals[key] = float(raw)
                except ValueError:
                    pass
    return vals


def parse_spill_log(path):
    """Return ROI counters from the # key : value comment header."""
    counters = {}
    pat = re.compile(r'^#\s+([\w]+)\s*:\s*([\d.]+)')
    with open(path) as f:
        for line in f:
            m = pat.match(line)
            if m:
                k, v = m.group(1), m.group(2)
                try:
                    counters[k] = int(v)
                except ValueError:
                    try:
                        counters[k] = float(v)
                    except ValueError:
                        pass
    return counters


# ── m5out discovery ───────────────────────────────────────────────────────────

def find_best_m5out(bench_dir: Path):
    """Return (Path, label) for the best completed new-build run, or (None, None)."""
    candidates = []
    for d in sorted(bench_dir.iterdir()):
        if not d.is_dir() or not d.name.startswith('m5out'):
            continue
        stats = d / 'stats.txt'
        if not stats.exists():
            continue
        with open(stats) as f:
            has_new = 'spillLoadHits' in f.read()
        candidates.append((d.name, d, has_new))

    if not candidates:
        return None, None

    def priority(c):
        name, _, has_new = c
        if not has_new:
            return -1                    # old build — ignore
        if name == 'm5out_new_ref':     return 12   # new build ref
        if name == 'm5out_new_train':   return 11   # new build train
        if name == 'm5out_new_test':    return 10   # new build test
        if name == 'm5out_ref':         return 9
        if name == 'm5out_ref_checkspam': return 8  # perlbench canonical
        if name == 'm5out':             return 7
        if name.startswith('m5out_ref'): return 6
        return 1

    best = max(candidates, key=priority)
    if not best[2]:                    # all old-build
        return None, None
    return best[1], best[0]


# ── metric computation ────────────────────────────────────────────────────────

def compute_metrics(bench_name, m5out: Path, label: str):
    st = parse_stats_txt(m5out / 'stats.txt')
    sp = parse_spill_log(m5out / 'riscv_spill_stats.txt') \
         if (m5out / 'riscv_spill_stats.txt').exists() else {}

    def g(d, *keys, default=None):
        for k in keys:
            if k in d:
                return d[k]
        return default

    roi_spills = g(sp, 'roi_spills')
    roi_loads  = g(sp, 'roi_loads')
    roi_insns  = g(sp, 'roi_instructions')

    sl_hits = g(st, 'system.cpu.dcache.spillLoadHits',   default=0)
    sl_miss = g(st, 'system.cpu.dcache.spillLoadMisses', default=0)
    l2_hits = g(st, 'system.l2.spillLoadHits',           default=0)
    l2_miss = g(st, 'system.l2.spillLoadMisses',         default=0)
    d_miss  = g(st, 'system.cpu.dcache.demandMisses')

    spill_total = sl_hits + sl_miss

    return {
        'bench':             bench_name,
        'm5out':             label,
        # SpillDetector
        'roi_insns':         roi_insns,
        'roi_spills':        roi_spills,
        'roi_loads':         roi_loads,
        'spill_rate_pct':    (roi_spills / roi_loads * 100)
                             if roi_spills is not None and roi_loads else None,
        # Cache counters
        'spill_total':       spill_total,
        'l1d_hits':          sl_hits,
        'l1d_miss':          sl_miss,
        # Derived
        'l1d_hit_rate':      (sl_hits / spill_total) if spill_total else None,
        'miss_of_demand':    (sl_miss / d_miss)       if d_miss      else None,
        'l2_hits':           l2_hits,
        'l2_miss':           l2_miss,
        'l2_hit_rate':       (l2_hits / (l2_hits + l2_miss))
                             if (l2_hits + l2_miss) else None,
        'dram_pct':          (l2_miss / spill_total) if spill_total  else None,
    }


# ── formatting ────────────────────────────────────────────────────────────────

def _f(v, fmt='', pct=False, na='—'):
    if v is None: return na
    if pct:       return f'{v*100:.1f}%'
    if fmt:       return format(v, fmt)
    return f'{v:.4f}' if isinstance(v, float) else str(v)


def print_table(rows):
    SEP = '─' * 112

    print(f'\n{"SPILL DETECTION SUMMARY":^112}')
    print(SEP)
    print(f"{'Bench':<15} {'m5out':<24} {'ROI insns':>14} {'roi_spills':>12}"
          f" {'roi_loads':>14} {'spill_rate':>11}")
    print(SEP)
    for r in rows:
        sr = (_f(r['spill_rate_pct'], '.2f') + '%') if r['spill_rate_pct'] is not None else '—'
        print(f"{r['bench']:<15} {r['m5out']:<24}"
              f" {_f(r['roi_insns'], ','):>14}"
              f" {_f(r['roi_spills'], ','):>12}"
              f" {_f(r['roi_loads'], ','):>14}"
              f" {sr:>11}")

    print(f'\n{"SPILL CACHE HIT/MISS BREAKDOWN":^112}')
    print(SEP)
    print(f"{'Bench':<15} {'total':>9} {'L1Hits':>9} {'L1Miss':>9}"
          f" {'L1HitRate':>10} {'MissOfDmd':>10}"
          f" {'L2Hits':>9} {'L2Miss':>9} {'L2HitRate':>10} {'→DRAM':>8}")
    print(SEP)
    for r in rows:
        print(f"{r['bench']:<15}"
              f" {_f(r['spill_total'], ','):>9}"
              f" {_f(r['l1d_hits'], ','):>9}"
              f" {_f(r['l1d_miss'], ','):>9}"
              f" {_f(r['l1d_hit_rate'], pct=True):>10}"
              f" {_f(r['miss_of_demand'], pct=True):>10}"
              f" {_f(r['l2_hits'], ','):>9}"
              f" {_f(r['l2_miss'], ','):>9}"
              f" {_f(r['l2_hit_rate'], pct=True):>10}"
              f" {_f(r['dram_pct'], pct=True):>8}")

    print()
    print('  total      = l1d_hits + l1d_miss  (should equal roi_spills)')
    print('  L1HitRate  = l1d_hits / total')
    print('  MissOfDmd  = l1d_miss / dcache.demandMisses::total   (spill pressure on L1)')
    print('  L2HitRate  = l2_hits  / (l2_hits + l2_miss)')
    print('  →DRAM      = l2_miss  / total                        (fraction reaching DRAM)')
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('benches', nargs='*', help='Benchmark names (default: all)')
    ap.add_argument('--csv', metavar='FILE', help='Write CSV to FILE')
    args = ap.parse_args()

    if args.benches:
        bench_names = args.benches
    else:
        bench_names = sorted(
            d.name for d in BENCHMARKS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        )

    rows, skipped_old, skipped_missing = [], [], []

    for name in bench_names:
        bench_dir = BENCHMARKS_DIR / name
        if not bench_dir.is_dir():
            print(f'WARNING: {name} not found', file=sys.stderr)
            continue
        m5out, label = find_best_m5out(bench_dir)
        if m5out is None:
            # distinguish: has m5out dirs but old build vs no runs at all
            has_any = any(
                d.is_dir() and d.name.startswith('m5out')
                for d in bench_dir.iterdir()
            )
            (skipped_old if has_any else skipped_missing).append(name)
            continue
        try:
            rows.append(compute_metrics(name, m5out, label))
        except Exception as e:
            print(f'ERROR {name}/{label}: {e}', file=sys.stderr)

    if skipped_missing:
        print(f'\nNot yet run:         {", ".join(skipped_missing)}', file=sys.stderr)
    if skipped_old:
        print(f'Old build (no stats): {", ".join(skipped_old)}', file=sys.stderr)

    if not rows:
        print('\nNo completed new-build runs found. Launch benchmarks first.')
        sys.exit(0)

    print_table(rows)

    if args.csv:
        with open(args.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f'CSV written → {args.csv}')


if __name__ == '__main__':
    main()
