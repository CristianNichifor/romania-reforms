"""Extract the shared local-finance mart into the web simulator's UAT order.

The administrativ model keeps its own 2024 finance payload because it carries
administration-only spending, which the shared mart deliberately does not. This build step
adds the reusable fiscal indicators that *are* shared: total revenue, own revenue and own
revenue share, aligned to the same positional UAT index as `attributes.bin`.

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


def money(row: dict[str, Any], field: str) -> float:
    value = row.get(field)
    if value is None:
        return 0.0
    return round(float(value), 2)


def build_payload(
    mart: dict[str, Any],
    attributes: dict[str, Any],
    year: int,
    mart_sha256: str,
) -> dict[str, Any]:
    sirutas = [normalise_siruta(value) for value in attributes["siruta"]]
    if len(sirutas) != len(set(sirutas)):
        raise ValueError("attributes.json contains duplicate SIRUTA codes")

    records: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in mart["records"]:
        if int(row["year"]) != year:
            continue
        siruta = normalise_siruta(row["siruta"])
        if siruta in records:
            duplicates.append(siruta)
        records[siruta] = row

    if duplicates:
        listed = ", ".join(sorted(set(duplicates))[:10])
        raise ValueError(f"shared local-finance mart has duplicate {year} SIRUTA rows: {listed}")

    missing = [siruta for siruta in sirutas if siruta not in records]
    if missing:
        listed = ", ".join(missing[:10])
        raise ValueError(f"shared local-finance mart is missing {year} rows for: {listed}")

    revenue = [money(records[siruta], "revenueRon") for siruta in sirutas]
    own_revenue = [money(records[siruta], "ownRevenueRon") for siruta in sirutas]
    own_share = [
        round(own / total, 4) if total > 0 else None
        for own, total in zip(own_revenue, revenue, strict=True)
    ]

    return {
        "id": f"administrativ-local-finance-{year}",
        "sourceMartId": mart["id"],
        "sourceMartSha256": mart_sha256,
        "period": str(year),
        "publisher": mart.get("publisher"),
        "siruta": sirutas,
        "revenueRon": revenue,
        "ownRevenueRon": own_revenue,
        "ownRevenueShare": own_share,
        "summary": {
            "uats": len(sirutas),
            "sourceYearRecords": len(records),
            "excludedSourceRecords": len(records) - len(sirutas),
            "revenueRon": round(sum(revenue), 2),
            "ownRevenueRon": round(sum(own_revenue), 2),
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
        f"{args.out.relative_to(PROJECT_ROOT)} from {payload['sourceMartId']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
