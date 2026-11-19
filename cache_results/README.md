# Replacement-policy experiment (metric schema 10)

Every run of the input under the small cache sizes (L1D 4 KiB, L1I 32 KiB,
L2 32 KiB, 64 B lines) with L1D 2-, 4- and 8-way (L2 8-way, L1I 2-way) and
six replacement policies, the same policy in L1I, L1D and L2. Started and
monitored with `cache_scripts/policy_campaign.sh`.

| Config suffix | gem5 policy |
|---|---|
| `lru__` | `LRURP` |
| `plru_` | `TreePLRURP` |
| `fifo_` | `FIFORP` |
| `rand_` | `RandomRP` |
| `srrip` | `RRIPRP` (SRRIP: `BRRIPRP` with `btp=100`) |
| `brrip` | `BRRIPRP` (`btp=3`) |

The suffixes are padded to five letters so that every configuration's run
paths have the same length: the path reaches the program's arguments and
moves its stack, which changes the cache behaviour by itself. For the same
reason LRU is run again here instead of reusing the runs in `benchmarks/`.

Layout, one directory per benchmark:

    <benchmark>/<input>/m5out/<config>/<run>_<HHMM_DDMMYYYY>/   gem5 output of one run
    <benchmark>/<input>/report/                                reports of the benchmark
    <benchmark>/m5out_<benchmark>/                             latest_* links of the runner
    _campaign/                                                 plan, campaign.log, queue.log

The program counters (`roi_spill_*`) do not depend on the cache; only the
hit and miss counts change with the policy.
