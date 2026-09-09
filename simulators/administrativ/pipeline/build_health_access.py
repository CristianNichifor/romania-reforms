"""Extract the shared health-access UAT view into the web simulator's UAT order.

The administrative simulator addresses UATs by the positional index in
`web/public/data/attributes.json`. This build step keeps the shared health view out of the
hot model binary, but exposes the local provider counts in the same order so the detail
panel can sum them for any proposed merged unit.

Usage:
    uv run python -m pipeline.build_health_access
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
DEFAULT_ACCESS = (
    PROJECT_ROOT / "packages/health_access/data/health-service-access-uat-2024-2026.json"
)
DEFAULT_ATTRIBUTES = WEB_DATA_DIR / "attributes.json"
DEFAULT_OUT = WEB_DATA_DIR / "health-access-uat.json"

BUCHAREST = "B"
BUCHAREST_MUNICIPALITY_SIRUTA = "179132"


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


def build_payload(
    access: dict[str, Any],
    attributes: dict[str, Any],
    access_sha256: str,
) -> dict[str, Any]:
    sirutas = [normalise_siruta(value) for value in attributes["siruta"]]
    counties = [str(value) for value in attributes["county"]]
    if len(sirutas) != len(set(sirutas)):
        raise ValueError("attributes.json contains duplicate SIRUTA codes")
    if len(counties) != len(sirutas):
        raise ValueError("attributes.json county array is not aligned to SIRUTA")

    units_by_siruta: dict[str, dict[str, Any]] = {}
    duplicate_sirutas = []
    for unit in access["units"]:
        siruta = normalise_siruta(unit["siruta"])
        if siruta in units_by_siruta:
            duplicate_sirutas.append(siruta)
        units_by_siruta[siruta] = unit
    if duplicate_sirutas:
        listed = ", ".join(sorted(set(duplicate_sirutas))[:10])
        raise ValueError(f"shared health-access view has duplicate SIRUTA rows: {listed}")

    has_local_provider: list[bool | None] = []
    local_provider_count: list[int | None] = []
    local_clinical_bed_providers: list[int | None] = []
    local_clinical_beds: list[float | None] = []
    county_eligible_provider_count: list[int] = []
    county_blocked_provider_count: list[int] = []
    sector_row_excluded: list[bool] = []
    missing = []
    bucharest_municipality = units_by_siruta.get(BUCHAREST_MUNICIPALITY_SIRUTA, {})

    for siruta, county in zip(sirutas, counties, strict=True):
        unit = units_by_siruta.get(siruta)
        if unit is None:
            if county == BUCHAREST:
                has_local_provider.append(None)
                local_provider_count.append(None)
                local_clinical_bed_providers.append(None)
                local_clinical_beds.append(None)
                county_eligible_provider_count.append(
                    int(bucharest_municipality.get("countyEligibleProviderCount", 0))
                )
                county_blocked_provider_count.append(
                    int(bucharest_municipality.get("countyBlockedProviderCount", 0))
                )
                sector_row_excluded.append(True)
                continue
            missing.append(siruta)
            continue

        has_local_provider.append(bool(unit["hasLocalProvider"]))
        local_provider_count.append(int(unit["localProviderCount"]))
        local_clinical_bed_providers.append(int(unit["localClinicalBedProviders"]))
        local_clinical_beds.append(round(float(unit["localClinicalBeds"]), 2))
        county_eligible_provider_count.append(int(unit["countyEligibleProviderCount"]))
        county_blocked_provider_count.append(int(unit["countyBlockedProviderCount"]))
        sector_row_excluded.append(False)

    if missing:
        listed = ", ".join(missing[:10])
        raise ValueError(f"shared health-access view is missing UAT rows for: {listed}")

    provider_rows = [value for value in local_provider_count if value is not None]
    has_provider_rows = [value for value in has_local_provider if value is True]

    return {
        "id": "administrativ-health-access-uat-2024-2026",
        "sourceViewId": access["id"],
        "sourceViewSha256": access_sha256,
        "periodStart": access["periodStart"],
        "periodEnd": access["periodEnd"],
        "publisher": access.get("publisher"),
        "siruta": sirutas,
        "hasLocalProvider": has_local_provider,
        "localProviderCount": local_provider_count,
        "localClinicalBedProviders": local_clinical_bed_providers,
        "localClinicalBeds": local_clinical_beds,
        "countyEligibleProviderCount": county_eligible_provider_count,
        "countyBlockedProviderCount": county_blocked_provider_count,
        "sectorRowExcluded": sector_row_excluded,
        "summary": {
            "uats": len(sirutas),
            "sourceUats": len(access["units"]),
            "uatsWithHealthData": len(provider_rows),
            "uatsWithLocalProvider": len(has_provider_rows),
            "localProviderCount": sum(provider_rows),
            "eligibleProviders": access["summary"]["eligibleProviders"],
            "blockedProviders": access["summary"]["blockedProviders"],
            "namedExclusions": access["summary"]["namedExclusions"],
            "sectorRowsExcluded": sum(1 for value in sector_row_excluded if value),
            "sourceExcludedSectorRows": access["summary"]["excludedSectorRows"],
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
    parser.add_argument("--access", type=Path, default=DEFAULT_ACCESS)
    parser.add_argument("--attributes", type=Path, default=DEFAULT_ATTRIBUTES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.access.exists():
        raise SystemExit(f"Missing {args.access} - build packages/health_access first")
    if not args.attributes.exists():
        raise SystemExit(f"Missing {args.attributes} - run pipeline.export first")

    payload = build_payload(read_json(args.access), read_json(args.attributes), sha256(args.access))
    write_json(args.out, payload)
    print(
        f"{payload['summary']['uats']:,} UATs -> "
        f"{display_path(args.out)} from {payload['sourceViewId']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
