"""Extract the shared local-finance mart into the web simulator's UAT order.

The administrativ model keeps its own 2024 finance payload because it carries
administration-only spending, which the shared mart deliberately does not. This build step
adds the reusable fiscal indicators that *are* shared: total revenue, own revenue,
spending pressure and multi-year fiscal trend bases, aligned to the same positional
UAT index as `attributes.bin`.

Usage:
    uv run python -m pipeline.build_local_finance
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.paths import REPO_ROOT as SIMULATOR_ROOT
from pipeline.paths import WEB_DATA_DIR
from pipeline.sources import FINANCE_YEAR

PROJECT_ROOT = SIMULATOR_ROOT.parent.parent
DEFAULT_MART = PROJECT_ROOT / "packages/local_finance/data/local-finance-mart-2023-2025.json"
DEFAULT_ATTRIBUTES = WEB_DATA_DIR / "attributes.json"
DEFAULT_OUT = WEB_DATA_DIR / f"local-finance-{FINANCE_YEAR}.json"
SOURCE_YEARS = (2023, 2024, 2025)
TREND_START_YEAR = 2023
TREND_END_YEAR = 2025


def normalise_siruta(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.lstrip("0") or "0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return path


def money(row: dict[str, Any], field: str) -> float:
    value = row.get(field)
    if value is None:
        return 0.0
    return round(float(value), 2)


def source_records_by_year(
    mart: dict[str, Any],
    years: list[int],
) -> dict[int, dict[str, dict[str, Any]]]:
    wanted_years = set(years)
    records = {source_year: {} for source_year in years}
    duplicates: dict[int, list[str]] = {source_year: [] for source_year in years}

    for row in mart["records"]:
        source_year = int(row["year"])
        if source_year not in wanted_years:
            continue
        siruta = normalise_siruta(row["siruta"])
        if siruta in records[source_year]:
            duplicates[source_year].append(siruta)
        records[source_year][siruta] = row

    for source_year, duplicate_sirutas in duplicates.items():
        if duplicate_sirutas:
            listed = ", ".join(sorted(set(duplicate_sirutas))[:10])
            raise ValueError(
                f"shared local-finance mart has duplicate {source_year} SIRUTA rows: {listed}"
            )

    return records


def optional_money(
    records: dict[str, dict[str, Any]],
    siruta: str,
    field: str,
) -> float | None:
    row = records.get(siruta)
    return money(row, field) if row is not None else None


def build_payload(
    mart: dict[str, Any],
    attributes: dict[str, Any],
    year: int,
    mart_sha256: str,
) -> dict[str, Any]:
    sirutas = [normalise_siruta(value) for value in attributes["siruta"]]
    if len(sirutas) != len(set(sirutas)):
        raise ValueError("attributes.json contains duplicate SIRUTA codes")

    source_years = sorted(set([*SOURCE_YEARS, year]))
    records_by_year = source_records_by_year(mart, source_years)
    records = records_by_year[year]

    missing = [siruta for siruta in sirutas if siruta not in records]
    if missing:
        listed = ", ".join(missing[:10])
        raise ValueError(f"shared local-finance mart is missing {year} rows for: {listed}")

    revenue = [money(records[siruta], "revenueRon") for siruta in sirutas]
    own_revenue = [money(records[siruta], "ownRevenueRon") for siruta in sirutas]
    spending = [money(records[siruta], "spendingRon") for siruta in sirutas]
    personnel_spending = [money(records[siruta], "personnelSpendingRon") for siruta in sirutas]
    start_records = records_by_year[TREND_START_YEAR]
    end_records = records_by_year[TREND_END_YEAR]
    spending_start = [optional_money(start_records, siruta, "spendingRon") for siruta in sirutas]
    spending_end = [optional_money(end_records, siruta, "spendingRon") for siruta in sirutas]
    revenue_start = [optional_money(start_records, siruta, "revenueRon") for siruta in sirutas]
    revenue_end = [optional_money(end_records, siruta, "revenueRon") for siruta in sirutas]
    own_revenue_start = [
        optional_money(start_records, siruta, "ownRevenueRon") for siruta in sirutas
    ]
    own_revenue_end = [optional_money(end_records, siruta, "ownRevenueRon") for siruta in sirutas]
    return {
        "id": f"administrativ-local-finance-{year}",
        "sourceMartId": mart["id"],
        "sourceMartSha256": mart_sha256,
        "period": str(year),
        "sourceYears": list(SOURCE_YEARS),
        "publisher": mart.get("publisher"),
        "siruta": sirutas,
        "revenueRon": revenue,
        "ownRevenueRon": own_revenue,
        "spendingRon": spending,
        "personnelSpendingRon": personnel_spending,
        "spendingRon2023": spending_start,
        "spendingRon2025": spending_end,
        "revenueRon2023": revenue_start,
        "revenueRon2025": revenue_end,
        "ownRevenueRon2023": own_revenue_start,
        "ownRevenueRon2025": own_revenue_end,
        "summary": {
            "uats": len(sirutas),
            "sourceYearRecords": len(records),
            "excludedSourceRecords": len(records) - len(sirutas),
            "revenueRon": round(sum(revenue), 2),
            "ownRevenueRon": round(sum(own_revenue), 2),
            "spendingRon": round(sum(spending), 2),
            "personnelSpendingRon": round(sum(personnel_spending), 2),
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mart", type=Path, default=DEFAULT_MART)
    parser.add_argument("--attributes", type=Path, default=DEFAULT_ATTRIBUTES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--year", type=int, default=FINANCE_YEAR)
    args = parser.parse_args(argv)

    if not args.mart.exists():
        raise SystemExit(f"Missing {args.mart} - run scripts/fetch_release_data.py first")
    if not args.attributes.exists():
        raise SystemExit(f"Missing {args.attributes} - run pipeline.export first")

    payload = build_payload(
        read_json(args.mart),
        read_json(args.attributes),
        args.year,
        sha256(args.mart),
    )
    write_json(args.out, payload)
    print(
        f"{payload['summary']['uats']:,} UATs -> "
        f"{display_path(args.out)} from {payload['sourceMartId']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
