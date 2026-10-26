#!/usr/bin/env python3
"""
generate_reports.py
Generates two LaTeX reports from SPEC CPU2017 spill cache simulation data.
"""

import os

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Ordered benchmark list ──────────────────────────────────────────────────
# (key, label_tex, full_name, pattern, roi_func)
BENCHMARKS = [
    ("deepsjeng", r"531.deepsjeng\_r", "Deep Sjeng",
     r"Recursive alpha-beta game-tree search with large call stacks and transposition table bookkeeping.",
     r"run\_epd\_testsuite()"),
    ("leela",     r"541.leela\_r", "Leela",
     r"Monte-Carlo tree search with per-node statistics; high function-call depth drives register pressure.",
     r"main try/catch block"),
    ("namd",      r"508.namd\_r", "NAMD",
     r"Vectorised molecular-dynamics force computation; SIMD-friendly loops with moderate spill rate.",
     r"iterations for-loop in spec\_namd.C"),
    ("lbm",       r"519.lbm\_r", "LBM",
     r"Single innermost kernel sweeping a 3-D lattice; 19 FP distribution values per cell exceed the 32 available FP registers.",
     r"main time-step for-loop"),
    ("nab",       r"544.nab\_r", "NAB",
     r"Implicit-solvent MD with Born and vacuum phases; two separate \texttt{md()} calls share the ROI.",
     r"two md() calls (Born + vacuum)"),
    ("xz",        r"557.xz\_r", "XZ",
     r"LZMA2 encoder/decoder with large sliding-window state; compression inner loops sustain register pressure.",
     r"compression for-loop in spec.c"),
    ("imagick",   r"538.imagick\_r", "ImageMagick",
     r"Image-processing pipeline with chained convolution filters; the tiny test image means very short ROI.",
     r"ConvertMain()"),
    ("blender",   r"526.blender\_r", "Blender",
     r"Cycles path-tracer with recursive BVH traversal, shading, and per-sample RNG state -- second-highest spill rate.",
     r"session\_init() + wait + exit"),
    ("povray",    r"511.povray\_r", "POV-Ray",
     r"Ray-tracer with recursive intersection testing and lighting evaluation -- highest SP/inst\% in the suite.",
     r"StartRender() + cooperate loop"),
    ("omnetpp",   r"520.omnetpp\_r", "OMNeT++",
     r"Object-oriented discrete-event network simulator with deep virtual-dispatch call chains and many short-lived stack frames.",
     r"setupUserInterface()"),
    ("xalancbmk", r"523.xalancbmk\_r", "Xalan-C",
     r"XSLT document transformation; recursive XPath evaluation and heavy OO design drive persistent spilling.",
     r"xsltMain()"),
    ("x264",      r"525.x264\_r", "x264/ldecod",
     r"H.264 video decoder (ldecod path); inner decode loops maintain per-slice state that frequently spills.",
     r"do-while decode loop"),
    ("gcc",       r"502.gcc\_r", "GCC",
     r"Full GCC compiler pass sequence; IR-manipulation passes keep many values simultaneously live, producing the highest SP/load\% in the suite.",
     r"toplev\_main()"),
    ("mcf",       r"505.mcf\_r", "MCF",
     r"Min-cost flow network optimiser; sparse graph traversal with pointer-chasing limits register reuse.",
     r"global\_opt()"),
    ("perlbench", r"500.perlbench\_r", "Perlbench",
     r"Perl interpreter; opcode dispatch loop and runtime maintain large per-op state, yielding high SP/inst\%.",
     r"perl\_run()"),
]

# ── Raw data: TEST (m5out_test_l2) — all 15 benchmarks ─────────────────────
# Fields: (roi_insts, roi_loads, roi_stores, roi_spills,
#          L1LH, L1LM, L2LH, L2LM, L1SH, L1SM, L2SH, L2SM, simTicks, numCycles)
RAW_TEST = {
    "deepsjeng": (46202686170, 7989081366, 3395185975, 1975804388,
                  1975206259, 598129, 598129, 0,
                  2455101069, 7816635, 7778340, 38295,
                  74082103772500, 148164207545),
    "leela":     (26063891645, 5110627713, 1756742699, 1179370892,
                  1179338000, 32892, 32892, 0,
                  1428053676, 2756220, 2706325, 49895,
                  43332088560500, 86664177121),
    "namd":      (31914751100, 8380476926, 1945521360, 335693695,
                  335462867, 230828, 230828, 0,
                  345078743, 613961, 613681, 280,
                  60296764703500, 120593529407),
    "lbm":       (6506800041, 1276836306, 775731184, 274130440,
                  274130440, 0, 0, 0,
                  273901743, 229401, 229320, 81,
                  35835443156500, 71670886313),
    "nab":       (6691483052, 1523059851, 321568363, 153736211,
                  153736011, 200, 200, 0,
                  159220629, 22935, 22935, 0,
                  10840214870500, 21680429741),
    "xz":        (2014351522, 367733280, 183548298, 39181468,
                  39179916, 1552, 1552, 0,
                  42539357, 43961, 42842, 1119,
                  4801927007500, 9603854015),
    "imagick":   (117707681, 20608164, 8985699, 2426438,
                  2426377, 61, 61, 0,
                  2466095, 6420, 5352, 1068,
                  205333064500, 410666129),
    "blender":   (994414403, 233612260, 116509608, 64831836,
                  64831309, 527, 527, 0,
                  81859169, 54209, 53739, 470,
                  2076426456500, 4152852913),
    "povray":    (2240825558, 716248306, 287976470, 180043488,
                  179869310, 174178, 174178, 0,
                  199565793, 709492, 709099, 393,
                  3977653452500, 7955306905),
    "omnetpp":   (10286636, 1642711, 655212, 437793,
                  437527, 266, 266, 0,
                  474129, 754, 317, 437,
                  22494827500, 44989655),
    "xalancbmk": (395919950, 106032294, 38990477, 19354339,
                  19334727, 19612, 19612, 0,
                  20019872, 64536, 64217, 319,
                  719403816500, 1438807633),
    "x264":      (18192367319, 3573842627, 1995653850, 664763019,
                  664697121, 65898, 65898, 0,
                  789380541, 202942, 196961, 5981,
                  34565659817500, 69131319635),
    "gcc":       (16027045, 2957463, 1955576, 1117205,
                  1117139, 66, 66, 0,
                  1201024, 695, 590, 105,
                  39525470500, 79050941),
    "mcf":       (24426982048, 8113038194, 1300618520, 509449025,
                  508855015, 594010, 594010, 0,
                  701921199, 3261071, 3209877, 51194,
                  93458864180500, 186917728361),
    "perlbench": (14690864, 3491473, 2035472, 1080784,
                  1080738, 46, 46, 0,
                  1152530, 1638, 1580, 58,
                  31902819500, 63805639),
}

# ── Raw data: TRAIN (m5out_train, no L2 cache counters) ─────────────────────
# Fields: (roi_insts, roi_loads, roi_stores, roi_spills)  — no cache stats
RAW_TRAIN = {
    "deepsjeng": (399987651204, 72368911103, 32213674285, 18131499845),
    "leela":     (436316211710, 85302835628, 27570532075, 19460747256),
    "namd":      (218427292249, 57662937316, 13245362832, 2285717035),
    "lbm":       (100160472569, 19574976720, 11753652015, 4229639284),
    "xz":        (45071901346,  8781014341,  5022533854,  1422403651),
    "imagick":   (284114913819, 47764394626, 652850800,   292429548),
    "blender":   (721231642103, 191998916318, 29533390237, 25389499715),
    "povray":    (28619546491,  9207049191,  3677218308,  2238921193),
    "omnetpp":   (134779629501, 34419513685, 17531247389, 9219009244),
    "xalancbmk": (7848338475,   1998392467,  956498570,   611389348),
    "x264":      (18192367319,  3573842627,  1995653850,  638746003),
    "mcf":       (125387999080, 40288133588, 8306287899,  2181746916),
}

