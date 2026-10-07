#!/usr/bin/env bash
# One command: collect every completed SPEC spill run, print the hit/miss and
# spill/fill table, and write results.csv + report.tex + report.pdf.
#
#   ./scripts/spill_report.sh                      # test profile, standard cache
#   ./scripts/spill_report.sh --profile train      # a different workload profile
#   ./scripts/spill_report.sh --cache small        # L1D 4 KiB / L2 32 KiB runs
#   ./scripts/spill_report.sh --run-missing        # launch runs that have no result yet
#   ./scripts/spill_report.sh --no-pdf             # table + CSV + .tex only
#   ./scripts/spill_report.sh --outdir DIR         # write the report somewhere specific

set -uo pipefail

# The repository root is one level above scripts/.
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PROFILE=test
CACHE=standard
RUN_MISSING=0
EXTRA=()

while (( $# > 0 )); do
    case "$1" in
        --profile) PROFILE="${2:?--profile needs a value}"; shift 2 ;;
        --cache)   CACHE="${2:?--cache needs a value}";     shift 2 ;;
        --outdir)  EXTRA+=(--outdir "${2:?--outdir needs a value}"); shift 2 ;;
        --run-missing) RUN_MISSING=1; shift ;;
        --no-pdf)  EXTRA+=(--no-pdf); shift ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) printf 'unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done

if (( RUN_MISSING )); then
    printf 'Launching runs without a completed result (%s/%s)...\n' "$PROFILE" "$CACHE"
    "$ROOT_DIR/scripts/spec_spill_runner.sh" start "$PROFILE" "$CACHE" all
    printf '\nRuns launched in the background. Re-run this script without\n'
    printf -- '--run-missing once ./scripts/spec_spill_runner.sh status %s %s all is clear.\n\n' \
        "$PROFILE" "$CACHE"
fi

exec python3 "$ROOT_DIR/scripts/spill_report.py" \
    --root "$ROOT_DIR" --profile "$PROFILE" --cache "$CACHE" "${EXTRA[@]}"
