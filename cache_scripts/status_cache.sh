#!/usr/bin/env bash
# Status of the cache organisation experiment, one script for everything.
#
#   cache_scripts/status_cache.sh            overview of small-2way / fa / dm
#   cache_scripts/status_cache.sh --2way     one N-way configuration (L1D N-way, L2 8-way)
#   cache_scripts/status_cache.sh --8way     N must be a power of two up to 64
#   cache_scripts/status_cache.sh --fa       fully associative L1D and L2
#   cache_scripts/status_cache.sh --dm       direct-mapped L1D and L2
#   cache_scripts/status_cache.sh --info     cache geometry of the three configurations
#
# Refresh every minute:  watch -n 60 cache_scripts/status_cache.sh --2way
exec python3 "$(dirname "$(readlink -f "$0")")/cache_status.py" "$@"