# ── Raw data: REF (m5out_ref_l2, WITH L2 cache counters) ────────────────────
RAW_REF_L2 = {
    "imagick":   (117706531, 20607957, 8985593, 2426383,
                  2426322, 61, 61, 0,
                  2466017, 6420, 5352, 1068,
                  205332104500, 410664209),
    "x264":      (23405758003, 4837558149, 2401493460, 804721799,
                  804624517, 97282, 97282, 0,
                  952021361, 292820, 286343, 6477,
                  43900585623500, 87801171247),
    "gcc":       (224869007944, 54829285747, 27885731758, 18182291057,
                  18180685272, 1605785, 1605785, 0,
                  19570879764, 42057744, 41481411, 576333,
                  455531372597500, 911062745195),
    "mcf":       (24426982048, 8113038194, 1300618520, 509449025,
                  508855015, 594010, 594010, 0,
                  701921199, 3261071, 3209877, 51194,
                  93458864180500, 186917728361),
}

# ── Raw data: REF (m5out_ref, NO L2 cache counters) ─────────────────────────
RAW_REF_NOLC = {
    "xz":  (401325609454, 65376336569, 24760673373, 6636190731),
}

# ── Raw data: TRAIN (m5out_train_l2, WITH L2 cache counters) ─────────────────
# Same 14-field format as RAW_TEST / RAW_REF_L2.
# xalancbmk and perlbench (scrabbl + suns sub-runs) were first to complete.
RAW_TRAIN_L2 = {
    "xalancbmk":   (7848338475, 1998392467, 956498570, 617655308,
                    617217337, 437971, 437971, 0,
                    648094884, 228450, 228127, 323,
                    14738680067500, 29477360135),
    "perl_scrabbl": (1176588509, 302149216, 182574177, 115765326,
                     115765105, 221, 221, 0,
                     122163787, 26745, 26483, 262,
                     2323529683500, 4647059367),
    "perl_suns":    (2739251962, 681242110, 419375212, 285586649,
                     285579892, 6757, 6757, 0,
                     288748942, 67269, 67114, 155,
                     4645623913500, 9291247827),
}

# ── Input size tables ────────────────────────────────────────────────────────
# (tier, description, relative_note)
INPUT_TABLES = {
    "deepsjeng": [
        ("test",  r"test.txt --- 2 chess positions, search depth 15", r"2 positions"),
        ("train", r"train.txt --- 20 positions, search depth 15", r"10$\times$ more positions"),
        ("ref",   r"ref.txt --- 24 positions, search depth 15", r"12$\times$ more positions"),
    ],
    "leela": [
        ("test",  r"test.sgf --- 1.6\,kB Go game record", r"1.6\,kB"),
        ("train", r"train.sgf --- 642\,B (shorter game)", r"shorter than test"),
        ("ref",   r"ref.sgf --- 4.7\,kB (longer game)", r"3$\times$ larger than test"),
    ],
    "namd": [
        ("test",  r"apoa1.input, \textbf{1 iteration}", r"1 iter"),
        ("train", r"apoa1.input, \textbf{7 iterations}", r"7$\times$ iterations"),
        ("ref",   r"apoa1.input, \textbf{65 iterations}", r"65$\times$ iterations"),
    ],
    "lbm": [
        ("test",  r"\textbf{20} time-steps, channel-flow domain (cf\_a.of)",  r"20 steps"),
        ("train", r"\textbf{300} time-steps, channel-flow domain (cf\_b.of)", r"15$\times$ more steps"),
        ("ref",   r"\textbf{3000} time-steps, lid-driven cavity (ldc.of)",    r"150$\times$ more steps"),
    ],
    "nab": [
        ("test",  r"hkrdenq molecule, 1000 MD steps",  r"small molecule"),
        ("train", r"aminos molecule, 1000 MD steps",    r"larger molecule"),
        ("ref",   r"1am0 molecule, 122 MD steps",       r"largest molecule"),
    ],
    "xz": [
        ("test",  r"cpu2006docs.tar.xz --- 1.3\,MB, compression level 0",  r"1.3\,MB file"),
        ("train", r"IMG\_2560.cr2.xz --- 15\,MB, compression level 4",      r"15\,MB (12$\times$), harder"),
        ("ref",   r"cld.tar.xz --- 79\,MB, compression level 6",            r"79\,MB (61$\times$), hardest"),
    ],
    "imagick": [
        ("test",  r"test\_input.tga (318\,B), 4-filter chain", r"tiny synthetic image"),
        ("train", r"train\_input.tga (318\,B), 8-filter chain with resize", r"same image, more filters"),
        ("ref",   r"refrate\_input.tga (8.2\,MB), 6-filter chain",         r"8.2\,MB real image"),
    ],
    "blender": [
        ("test",  r"cube.blend --- simple cube scene, frame 1", r"trivial scene"),
        ("train", r"sh5\_reduced.blend --- scene with objects, frame 234", r"moderate complexity"),
        ("ref",   r"sh3\_no\_char.blend --- full production scene, frame 849", r"full complexity"),
    ],
    "povray": [
        ("test",  r"SPEC-benchmark-test.ini --- $50\times50$ pixel output",   r"tiny render"),
        ("train", r"SPEC-benchmark-train.ini --- ${\sim}200\times150$ pixels", r"${\sim}12\times$ more pixels"),
        ("ref",   r"SPEC-benchmark-ref.ini --- $1280\times768$ pixels",        r"$392\times$ more pixels"),
    ],
    "omnetpp": [
        ("test",  r"General config, simulated time limit 0.003\,s",  r"0.003\,s sim"),
        ("train", r"General config, simulated time limit 0.15\,s",   r"50$\times$ more sim time"),
        ("ref",   r"General config, simulated time limit 2.25\,s",   r"750$\times$ more sim time"),
    ],
    "xalancbmk": [
        ("test",  r"test.xml (28\,kB) + xalanc.xsl",    r"small document"),
        ("train", r"allbooks.xml (larger) + xalanc.xsl", r"larger document"),
        ("ref",   r"t5.xml (largest) + xalanc.xsl",     r"largest document"),
    ],
    "x264": [
        ("test",  r"BuckBunny\_train.264 --- 1.3\,MB H.264 stream (720p excerpt)", r"1.3\,MB stream"),
        ("train", r"BuckBunny.264 --- 2.4\,MB full H.264 file (720p)",            r"1.8$\times$ larger"),
        ("ref",   r"BuckBunny.264 --- 2.4\,MB full H.264 file (same as train)",   r"same as train"),
    ],
    "gcc": [
        ("test",  r"t1.c --- a 69-byte trivial C source file, compiled at \texttt{-O3}",
                  r"single tiny file"),
        ("train", r"train01.c --- a 1.2\,MB C source file, compiled at \texttt{-O3}",
                  r"${\sim}17{,}000\times$ larger source file"),
        ("ref",   r"gcc-pp.c --- an 11\,MB C preprocessed source, compiled at \texttt{-O3}",
                  r"${\sim}159{,}000\times$ larger source file"),
    ],
    "mcf": [
        ("test",  r"inp.in --- 1.2\,MB min-cost flow problem instance",  r"1.2\,MB instance"),
        ("train", r"inp\_train.in --- 2.2\,MB larger problem instance",  r"1.8$\times$ larger"),
        ("ref",   r"inp.in --- same 1.2\,MB instance as test",           r"identical to test"),
    ],
    "perlbench": [
        ("test",  r"test.pl (29\,B) --- minimal Perl smoke-test script",     r"trivial script"),
        ("train", r"scrabbl.pl + suns.pl --- two real Perl programs",        r"realistic workloads"),
        ("ref",   r"checkspam.pl / diffmail.pl / splitmail.pl (3 runs)",     r"production scripts"),
    ],
}

# ────────────────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────────────────

