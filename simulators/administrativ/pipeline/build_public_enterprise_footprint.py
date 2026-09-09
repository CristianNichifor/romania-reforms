"""Align the shared public-enterprise aggregate to the web simulator's UAT order.

The shared package keeps authority/UAT/county aggregates. The browser wants positional arrays
in the same SIRUTA order as attributes.json, so merged units can be summed cheaply and without
loading company rows.

Usage:
    uv run python -m pipeline.build_public_enterprise_footprint
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.paths import REPO_ROOT as SIMULATOR_ROOT
from pipeline.paths import WEB_DATA_DIR

PROJECT_ROOT = SIMULATOR_ROOT.parent.parent
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "packages"
    / "public_enterprise_governance"
    / "data"
    / "public-enterprise-administrative-footprint-2024-2026.json"
)
DEFAULT_ATTRIBUTES = WEB_DATA_DIR / "attributes.json"
DEFAULT_OUT = WEB_DATA_DIR / "public-enterprise-footprint.json"

NUMERIC_FIELDS = (
    "authorityCount",
    "companyCount",
    "activeCompanyCount",
    "companiesWithFinancials",
    "lossMakingCompanyCount",
    "employeeCount",
    "revenueRon",
    "profitLossRon",
    "debtRon",
    "subsidiesRon",
)


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


def number(row: dict[str, Any], field: str) -> float:
    value = row.get(field)
    if value is None:
        return 0.0
    return round(float(value), 2)


def source_rows_by_siruta(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in source.get("uats", []):
        siruta = normalise_siruta(row["siruta"])
        if siruta in rows:
            duplicates.append(siruta)
        rows[siruta] = row
    if duplicates:
        listed = ", ".join(sorted(set(duplicates))[:10])
        raise ValueError(f"public-enterprise aggregate has duplicate UAT SIRUTA rows: {listed}")
    return rows


def build_payload(
    source: dict[str, Any],
    attributes: dict[str, Any],
    source_sha256: str,
) -> dict[str, Any]:
    sirutas = [normalise_siruta(value) for value in attributes["siruta"]]
    if len(sirutas) != len(set(sirutas)):
        raise ValueError("attributes.json contains duplicate SIRUTA codes")

    source_rows = source_rows_by_siruta(source)
    attribute_sirutas = set(sirutas)
    excluded_source_sirutas = sorted(
        siruta for siruta in source_rows if siruta not in attribute_sirutas
    )

    series: dict[str, list[float]] = {field: [] for field in NUMERIC_FIELDS}
    matched_source_uats = 0
    for siruta in sirutas:
        row = source_rows.get(siruta)
        if row is not None:
            matched_source_uats += 1
        for field in NUMERIC_FIELDS:
            series[field].append(number(row or {}, field))

    return {
        "id": "administrativ-public-enterprise-footprint-2024-2026",
        "sourceViewId": source["id"],
        "sourceViewSha256": source_sha256,
        "periodStart": source["periodStart"],
        "periodEnd": source["periodEnd"],
        "publisher": source["publisher"],
        "license": source["license"],
        "attribution": source["attribution"],
        "siruta": sirutas,
        **series,
        "summary": {
            "uats": len(sirutas),
            "sourceUats": len(source_rows),
            "matchedSourceUats": matched_source_uats,
            "excludedSourceUats": len(excluded_source_sirutas),
            "excludedSourceSiruta": excluded_source_sirutas,
            "companyCount": int(sum(series["companyCount"])),
            "activeCompanyCount": int(sum(series["activeCompanyCount"])),
            "lossMakingCompanyCount": int(sum(series["lossMakingCompanyCount"])),
            "companiesWithFinancials": int(sum(series["companiesWithFinancials"])),
            "employeeCount": int(sum(series["employeeCount"])),
            "revenueRon": round(sum(series["revenueRon"]), 2),
            "profitLossRon": round(sum(series["profitLossRon"]), 2),
            "debtRon": round(sum(series["debtRon"]), 2),
            "subsidiesRon": round(sum(series["subsidiesRon"]), 2),
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
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--attributes", type=Path, default=DEFAULT_ATTRIBUTES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.source.exists():
        raise SystemExit(
            f"Missing {args.source} - build the public-enterprise package aggregate first"
        )
    if not args.attributes.exists():
        raise SystemExit(f"Missing {args.attributes} - run pipeline.export first")

    payload = build_payload(read_json(args.source), read_json(args.attributes), sha256(args.source))
    write_json(args.out, payload)
    print(
        f"{payload['summary']['matchedSourceUats']:,} source UATs -> "
        f"{display_path(args.out)} from {payload['sourceViewId']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
