"""What each commune raises and what it spends, from its own budget execution.

The finance import now lives in `packages/local_finance` so other simulators can reuse the
same Transparenta queries, registry join and classification assumptions. This file remains
as the impozit-teren entry point and compatibility module for neighbouring scripts.

Usage:
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py --year 2024
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
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
    parser.add_argument(
        "--mart",
        type=Path,
        help="read an existing packages/local_finance mart instead of the default year file",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="fetch Transparenta again and rebuild the full shared mart before exporting",
    )
    args = parser.parse_args()

    mart_path = args.mart or finance.default_mart_path(args.year)
    if mart_path.exists() and not args.refresh:
        mart = json.loads(mart_path.read_text(encoding="utf-8"))
    else:
        mart, _ = finance.build_finance_documents(
            "full",
            [args.year],
            date.today().isoformat(),
            UAT_REGISTRY,
        )
        finance.write_json(mart_path, mart)

    document = finance.build_legacy_budget_document_from_mart(mart, args.year)

    out = ROOT / "data" / f"buget-uat-{args.year}.json"
    finance.write_json(out, document)
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