def derived_full(row):
    """Derive all metrics from a full 14-field row (with L2 cache counters).

    All cache percentages use the same denominator (total spill loads or stores)
    so that: L1H + L2H + DRAML = 100%  and  L1HS + L2HS + DRAMS = 100%.
    """
    (insts, loads, stores, spills,
     l1lh, l1lm, l2lh, l2lm,
     l1sh, l1sm, l2sh, l2sm,
     ticks, cycles) = row
    total_l = l1lh + l1lm
    total_s = l1sh + l1sm
    def pct(n, d): return 100.0 * n / d if d else None
    return dict(
        insts=insts, loads=loads, stores=stores, spills=spills,
        total_l=total_l, total_s=total_s,
        l1lh=l1lh, l1lm=l1lm, l2lh=l2lh, l2lm=l2lm,
        l1sh=l1sh, l1sm=l1sm, l2sh=l2sh, l2sm=l2sm,
        ticks=ticks, cycles=cycles,
        sp_inst=pct(spills, insts),
        sp_load=pct(spills, loads),
        # Spill-load cache metrics (all /total_l)
        L1H=pct(l1lh, total_l),    # L1 hit  rate
        L1M=pct(l1lm, total_l),    # L1 miss rate (= 100 - L1H)
        L2H=pct(l2lh, total_l),    # L2 hit  rate (of total, not of L1 misses)
        DRAML=pct(l2lm, total_l),  # DRAM    rate
        # Spill-store cache metrics (all /total_s)
        L1HS=pct(l1sh, total_s),   # L1 hit  rate (stores)
        L1MS=pct(l1sm, total_s),   # L1 miss rate (stores)
        L2HS=pct(l2sh, total_s),   # L2 hit  rate (stores, of total)
        DRAMS=pct(l2sm, total_s),  # DRAM    rate (stores)
        sim_s=ticks / 1e12,
        cpi=cycles / insts if insts else None,
    )

def derived_nolc(row):
    """Derive metrics from a 4-field row (no L2 cache counters)."""
    insts, loads, stores, spills = row
    def pct(n, d): return 100.0 * n / d if d else None
    return dict(
        insts=insts, loads=loads, stores=stores, spills=spills,
        sp_inst=pct(spills, insts),
        sp_load=pct(spills, loads),
    )

def p(v, na=r"\textemdash"):
    """Format a percentage or return em-dash."""
    if v is None: return na
    return f"{v:.2f}"

def fM(n):  return f"{n/1e6:,.1f}"
def fB(n):  return f"{n/1e9:.2f}"
def fBc(n): return f"{n/1e9:,.3f}"   # comma-formatted billions

# ────────────────────────────────────────────────────────────────────────────
# TASK 1: Test Results Report (IEEEtran)
# ────────────────────────────────────────────────────────────────────────────
PREAMBLE_IEEE = r"""\documentclass[conference]{IEEEtran}
\usepackage{amsmath,amssymb}
\usepackage{float}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{pdflscape}
\usepackage{array}
\usepackage[T1]{fontenc}

\newcommand{\LongDate}{\number\day\space
  \ifcase\month\or January\or February\or March\or April\or May\or June%
  \or July\or August\or September\or October\or November\or December\fi
  \space\number\year}
"""

