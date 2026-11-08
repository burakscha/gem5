# Retired with metric schema 10

The eight eviction-attribution tests (`tc4a`-`tc4h`) checked the
`<access>EvictedBy<evictor>` cache statistics, which metric schema 10 removed
(they were not used by any report and had two known faults: an L2 store miss
arrives as `ReadExReq` and was counted as a load, and the eviction ledger was
not scoped to the ROI). The sources are kept here for reference; `run_tests.py`
no longer runs them.
