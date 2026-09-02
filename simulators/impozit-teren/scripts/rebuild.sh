#!/usr/bin/env bash
#
# Rebuild every derived dataset, in the one order that is correct.
#
# This exists because the order is not obvious and I have got it wrong three times, each time
# the same way: building a yield from the value files *before* rebuilding the value files, so
# the yield describes a dataset that no longer exists. It never fails. It produces numbers that
# differ in the fourth significant figure, which looks like nothing and is caught only by CI
# refusing the byte diff — a full pipeline run later.
#
# The dependencies, which are the whole content of this file:
#
#   ghid-teren-*        the parsed grids                     (import_ghid.py, per chamber)
#     └── valoare-teren-*   grid × the land register's hectares
#           ├── multiplu-piata        compares the grid with asking prices
#           ├── randament-padure      harvest ÷ the forest VALUE, so it reads valoare-teren
#           └── randament-teren-construit
#                 └── impozit-*       needs every yield, because it carries them for the page
#                       └── renta-*   value × yield, so it needs both of the above
#                             └── valoare-nationala   fitted on every county's value
#
# Two things are deliberately not here. The importers are not run: they hit INS, the ECB, the
# notaries' servers and a legal portal, and a rebuild should not depend on four third parties
# being up. And the map is not built: it needs geopandas and the administrativ pipeline's
# geometry, which a fresh checkout does not have.
#
# Usage:
#   simulators/impozit-teren/scripts/rebuild.sh              # today's exchange rate
#   simulators/impozit-teren/scripts/rebuild.sh --pinned     # the rate the datasets carry
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
cd "$root"

# Every county with both a parsed grid and a land register, discovered rather than listed —
# a hand-kept list is how a county gets built and then silently left out of the next rebuild.
counties=$(
  ls simulators/impozit-teren/data/valoare-teren-*.json 2>/dev/null |
    grep -v -- '-nationala-' |
    sed -E 's#.*/valoare-teren-([a-z]{1,2})-[0-9]{4}\.json#\1#' |
    tr 'a-z' 'A-Z' | sort -u | tr '\n' ' '
)
if [ -z "$counties" ]; then
  echo "no county has a value dataset yet; run import_ghid.py and build_valoare_teren.py first" >&2
  exit 1
fi

pinned=""
[ "${1:-}" = "--pinned" ] && pinned="--reuse-exchange-rate"

step() { printf '\n=== %s\n' "$1"; }
run() { uv run python "simulators/impozit-teren/scripts/$@" >/dev/null; }

step "land value — $(echo "$counties" | wc -w) counties${pinned:+, at the rate they carry}"
for county in $counties; do run build_valoare_teren.py --county "$county" $pinned; done

step "yields, which read the value files above"
run build_multiplu_piata.py
run build_randament_construit.py
run build_randament_padure.py

step "tax and rent, which read the yields"
for county in $counties; do run build_impozit.py --county "$county"; done
for county in $counties; do run build_renta.py --county "$county"; done

step "the national estimate, fitted on all of it"
run build_valoare_nationala.py

printf '\nrebuilt %s counties\n' "$(echo "$counties" | wc -w)"