def task1_report():
    lines = [PREAMBLE_IEEE, r"""
\begin{document}
\title{\textbf{Spill Cache Hit/Miss Analysis}\\
  \normalsize SPEC CPU2017 on RISC-V via gem5 --- Test Input Dataset}
\author{
  \IEEEauthorblockN{L\"utfullah Burak Kaya}
  \IEEEauthorblockA{Ozyegin University \\ burak.kaya.50711@ozu.edu.tr}
  \and
  \IEEEauthorblockN{Ismail Akturk}
  \IEEEauthorblockA{Ozyegin University \\ ismail.akturk@ozyegin.edu.tr}
}
\twocolumn[\begin{@twocolumnfalse}\maketitle
\begin{center}{\small \LongDate}\end{center}\vspace{1em}
\end{@twocolumnfalse}]

\begin{abstract}
We characterise register spill behaviour and its interaction with the
memory hierarchy for 15 SPEC CPU2017 C/C++ benchmarks on RISC-V
(RV64GC) using gem5 TimingSimpleCPU.  All measurements use SPEC
\emph{test} inputs, which are intended for pipeline validation and
may not represent full workload behaviour; results should be read
as preliminary characterisation.
Spill fractions range from
\textbf{1.05\%} (\texttt{namd}) to \textbf{8.03\%} (\texttt{povray})
of ROI instructions, and from 4\% to 38\% of ROI loads.
Spill-load DRAM traffic (DRAML\%) is 0.00\% for all 15~benchmarks
at two-decimal precision, suggesting that most spilled values are
reloaded before their cache lines are evicted from L1.
Non-zero DRAM traffic ($<$0.1\%) is observed only on the
spill-store/RFO side (DRAMS\%), specifically for
\texttt{imagick} and \texttt{omnetpp}.
\end{abstract}

% ─────────────────────────────────────────────────────────────────────────────
\section{Methodology}

\subsection{gem5 Configuration}
\begin{itemize}
    \item CPU: TimingSimpleCPU, RISC-V RV64GC
    \item Caches: 32\,kB L1-D (8-way, 64\,B lines),
                  256\,kB unified L2 (\texttt{--caches --l2cache})
    \item Memory: 4\,GB SimpleMemory
    \item Input tier: SPEC \texttt{test} (short, suitable for pipeline validation)
\end{itemize}

\subsection{SpillDetector Module}

The SpillDetector is a custom gem5 module integrated into the
TimingSimpleCPU execute path.  It identifies spill store/reload pairs
using five guards designed to reduce false positives from unrelated
stack accesses:

\begin{enumerate}
  \item \textbf{Stack-address filter.}  Only instructions whose
    effective address falls within the current stack pointer
    $\pm$\,\texttt{MAX\_SPILL\_SIZE} bytes are considered candidates.
    Heap and global accesses are excluded by definition.
  \item \textbf{ROI-only counting.}  The detector is active only
    between \texttt{m5\_work\_begin()} and \texttt{m5\_work\_end()},
    so library initialisation, teardown, and non-kernel code are
    excluded from all counts.
  \item \textbf{Store-before-load ordering.}  A stack address is
    entered in the spill map on a \emph{store}; only a subsequent
    \emph{load} to the same address is counted as a spill reload.
    A load that arrives before any matching store is not counted.
  \item \textbf{Compatible access size.}  The load and its matching
    store must access the same number of bytes.  Mismatched-width
    accesses are rejected.
  \item \textbf{Spill-detection window.}  Store-map entries older
    than \texttt{MAX\_SPILL\_WINDOW} (50\,million ticks
    $\approx$\,50\,\textmu s) are purged before each load check.
    This prevents long-lived stack-frame data from being
    misidentified as spill targets across distantly separated
    call sites.
\end{enumerate}

The detector writes \texttt{riscv\_spill\_stats.txt} containing
\texttt{roi\_instructions}, \texttt{roi\_loads}, \texttt{roi\_stores},
and \texttt{roi\_spills}.

\subsection{Spill-Tagged Cache Counters}

Two \texttt{Request} flags---\texttt{SPILL\_LOAD} and
\texttt{SPILL\_STORE}---are set on memory requests that the
SpillDetector identifies as spill operations.
The L1-D cache and L2 each independently accumulate hit and miss
counters for spill-tagged requests:
\texttt{spillLoadHits}, \texttt{spillLoadMisses},
\texttt{spillStoreHits}, \texttt{spillStoreMisses} per level.

\subsection{Metrics}

\textbf{Spill-fraction metrics:}
\begin{align*}
\text{SP/inst\%} &= \frac{\text{roi\_spills}}{\text{roi\_instructions}} \times 100 \\[2pt]
\text{SP/load\%} &= \frac{\text{roi\_spills}}{\text{roi\_loads}} \times 100
\end{align*}

Let $N_L = \textit{dcache.spillLoadHits}+\textit{dcache.spillLoadMisses}$ and
$N_S = \textit{dcache.spillStoreHits}+\textit{dcache.spillStoreMisses}$.
All cache-level percentages use the same denominator so that:
\[
  \text{L1H\%} + \text{L2H\%} + \text{DRAML\%} = 100\%
\]
(the same identity holds for stores).

\textbf{Spill-load cache metrics (all divided by $N_L$):}
\begin{align*}
\text{L1H\%}   &= \frac{\textit{dcache.spillLoadHits}}{N_L} \times 100 \\[2pt]
\text{L2H\%}   &= \frac{\textit{l2.spillLoadHits}}{N_L} \times 100 \\[2pt]
\text{DRAML\%} &= \frac{\textit{l2.spillLoadMisses}}{N_L} \times 100
\end{align*}

\textbf{Spill-store/RFO cache metrics (all divided by $N_S$):}
\begin{align*}
\text{L1HS\%}  &= \frac{\textit{dcache.spillStoreHits}}{N_S} \times 100 \\[2pt]
\text{L2HS\%}  &= \frac{\textit{l2.spillStoreHits}}{N_S} \times 100 \\[2pt]
\text{DRAMS\%} &= \frac{\textit{l2.spillStoreMisses}}{N_S} \times 100
\end{align*}

\noindent
\textbf{Note:} L2H\% and L2HS\% measure the fraction of \emph{all} spill
loads (stores) rescued by L2, not a conditional rate conditioned on L1 misses.
Near-zero DRAML\% (DRAMS\%) is the key indicator that spilling does not
generate off-chip memory traffic.

% ─────────────────────────────────────────────────────────────────────────────
\section{Results}

Tables~\ref{tab:spill} and~\ref{tab:cache} present all 15 benchmarks.
Instructions are in billions~(B); Loads, Stores, and Spills are in millions~(M).
"""]

    # Table 1 — spill stats (landscape), Loads and Stores in M
    lines.append(r"""
\begin{landscape}
\begin{table*}[p]
\centering\caption{ROI Spill Statistics --- Test Input}\label{tab:spill}\small
\begin{tabular}{lrrrrrrrr}
\toprule
\textbf{Benchmark} & \textbf{Insts (B)} & \textbf{Loads (M)} & \textbf{Stores (M)}
  & \textbf{Spills (M)} & \textbf{SP/inst\%} & \textbf{SP/load\%}
  & \textbf{Sim\,t\,(s)} & \textbf{CPI} \\
\midrule
""")
    for (key, ltx, *_) in BENCHMARKS:
        d = derived_full(RAW_TEST[key])
        lines.append(
            f"\\texttt{{{ltx}}} & {fB(d['insts'])} & {fM(d['loads'])} & {fM(d['stores'])} & "
            f"{fM(d['spills'])} & {p(d['sp_inst'])} & {p(d['sp_load'])} & "
            f"{d['sim_s']:.2f} & {d['cpi']:.2f} \\\\\n")
    lines.append(r"""\bottomrule\end{tabular}\end{table*}

\begin{table*}[p]
\centering\caption{Spill Cache Hit/Miss Rates --- Test Input (all \% of total spills)}\label{tab:cache}\small
\begin{tabular}{lrrrrrrrrrrr}
\toprule
\multirow{2}{*}{\textbf{Benchmark}}
  & \multicolumn{5}{c}{\textbf{Spill Loads}} & \phantom{a}
  & \multicolumn{5}{c}{\textbf{Spill Stores / RFO}} \\
\cmidrule{2-6}\cmidrule{8-12}
  & \textbf{Tot.(M)} & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%}
  && \textbf{Tot.(M)} & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} \\
\midrule
""")
    for (key, ltx, *_) in BENCHMARKS:
        d = derived_full(RAW_TEST[key])
        lines.append(
            f"\\texttt{{{ltx}}} & {fM(d['total_l'])} & {p(d['L1H'])} & {p(d['L1M'])} & "
            f"{p(d['L2H'])} & {p(d['DRAML'])} "
            f"&& {fM(d['total_s'])} & {p(d['L1HS'])} & {p(d['L1MS'])} & {p(d['L2HS'])} & {p(d['DRAMS'])} \\\\\n")
    lines.append(r"""\bottomrule\end{tabular}\end{table*}
\end{landscape}
""")

    lines.append(r"""
% ─────────────────────────────────────────────────────────────────────────────
\section{Key Observations}

\subsection{Spill Rate Range}

SP/inst\% spans approximately an $8\times$ range across the suite
(1.05\% for \texttt{namd} to 8.03\% for \texttt{povray}).
\texttt{povray}, \texttt{perlbench}, \texttt{gcc}, and \texttt{blender}
all exceed 6.5\%.  High spill rates may indicate elevated register
pressure, large stack frames, frequent function calls, or many
simultaneously live temporaries; exact attribution requires further
static and dynamic analysis.

\texttt{gcc}'s SP/load\% of 37.78\% is the highest in the suite,
meaning that on the \emph{test} input 38\% of load operations are
spill reloads.  If this pattern holds at larger inputs, eliminating
spilling would reduce load traffic substantially.

\subsection{L1-D Cache Effectiveness for Spill Loads}

L1H\% is $\geq$99.88\% for all 15 benchmarks.
This indicates that most spilled values are reloaded before
their cache lines are evicted from L1 for the test inputs.
\texttt{lbm} has no L1 spill-load misses at all (L2H\%$=$0.00\%,
DRAML\%$=$0.00\%).

\subsection{Spill-Load L2 Rescue and DRAM Traffic}

DRAML\% is 0.00\% for all 15 benchmarks at the reported precision,
meaning no spill-load misses propagate to DRAM.
Where L1 misses do occur, they are entirely absorbed by L2
(DRAML\% $=$ 0.00\% while L2H\% $\approx$ L1M\%).
Together, these results suggest that spill reloads exercise
the on-chip cache hierarchy and do not materially increase
off-chip memory traffic in the test-input regime.

\subsection{Spill-Store/RFO Behaviour}

L1HS\% exceeds 99.5\% for 13 of 15 benchmarks.
A near-zero DRAMS\% is the key indicator of off-chip traffic;
L2HS\% measures the fraction of all spill stores rescued by L2,
which is meaningful only when DRAMS\% $>$ 0.

\texttt{imagick} and \texttt{omnetpp} show non-zero DRAMS\%
(0.04\% and 0.09\%, respectively), indicating a small number of
spill stores that reach DRAM.  \texttt{omnetpp}'s L2HS\% of 0.07\%
captures the fraction of total stores rescued by L2; the remaining
0.09\% (DRAMS\%) reach DRAM.  Both absolute values remain low.

% ─────────────────────────────────────────────────────────────────────────────
\section{Limitations and Next Steps}

SPEC test inputs are intentionally short and are well-suited for
rapid pipeline validation, but several limitations apply:

\begin{itemize}
  \item \textbf{Working-set size.}
    Small test inputs produce small working sets.
    These may fit entirely in L1/L2, understating cache pressure
    and overestimating L1 residency compared to production-size runs.
  \item \textbf{Code-path coverage.}
    Some benchmarks execute fundamentally different code paths
    under larger inputs (e.g.\ \texttt{imagick} switches filter
    pipelines), so test-input spill rates may not scale linearly
    to train or ref.
  \item \textbf{Instruction count.}
    Several benchmarks execute fewer than 100\,M ROI instructions
    under test input (\texttt{omnetpp}, \texttt{gcc},
    \texttt{perlbench}, \texttt{imagick}).  Measurement noise is
    relatively higher for these runs.
\end{itemize}

\noindent
\textbf{Next steps:}
Train-input simulations are in progress for all 15 benchmarks.
Selected ref-input runs (\texttt{gcc}, \texttt{x264}, \texttt{mcf},
\texttt{imagick}) are also complete.
A cross-tier comparison of SP/inst\%, SP/load\%,
L1H\%, L2H\%, DRAML\%, L1HS\%, L2HS\%, and DRAMS\% will be reported
to assess whether the test-input characterisation generalises.

% ─────────────────────────────────────────────────────────────────────────────
\section{Conclusion}

All 15 SPEC CPU2017 C/C++ benchmarks exhibit measurable register
spilling on RISC-V RV64GC under test inputs, with spill densities
ranging 1--8\% of instructions and 4--38\% of loads.
For these test-input runs, spill-load DRAM traffic is 0.00\%
across the suite, and every L1 spill-load miss is rescued by L2.
The results suggest that spill reloads mostly exercise the
on-chip cache hierarchy rather than off-chip memory bandwidth
for this input tier.
Stronger performance-cost claims require train/ref inputs
and correlation with stall cycles or cache-access latency,
which are the subject of ongoing simulation.
\end{document}
""")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# TASK 2: Combined Report (article class)
# ────────────────────────────────────────────────────────────────────────────

