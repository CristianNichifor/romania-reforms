"""What each commune raises and what it spends, from its own budget execution.

The finance import now lives in `packages/local_finance` so other simulators can reuse the
same Transparenta queries, registry join and classification assumptions. This file remains
as the impozit-teren entry point and compatibility module for neighbouring scripts.

Usage:
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py --year 2024
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "local_finance" / "scripts"))

import import_local_finance as finance  # noqa: E402

API = finance.API
BATCH = finance.BATCH
TRANSFER_PREFIXES = finance.TRANSFER_PREFIXES
SUSPECT_MULTIPLE = finance.SUSPECT_MULTIPLE
YEAR = finance.YEAR
UAT_REGISTRY = finance.UAT_REGISTRY

all_rows = finance.all_rows
batch_query = finance.batch_query
fetch = finance.fetch
post = finance.post
prefer_registry_population = finance.prefer_registry_population
quarantine = finance.quarantine
roster = finance.roster
shared_registry_population = finance.shared_registry_population
shared_registry_sirutas = finance.shared_registry_sirutas
totals = finance.totals
validate_roster_against_registry = finance.validate_roster_against_registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=YEAR)
    args = parser.parse_args()

    uats = roster()
    if len(uats) < 3000:
        raise SystemExit(f"only {len(uats)} UATs came back; refusing to write a partial roster")
    validate_roster_against_registry(uats, shared_registry_sirutas())
    prefer_registry_population(uats, shared_registry_population())

    revenue = fetch(uats, "vn", args.year)
    spending = fetch(uats, "ch", args.year)
    document = finance.build_legacy_budget_document(uats, revenue, spending, args.year)

    out = ROOT / "data" / f"buget-uat-{args.year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{document['summary']['uatsReporting']} UAT-uri, "
        f"{document['summary']['spendingRon'] / 1e9:.2f} mld lei cheltuiți"
    )
    if document["summary"]["medianOwnShare"] is not None:
        print(
            "mediana veniturilor proprii: "
            f"{document['summary']['medianOwnShare'] * 100:.1f}% din buget"
        )
    print(f"Wrote {out.relative_to(ROOT.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