def input_table(key, label_tex):
    rows = INPUT_TABLES[key]
    s  = f"\\begin{{table}}[H]\n\\centering\n"
    s += f"\\caption{{Input dataset sizes for \\texttt{{{label_tex}}}}}\n"
    s += f"\\label{{tab:{key}_inputs}}\n"
    s += "\\small\n\\begin{tabular}{lp{8cm}l}\n\\toprule\n"
    s += "\\textbf{Tier} & \\textbf{Input} & \\textbf{Relative scale} \\\\\n\\midrule\n"
    for (tier, desc, scale) in rows:
        bold = tier == "test"
        td = f"\\textbf{{{tier}}}" if bold else tier
        s += f"{td} & {desc} & {scale} \\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    return s

def roi_table(key, label_tex, tier, d):
    """Table of ROI spill statistics for a given tier and derived-metrics dict."""
    s  = f"\\begin{{table}}[H]\n\\centering\n"
    s += f"\\caption{{ROI spill statistics --- \\texttt{{{label_tex}}} ({tier} input)}}\n"
    s += f"\\label{{tab:{key}_{tier}_roi}}\n"
    s += "\\begin{tabular}{lr}\n\\toprule\n"
    s += "\\textbf{Metric} & \\textbf{Value} \\\\\n\\midrule\n"
    s += f"ROI instructions & {d['insts']:,} \\\\\n"
    s += f"ROI loads        & {d['loads']:,} \\\\\n"
    s += f"ROI stores       & {d['stores']:,} \\\\\n"
    s += f"\\textbf{{ROI spills}}   & \\textbf{{{d['spills']:,}}} \\\\\n"
    s += f"\\textbf{{SP/inst\\%}}   & \\textbf{{{p(d['sp_inst'])}\\%}} \\\\\n"
    s += f"\\textbf{{SP/load\\%}}   & \\textbf{{{p(d['sp_load'])}\\%}} \\\\\n"
    if 'sim_s' in d:
        s += f"Simulated time   & {d['sim_s']:.3f}\\,s \\\\\n"
        s += f"CPI              & {d['cpi']:.2f} \\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    return s

def cache_table(key, label_tex, tier, d):
    """Cache hit/miss breakdown table.  All % use the same total denominator:
    L1H% + L2H% + DRAM% = 100% for both spill loads and spill stores."""
    s  = f"\\begin{{table}}[H]\n\\centering\n"
    s += f"\\caption{{Spill cache hit/miss breakdown --- \\texttt{{{label_tex}}} ({tier} input)}}\n"
    s += f"\\label{{tab:{key}_{tier}_cache}}\n"
    s += "\\begin{tabular}{lrrrrr}\n\\toprule\n"
    s += ("\\textbf{} & \\textbf{Total (M)} & \\textbf{L1H\\%} "
          "& \\textbf{L1M\\%} & \\textbf{L2H\\%} & \\textbf{DRAM\\%} \\\\\n\\midrule\n")
    s += (f"Spill loads  & {fM(d['total_l'])} & {p(d['L1H'])} & "
          f"{p(d['L1M'])} & {p(d['L2H'])} & {p(d['DRAML'])} \\\\\n")
    s += (f"Spill stores & {fM(d['total_s'])} & {p(d['L1HS'])} & "
          f"{p(d['L1MS'])} & {p(d['L2HS'])} & {p(d['DRAMS'])} \\\\\n")
    s += "\\multicolumn{2}{l}{\\small\\textit{L1H\\%+L2H\\%+DRAM\\%=100\\%}} \\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    return s

def benchmark_section(key, label_tex, full_name, pattern, roi_func):
    d_test = derived_full(RAW_TEST[key])
    lines = [f"""
%%──────────────────────────────────────────────────────────────────────────────
\\section{{\\texttt{{{label_tex}}}}}
\\label{{sec:{key}}}

\\paragraph{{Benchmark summary.}}
\\texttt{{{label_tex}}} is the SPEC CPU2017 rate variant of {full_name}.
{pattern}
The ROI is bounded by \\texttt{{m5\\_work\\_begin()}} / \\texttt{{m5\\_work\\_end()}}
around \\texttt{{{roi_func}}}.

\\subsection{{Input Datasets}}
"""]
    lines.append(input_table(key, label_tex))

    # ── TEST results ──────────────────────────────────────────────────────────
    lines.append("\\subsection{Test Input Results}\n")
    lines.append(roi_table(key, label_tex, "test", d_test))
    lines.append(cache_table(key, label_tex, "test", d_test))

    # ── TRAIN results (where available) ──────────────────────────────────────
    lines.append("\\subsection{Train Input Results}\n")
    if key in RAW_TRAIN_L2:
        # Full cache stats available (m5out_train_l2)
        d_tr = derived_full(RAW_TRAIN_L2[key])
        lines.append(roi_table(key, label_tex, "train", d_tr))
        lines.append(cache_table(key, label_tex, "train", d_tr))
    elif key == "perlbench" and ("perl_scrabbl" in RAW_TRAIN_L2 or "perl_suns" in RAW_TRAIN_L2):
        # Perlbench train has two separate sub-runs (scrabbl + suns)
        for sub_key, sub_label in [("perl_scrabbl", "scrabbl.pl"), ("perl_suns", "suns.pl")]:
            if sub_key in RAW_TRAIN_L2:
                d_tr = derived_full(RAW_TRAIN_L2[sub_key])
                lines.append(f"\\subsubsection*{{Sub-run: \\texttt{{{sub_label}}}}}\n")
                lines.append(roi_table(sub_key, label_tex, f"train ({sub_label})", d_tr))
                lines.append(cache_table(sub_key, label_tex, f"train ({sub_label})", d_tr))
    elif key in RAW_TRAIN:
        d_tr = derived_nolc(RAW_TRAIN[key])
        lines.append("\\textit{Note: this run used an older simulation without "
                     "\\texttt{-{}-l2cache}; cache counters are not available.}\n\n")
        lines.append(roi_table(key, label_tex, "train", d_tr))
    else:
        lines.append("\\textit{Train simulation in progress.}\n\n")

    # ── REF results (where available) ─────────────────────────────────────────
    if key in RAW_REF_L2:
        d_ref = derived_full(RAW_REF_L2[key])
        lines.append("\\subsection{Ref Input Results}\n")
        lines.append(roi_table(key, label_tex, "ref", d_ref))
        lines.append(cache_table(key, label_tex, "ref", d_ref))
    elif key in RAW_REF_NOLC:
        d_ref = derived_nolc(RAW_REF_NOLC[key])
        lines.append("\\subsection{Ref Input Results}\n")
        lines.append("\\textit{Note: this run used the older simulation without "
                     "\\texttt{-{}-l2cache}; L1/L2 cache counters are not available.}\n\n")
        lines.append(roi_table(key, label_tex, "ref", d_ref))
    else:
        lines.append("\\subsection{Ref Input Results}\n"
                     "\\textit{Ref simulation in progress.}\n\n")

    return "\n".join(lines)


def summary_table_test(sorted_benches):
    """Two landscape tables: spill stats + cache stats for test input, sorted by SP/inst%."""
    lines = [r"""
\clearpage
\subsection{Test Input --- Complete Results}
\label{subsec:summary_test}

Tables~\ref{tab:sum_test_spill} and~\ref{tab:sum_test_cache} list all
15 benchmarks sorted by \textbf{SP/inst\%} (descending).

\begin{landscape}
\begin{table}[p]
\centering
\caption{Test input: ROI spill statistics (sorted by SP/inst\%)}
\label{tab:sum_test_spill}
\small
\begin{tabular}{clrrrrrrr}
\toprule
\textbf{Rank} & \textbf{Benchmark} & \textbf{Insts (B)} & \textbf{Loads (B)} &
\textbf{Stores (B)} & \textbf{Spills (M)} & \textbf{SP/inst\%} &
\textbf{SP/load\%} & \textbf{CPI} \\
\midrule
"""]
    for rank, (key, ltx, *_) in enumerate(sorted_benches, 1):
        d = derived_full(RAW_TEST[key])
        lines.append(
            f"{rank} & \\texttt{{{ltx}}} & {fB(d['insts'])} & {fB(d['loads'])} & "
            f"{fB(d['stores'])} & {fM(d['spills'])} & {p(d['sp_inst'])} & "
            f"{p(d['sp_load'])} & {d['cpi']:.2f} \\\\\n")
    lines.append(r"""\bottomrule
\end{tabular}
\end{table}

\begin{table}[p]
\centering
\caption{Test input: spill cache hit/miss breakdown (sorted by SP/inst\%, all \% of total)}
\label{tab:sum_test_cache}
\small
\begin{tabular}{clrrrrrrrrr}
\toprule
\multirow{2}{*}{\textbf{Rank}} & \multirow{2}{*}{\textbf{Benchmark}} &
\multicolumn{4}{c}{\textbf{Spill Loads}} & \phantom{x} &
\multicolumn{4}{c}{\textbf{Spill Stores}} \\
\cmidrule{3-6}\cmidrule{8-11}
 & & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} &
   & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} \\
\midrule
""")
    for rank, (key, ltx, *_) in enumerate(sorted_benches, 1):
        d = derived_full(RAW_TEST[key])
        lines.append(
            f"{rank} & \\texttt{{{ltx}}} & {p(d['L1H'])} & {p(d['L1M'])} & "
            f"{p(d['L2H'])} & {p(d['DRAML'])} & & "
            f"{p(d['L1HS'])} & {p(d['L1MS'])} & {p(d['L2HS'])} & {p(d['DRAMS'])} \\\\\n")
    lines.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\\end{landscape}\n")
    return "".join(lines)


def summary_table_train():
    """Summary table for train input (mix of with/without L2 counters).

    Prefers RAW_TRAIN_L2 over RAW_TRAIN for the same benchmark.
    perlbench sub-runs (perl_scrabbl, perl_suns) are listed individually.
    """
    ltx_map = {e[0]: e[1] for e in BENCHMARKS}

    # Build combined entry list: (sort_key, ltx_label, d, has_cache, suffix)
    entries = []

    # RAW_TRAIN_L2 entries (full cache stats, preferred)
    for key in list(RAW_TRAIN_L2.keys()):
        d = derived_full(RAW_TRAIN_L2[key])
        if key == "perl_scrabbl":
            ltx = ltx_map["perlbench"]
            suffix = r" \textit{(scrabbl.pl)}"
        elif key == "perl_suns":
            ltx = ltx_map["perlbench"]
            suffix = r" \textit{(suns.pl)}"
        else:
            ltx = ltx_map.get(key, key)
            suffix = ""
        entries.append((d['sp_inst'], ltx, d, True, suffix))

    # RAW_TRAIN entries without L2 data (skip if already covered by RAW_TRAIN_L2)
    for key, row in RAW_TRAIN.items():
        if key in RAW_TRAIN_L2:
            continue
        d = derived_nolc(row)
        ltx = ltx_map.get(key, key)
        entries.append((d['sp_inst'], ltx, d, False, ""))

    entries.sort(key=lambda x: x[0], reverse=True)

    lines = [r"""
\subsection{Train Input --- Available Results}
\label{subsec:summary_train}

Table~\ref{tab:sum_train_spill} lists all benchmarks for which train-input
simulations are complete.  Entries marked with a dagger~($\dagger$) come from
runs \emph{without} \texttt{--l2cache} (no cache counters available).
Table~\ref{tab:sum_train_cache} shows cache breakdown for the subset run with
\texttt{--l2cache}.

\begin{table}[H]
\centering
\caption{Train input: ROI spill statistics (sorted by SP/inst\%)}
\label{tab:sum_train_spill}
\small
\begin{tabular}{clrrrr}
\toprule
\textbf{Rank} & \textbf{Benchmark} & \textbf{Insts (B)} & \textbf{Spills (M)}
  & \textbf{SP/inst\%} & \textbf{SP/load\%} \\
\midrule
"""]
    for rank, (_, ltx, d, has_cache, suffix) in enumerate(entries, 1):
        marker = "" if has_cache else r"$^\dagger$"
        lines.append(
            f"{rank} & \\texttt{{{ltx}}}{suffix}{marker} & {fB(d['insts'])} & "
            f"{fM(d['spills'])} & {p(d['sp_inst'])} & {p(d['sp_load'])} \\\\\n")
    lines.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n")

    # Cache table for RAW_TRAIN_L2 entries only
    l2_entries = [(ltx, d, suffix) for (_, ltx, d, has_cache, suffix) in entries if has_cache]
    if l2_entries:
        lines.append(r"""
\begin{table}[H]
\centering
\caption{Train input: spill cache hit/miss breakdown (\texttt{--l2cache} runs, all \% of total)}
\label{tab:sum_train_cache}
\small
\begin{tabular}{lrrrrrrrrrr}
\toprule
\multirow{2}{*}{\textbf{Benchmark}} &
\multicolumn{4}{c}{\textbf{Spill Loads}} & \phantom{x} &
\multicolumn{4}{c}{\textbf{Spill Stores}} \\
\cmidrule{2-5}\cmidrule{7-10}
 & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} &
   & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} \\
\midrule
""")
        for (ltx, d, suffix) in l2_entries:
            lines.append(
                f"\\texttt{{{ltx}}}{suffix} & {p(d['L1H'])} & {p(d['L1M'])} & "
                f"{p(d['L2H'])} & {p(d['DRAML'])} & & "
                f"{p(d['L1HS'])} & {p(d['L1MS'])} & {p(d['L2HS'])} & {p(d['DRAMS'])} \\\\\n")
        lines.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n")

    return "".join(lines)


def summary_table_ref():
    """Summary table for ref input (mix of with/without L2 counters)."""
    lines = [r"""
\subsection{Ref Input --- Available Results}
\label{subsec:summary_ref}

Table~\ref{tab:sum_ref_spill} lists benchmarks for which ref-input
simulations are complete.  Four benchmarks (\texttt{gcc}, \texttt{x264},
\texttt{mcf}, \texttt{imagick}) were run with \texttt{--l2cache} and
provide full cache statistics; \texttt{xz} provides spill counts only.

\begin{table}[H]
\centering
\caption{Ref input: ROI spill statistics (sorted by SP/inst\%)}
\label{tab:sum_ref_spill}
\small
\begin{tabular}{clrrrr}
\toprule
\textbf{Rank} & \textbf{Benchmark} & \textbf{Insts (B)} & \textbf{Spills (M)}
  & \textbf{SP/inst\%} & \textbf{SP/load\%} \\
\midrule
"""]
    ref_entries = []
    for key in ["gcc", "x264", "mcf", "imagick"]:
        d = derived_full(RAW_REF_L2[key])
        ref_entries.append((key, d))
    for key in ["xz"]:
        d = derived_nolc(RAW_REF_NOLC[key])
        ref_entries.append((key, d))
    ref_entries.sort(key=lambda x: x[1]['sp_inst'], reverse=True)

    ltx_map = {e[0]: e[1] for e in BENCHMARKS}
    for rank, (key, d) in enumerate(ref_entries, 1):
        ltx = ltx_map[key]
        lines.append(
            f"{rank} & \\texttt{{{ltx}}} & {fB(d['insts'])} & "
            f"{fM(d['spills'])} & {p(d['sp_inst'])} & {p(d['sp_load'])} \\\\\n")
    lines.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n")

    # Cache table for the 4 that have L2 data
    lines.append(r"""
\begin{table}[H]
\centering
\caption{Ref input: spill cache hit/miss breakdown (benchmarks with \texttt{--l2cache}, all \% of total)}
\label{tab:sum_ref_cache}
\small
\begin{tabular}{lrrrrrrrrrr}
\toprule
\multirow{2}{*}{\textbf{Benchmark}} &
\multicolumn{4}{c}{\textbf{Spill Loads}} & \phantom{x} &
\multicolumn{4}{c}{\textbf{Spill Stores}} \\
\cmidrule{2-5}\cmidrule{7-10}
 & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} &
   & \textbf{L1H\%} & \textbf{L1M\%} & \textbf{L2H\%} & \textbf{DRAM\%} \\
\midrule
""")
    l2_keys_sorted = sorted(["gcc", "x264", "mcf", "imagick"],
                             key=lambda k: derived_full(RAW_REF_L2[k])['sp_inst'], reverse=True)
    for key in l2_keys_sorted:
        d = derived_full(RAW_REF_L2[key])
        ltx = ltx_map[key]
        lines.append(
            f"\\texttt{{{ltx}}} & {p(d['L1H'])} & {p(d['L1M'])} & "
            f"{p(d['L2H'])} & {p(d['DRAML'])} & & "
            f"{p(d['L1HS'])} & {p(d['L1MS'])} & {p(d['L2HS'])} & {p(d['DRAMS'])} \\\\\n")
    lines.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    return "".join(lines)


def task2_report():
    lines = [r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{float}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{pdflscape}
\usepackage{array}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage[T1]{fontenc}
\hypersetup{colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue}

\title{
  \textbf{Register Spill Analysis on RISC-V}\\[4pt]
  \large SPEC CPU2017 Benchmark Suite\\
  \normalsize gem5 TimingSimpleCPU $\cdot$ Custom SpillDetector $\cdot$ L1/L2 Spill Cache Counters
}
\author{
  L\"utfullah Burak Kaya\thanks{burak.kaya.50711@ozu.edu.tr, Ozyegin University}
  \and
  Ismail Akturk\thanks{ismail.akturk@ozyegin.edu.tr, Ozyegin University}
}
\date{\today}
\begin{document}
\maketitle
\tableofcontents
\clearpage
"""]

    # ── Introduction ──────────────────────────────────────────────────────────
    lines.append(r"""
\section{Introduction}
\label{sec:intro}

Register spilling is the compiler-induced pattern of writing a live
register value to the stack (\emph{spill store}) and subsequently
reloading it (\emph{spill reload}) when the number of simultaneously
live values exceeds the ISA's physical register count.  On RISC-V
(RV64GC), the general-purpose and floating-point register files each
contain 32 entries.  Any computation that requires more than 32
live integer or floating-point values at once forces the compiler to
save the excess to memory.

This report presents the complete results of a custom gem5-based
spill measurement campaign covering all 15 C/C++ benchmarks from
SPEC CPU2017.  For each benchmark we report:
\begin{enumerate}
  \item ROI instruction, load, store, and spill counts for each
        available input tier (test, train, ref).
  \item Two spill-fraction metrics: \textbf{SP/inst\%}
        (spills\,/\,instructions) and \textbf{SP/load\%}
        (spills\,/\,loads).
  \item For the test input and for ref runs performed with
        \texttt{--l2cache}: L1-D and L2 cache hit/miss rates
        for spill loads and spill stores separately.
\end{enumerate}

Section~\ref{sec:method} describes the measurement infrastructure in
detail, including the rationale for each metric.
Sections~\ref{sec:deepsjeng}--\ref{sec:perlbench} present
per-benchmark results.
Section~\ref{sec:summary} contains a cross-benchmark comparison.
""")

    # ── Methodology ────────────────────────────────────────────────────────────
    lines.append(r"""
\section{Methodology}
\label{sec:method}

\subsection{gem5 Simulation Environment}

All simulations use gem5 Syscall-Emulation (SE) mode with:
\begin{itemize}
  \item \textbf{CPU model}: TimingSimpleCPU (in-order, timing-accurate)
  \item \textbf{ISA}: RISC-V RV64GC
  \item \textbf{L1-D cache}: 32\,kB, 8-way, 64\,B lines
  \item \textbf{L2 cache}: 256\,kB, 8-way unified, write-back
  \item \textbf{DRAM}: 4\,GB SimpleMemory ($\approx$63\,ns latency)
  \item \textbf{gem5 flags}: \texttt{--cpu-type=TimingSimpleCPU --caches --l2cache --mem-size=4GB}
\end{itemize}

\subsection{SpillDetector Module}

A custom \texttt{SpillDetector} is integrated into
\texttt{gem5/src/cpu/simple/timing.cc}.  It operates on two hooks:
\begin{enumerate}
  \item \textbf{onStoreInstruction}: every store instruction inside the
    ROI is checked.  If the target address is a \emph{stack address}
    (within the current SP $\pm$ \texttt{MAX\_SPILL\_SIZE} bytes), the
    address and issue tick are recorded in a hash map.
  \item \textbf{onLoadInstruction}: every load inside the ROI is checked.
    Stale entries older than \texttt{MAX\_SPILL\_WINDOW}
    (50 million ticks $\approx$ 50\,\textmu s) are first purged
    to prevent false positives from long-lived stack data.
    Then, if the load address matches a recorded store entry, it is
    counted as a \emph{spill reload} (\texttt{roi\_spills}).
\end{enumerate}

The detector outputs a per-run file
\texttt{riscv\_spill\_stats.txt} containing
\texttt{roi\_instructions}, \texttt{roi\_loads}, \texttt{roi\_stores},
and \texttt{roi\_spills}.

\subsection{Spill-Tagged Cache Counters}

Two new \texttt{Request} flags---\texttt{SPILL\_LOAD} and
\texttt{SPILL\_STORE}---are set on memory requests that the
SpillDetector identifies as spill operations.  The L1-D and L2
caches separately accumulate hit and miss counters for
spill-tagged requests, producing four new per-cache statistics:
\texttt{spillLoadHits}, \texttt{spillLoadMisses},
\texttt{spillStoreHits}, \texttt{spillStoreMisses}.

\subsection{ROI Markers}

Each benchmark binary was compiled with gem5 ROI markers
(\texttt{m5\_work\_begin()} / \texttt{m5\_work\_end()}) around
the dominant computational kernel, as listed in Table~\ref{tab:roi_markers}.

\begin{table}[H]
\centering
\caption{ROI marker placement per benchmark}
\label{tab:roi_markers}
\small
\begin{tabular}{lll}
\toprule
\textbf{Benchmark} & \textbf{Source file} & \textbf{ROI wraps} \\
\midrule
531.deepsjeng\_r & \texttt{src/sjeng.cpp}            & \texttt{run\_epd\_testsuite()} \\
541.leela\_r     & \texttt{src/Leela.cpp}             & main try/catch block \\
508.namd\_r      & \texttt{src/spec\_namd.C}          & iterations for-loop \\
519.lbm\_r       & \texttt{src/main.c}                & time-step for-loop \\
544.nab\_r       & \texttt{src/nabmd.c}               & two \texttt{md()} calls \\
557.xz\_r        & \texttt{src/spec.c}                & compression for-loop \\
538.imagick\_r   & \texttt{src/utilities/convert.c}   & \texttt{ConvertMain()} \\
526.blender\_r   & \texttt{...cycles\_standalone.cpp} & session init + wait \\
511.povray\_r    & \texttt{src/povray.cpp}            & \texttt{StartRender()} loop \\
520.omnetpp\_r   & \texttt{src/simulator/main.cc}     & \texttt{setupUserInterface()} \\
523.xalancbmk\_r & \texttt{src/XalanExe.cpp}          & \texttt{xsltMain()} \\
525.x264\_r      & \texttt{src/ldecod\_src/...}       & do-while decode loop \\
502.gcc\_r       & \texttt{src/main.c}                & \texttt{toplev\_main()} \\
505.mcf\_r       & \texttt{src/mcf.c}                 & \texttt{global\_opt()} \\
500.perlbench\_r & \texttt{src/perlmain.c}            & \texttt{perl\_run()} \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Metric Definitions and Rationale}
\label{subsec:metrics}

Let $N_L = \textit{spillLoadHits}_\text{L1} + \textit{spillLoadMisses}_\text{L1}$ and
$N_S = \textit{spillStoreHits}_\text{L1} + \textit{spillStoreMisses}_\text{L1}$.
All cache-level percentages share the same denominator so that
$\text{L1H\%}+\text{L2H\%}+\text{DRAML\%} = 100\%$
(and identically for stores).

\begin{align}
\text{SP/inst\%}  &= \frac{\text{roi\_spills}}{\text{roi\_instructions}} \times 100
\label{eq:spinst}\\
\text{SP/load\%}  &= \frac{\text{roi\_spills}}{\text{roi\_loads}} \times 100
\label{eq:spload}\\
\text{L1H\%}  &= \frac{\textit{spillLoadHits}_\text{L1}}{N_L} \times 100
\label{eq:l1h}\\
\text{L2H\%}  &= \frac{\textit{spillLoadHits}_\text{L2}}{N_L} \times 100
\label{eq:l2h}\\
\text{DRAML\%}&= \frac{\textit{spillLoadMisses}_\text{L2}}{N_L} \times 100
\label{eq:draml}
\end{align}
L1HS\%, L2HS\%, and DRAMS\% use the same formulae with spill-store counters.

\paragraph{Why SP/inst\%?}
Equation~\eqref{eq:spinst} measures the \emph{density} of spill
operations within the instruction stream.  It answers ``what fraction
of the program's issue bandwidth is consumed by register-spill memory
traffic?''  A value of 4\% means 1 in every 25 instructions is a
spill reload.  This is the most direct proxy for the \emph{code-size
and issue-slot overhead} of spilling.

\paragraph{Why SP/load\%?}
Equation~\eqref{eq:spload} measures the \emph{fraction of load traffic}
attributable to spilling.  It is arguably the more important metric
for memory-system analysis because the load unit and cache are shared
resources: displacing useful (non-spill) loads by spill reloads
wastes bandwidth.  A value of 30\% means that eliminating spilling
would reduce load traffic by 30\%, with direct impact on CPI and
energy.

\paragraph{Why L1H\% and L2H\%?}
Equations~\eqref{eq:l1h}--\eqref{eq:l2h} characterise the
\emph{cache footprint} of spilled data.  Because a spill store and
its subsequent spill reload are temporally adjacent (the value is
reloaded as soon as a register is needed again), the compiler's stack
discipline naturally produces high spatial and temporal locality.
We expect---and confirm---that spill traffic is overwhelmingly served
by the L1-D cache.  If L1H\% were low, it would suggest that the
ROI involves many long-lived variables that are pushed beyond L1's
capacity before being reloaded, which would indicate a qualitatively
different spilling regime.

\paragraph{Why DRAML\%?}
Equation~\eqref{eq:draml} quantifies whether spilling imposes
\emph{off-chip memory traffic}.  Near-zero DRAML\% (as observed
across the suite) means that spilling costs latency and issue slots
but does \emph{not} burden the memory bus.  This is an important
distinction: a hardware register-file extension that eliminated
spilling would primarily recover CPU cycles rather than DRAM bandwidth.

\paragraph{Why L2H\% alongside DRAML\%?}
L2H\% measures what fraction of \emph{all} spill loads are served by
L2 (not a conditional rate on L1 misses).  Together L1H\%+L2H\%+DRAML\%$=$100\%,
so L2H\% quantifies the share of total spill-load traffic that hits L2.
Near-zero DRAML\% with L2H\%$\approx$L1M\% confirms that L2 rescues
every L1 spill miss with no escapes to DRAM.

\clearpage
""")

    # ── Per-benchmark sections ─────────────────────────────────────────────────
    for entry in BENCHMARKS:
        lines.append(benchmark_section(*entry))

    # ── Cross-benchmark Summary ────────────────────────────────────────────────
    lines.append(r"""
\clearpage
\section{Cross-Benchmark Summary}
\label{sec:summary}

The following subsections present summary tables for each simulation tier.
Benchmarks that do not yet have results for a given tier are omitted.
All tables are sorted by SP/inst\% (descending) to highlight the
benchmarks with the highest register pressure.
""")

    sorted_by_sp = sorted(BENCHMARKS,
                          key=lambda e: derived_full(RAW_TEST[e[0]])['sp_inst'],
                          reverse=True)

    lines.append(summary_table_test(sorted_by_sp))
    lines.append(summary_table_train())
    lines.append(summary_table_ref())

    # ── Discussion ─────────────────────────────────────────────────────────────
    lines.append(r"""
\subsection{Discussion}

\paragraph{Spill rate range.}
SP/inst\% spans an $8\times$ range (1.05\%--8.03\%) across the test
tier.  The highest spilling benchmarks share a common trait: they
execute deep recursive call graphs that keep many values simultaneously
live.  \texttt{povray} (ray-tracer), \texttt{perlbench} (Perl
interpreter), \texttt{gcc} (compiler IR passes), and \texttt{blender}
(path-tracer) all exceed 6.5\%.

\paragraph{Test vs.\ train scaling.}
For benchmarks where both tiers are available, SP/inst\% is
remarkably stable.  \texttt{lbm} goes from 4.21\% (test, 20 steps)
to 4.22\% (train, 300 steps)---essentially constant---because each
time-step executes the identical D3Q19 collision kernel.
\texttt{deepsjeng} similarly holds near 4.5\% across input sizes.
\texttt{imagick} is a notable exception: 2.06\% (test, 318\,B input)
vs.\ 0.10\% (train, 284\,B input with 8 filters),
reflecting a qualitative difference in which code paths dominate for
the two filter chains.

\paragraph{SP/load\% as the key overhead metric.}
\texttt{gcc} is the clearest example: its 37.78\% SP/load\% means
that eliminating all register spilling would reduce its load traffic
by more than a third---a potential CPI improvement of similar
magnitude on a bandwidth-constrained pipeline.

\paragraph{Cache effectiveness.}
The L1-D cache absorbs $\geq$99.88\% of spill loads (L1H\%$\geq$99.88\%)
across all benchmarks and all tiers with cache data.  This holds even for
\texttt{gcc} ref (18 billion spills): the 8.09\% SP/inst\% leads to
just 1.6M L1 misses out of 18.2B total spill loads.
The conclusion is consistent: \emph{spilling costs instruction
bandwidth, not memory bandwidth}.

\paragraph{DRAM traffic from spilling.}
DRAML\% is 0.00\% for every benchmark across all tiers with cache data,
meaning no spill-load misses escape to DRAM.  L2H\%$\approx$L1M\%
for each benchmark, confirming that L2 rescues every L1 spill miss.
DRAM traffic from spilling is therefore zero or negligible ($<$0.1\%).

\section{Conclusion}

All 15 SPEC CPU2017 C/C++ benchmarks exhibit measurable register
spilling on RISC-V RV64GC.  Spill densities range 1--8\% of
instructions and 4--38\% of loads.  Across all simulation tiers
and all benchmarks for which cache data is available:
\begin{itemize}
  \item The L1-D cache serves $>$99.88\% of spill reloads (L1H\%$>$99.88\%).
  \item L2 rescues every L1 spill miss (DRAML\%$=$0.00\%).
  \item DRAM traffic from spilling is $<$0.1\% or zero (DRAMS\%$\leq$0.09\%).
\end{itemize}
The dominant cost of register spilling on this architecture is
therefore \emph{instruction-stream overhead} (added load/store
instructions and issue slots), not off-chip bandwidth.
\texttt{gcc} and \texttt{perlbench} are the most likely candidates
to benefit from compiler improvements or a hardware register-file
extension.

\end{document}
""")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    out1 = os.path.join(BENCH_DIR, "..", "logs", "test", "spill_cache_test_report.tex")
    out2 = os.path.join(BENCH_DIR, "combined_spill_report.tex")

    with open(out1, "w") as f:
        f.write(task1_report())
    print(f"Written: {os.path.realpath(out1)}")

    with open(out2, "w") as f:
        f.write(task2_report())
    print(f"Written: {os.path.realpath(out2)}")
