"""Build the shared UAT registry from INS SIRUTA and the Transparenta CUI map.

Usage:
    uv run python packages/uat_registry/scripts/import_uat_registry.py
    uv run python packages/uat_registry/scripts/import_uat_registry.py \
        --siruta-source /tmp/siruta_s1_2026.csv \
        --crosswalk-source /tmp/uat-cui-map.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

YEAR: Final[int] = 2026
TRANSFORM_VERSION: Final[int] = 1
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
SIRUTA_URL: Final[str] = (
    "https://data.gov.ro/dataset/721c9059-5f87-4c79-9854-a1d5c18f58d5/"
    "resource/dac903f0-32b5-489a-89e7-2c80d96cf68d/download/siruta_s1_2026.csv"
)
CROSSWALK_URL: Final[str] = (
    "https://raw.githubusercontent.com/ClaudiuBogdan/hack-for-facts-eb-client/main/"
    "src/assets/data/uat-cui-map.csv"
)

SIRUTA_COLUMNS: Final[set[str]] = {
    "SIRUTA",
    "DENLOC",
    "JUD",
    "SIRSUP",
    "TIP",
    "NIV",
    "NUTS",
    "LAU",
}
CROSSWALK_COLUMNS: Final[set[str]] = {"cui", "natcode"}

COUNTY_CODE_BY_NAME: Final[dict[str, str]] = {
    "ALBA": "AB",
    "ARAD": "AR",
    "ARGES": "AG",
    "BACAU": "BC",
    "BIHOR": "BH",
    "BISTRITA-NASAUD": "BN",
    "BOTOSANI": "BT",
    "BRAILA": "BR",
    "BRASOV": "BV",
    "BUZAU": "BZ",
    "CARAS-SEVERIN": "CS",
    "CALARASI": "CL",
    "CLUJ": "CJ",
    "CONSTANTA": "CT",
    "COVASNA": "CV",
    "DAMBOVITA": "DB",
    "DOLJ": "DJ",
    "GALATI": "GL",
    "GIURGIU": "GR",
    "GORJ": "GJ",
    "HARGHITA": "HR",
    "HUNEDOARA": "HD",
    "IALOMITA": "IL",
    "IASI": "IS",
    "ILFOV": "IF",
    "MARAMURES": "MM",
    "MEHEDINTI": "MH",
    "MURES": "MS",
    "NEAMT": "NT",
    "OLT": "OT",
    "PRAHOVA": "PH",
    "SATU MARE": "SM",
    "SALAJ": "SJ",
    "SIBIU": "SB",
    "SUCEAVA": "SV",
    "TELEORMAN": "TR",
    "TIMIS": "TM",
    "TULCEA": "TL",
    "VASLUI": "VS",
    "VALCEA": "VL",
    "VRANCEA": "VN",
    "BUCURESTI": "B",
}

LEVEL_BY_TYPE: Final[dict[str, str]] = {
    "1": "municipality",
    "2": "town",
    "3": "commune",
    "4": "municipality",
    "6": "sector",
    "9": "municipality",
    "40": "county",
}


def read_source(location: str) -> bytes:
    if re.match(r"https?://", location):
        request = urllib.request.Request(location, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    return Path(location).read_bytes()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(data: bytes, delimiter: str, required: set[str]) -> list[dict[str, str]]:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"CSV missing required columns: {', '.join(sorted(missing))}")
    return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip().upper()


def short_name(name: str, level: str) -> str:
    folded = fold(name)
    for prefix in ("JUDETUL ", "MUNICIPIUL ", "ORAS ", "COMUNA "):
        if folded.startswith(prefix):
            return name[len(prefix) :].strip()
    if level == "sector" and folded.startswith("BUCURESTI SECTORUL "):
        return name.split(" ", 1)[1].strip()
    return name.strip()


def is_registry_row(row: dict[str, str]) -> bool:
    tip = row["TIP"]
    niv = row["NIV"]
    if tip == "40" and niv == "1":
        return True
    if tip in {"1", "2", "3", "4", "9"} and niv == "2":
        return True
    return tip == "6"


def county_metadata(
    rows: list[dict[str, str]], *, require_complete: bool = True
) -> tuple[dict[str, dict], dict[str, dict]]:
    counties_by_jud: dict[str, dict] = {}
    for row in rows:
        if row["TIP"] != "40" or row["NIV"] != "1":
            continue
        name = short_name(row["DENLOC"], "county")
        code = COUNTY_CODE_BY_NAME.get(fold(name))
        if not code:
            raise SystemExit(f"unknown county name in SIRUTA: {row['DENLOC']}")
        counties_by_jud[row["JUD"]] = {
            "siruta": row["SIRUTA"],
            "code": code,
            "name": name,
            "sourceName": row["DENLOC"],
        }
    if require_complete and len(counties_by_jud) != 42:
        raise SystemExit(f"expected 42 county-level rows, found {len(counties_by_jud)}")
    return counties_by_jud, {county["code"]: county for county in counties_by_jud.values()}


def analyse_crosswalk(
    crosswalk_rows: list[dict[str, str]],
    registry_by_siruta: dict[str, dict[str, str]],
    all_siruta_rows: dict[str, dict[str, str]],
    counties_by_code: dict[str, dict],
) -> dict:
    matches_by_siruta: dict[str, list[dict[str, str]]] = defaultdict(list)
    matched_county_rows: list[dict] = []
    unmatched: list[dict] = []
    non_uat: list[dict] = []
    matched_by = Counter()

    for row in crosswalk_rows:
        cui = row["cui"]
        natcode = row["natcode"]
        target_siruta: str | None = None
        match_kind: str | None = None

        if natcode.isdigit():
            if natcode in registry_by_siruta:
                target_siruta = natcode
                match_kind = "siruta"
            elif natcode in all_siruta_rows:
                source = all_siruta_rows[natcode]
                non_uat.append(
                    {
                        "cui": cui,
                        "siruta": natcode,
                        "name": source["DENLOC"],
                        "sirutaType": int(source["TIP"]),
                        "sirutaLevel": int(source["NIV"]),
                    }
                )
            else:
                unmatched.append({"cui": cui, "natcode": natcode, "reason": "siruta-not-found"})
        else:
            county = counties_by_code.get(natcode.upper())
            if county:
                target_siruta = county["siruta"]
                match_kind = "countyCode"
                matched_county_rows.append(
                    {
                        "countyCode": county["code"],
                        "siruta": county["siruta"],
                        "name": county["sourceName"],
                        "cui": cui,
                    }
                )
            else:
                unmatched.append(
                    {"cui": cui, "natcode": natcode, "reason": "county-code-not-found"}
                )

        if target_siruta and match_kind:
            matched_by[match_kind] += 1
            matches_by_siruta[target_siruta].append(
                {"cui": cui, "natcode": natcode, "matchKind": match_kind}
            )

    duplicate_siruta = [
        {"siruta": siruta, "cuis": sorted({match["cui"] for match in matches})}
        for siruta, matches in sorted(matches_by_siruta.items(), key=lambda item: item[0])
        if len({match["cui"] for match in matches}) > 1
    ]

    natcodes_by_cui: dict[str, set[str]] = defaultdict(set)
    for row in crosswalk_rows:
        natcodes_by_cui[row["cui"]].add(row["natcode"])
    duplicate_cui = [
        {"cui": cui, "natcodes": sorted(natcodes)}
        for cui, natcodes in sorted(natcodes_by_cui.items(), key=lambda item: item[0])
        if len(natcodes) > 1
    ]

    return {
        "matchesBySiruta": matches_by_siruta,
        "matchedCountyCodeRows": sorted(
            matched_county_rows, key=lambda row: (row["countyCode"], row["siruta"])
        ),
        "unmatchedCrosswalkRows": sorted(unmatched, key=lambda row: (row["natcode"], row["cui"])),
        "nonUatSirutaRows": sorted(non_uat, key=lambda row: (int(row["siruta"]), row["cui"])),
        "duplicateSiruta": duplicate_siruta,
        "duplicateCui": duplicate_cui,
        "duplicateCuiValues": {row["cui"] for row in duplicate_cui},
        "matchedBy": {
            "siruta": matched_by["siruta"],
            "countyCode": matched_by["countyCode"],
        },
    }


def crosswalk_assignment(
    matches: list[dict[str, str]] | None,
    duplicate_cuis: set[str],
) -> tuple[str | None, str | None, str | None]:
    if not matches:
        return None, None, None
    cuis = {match["cui"] for match in matches}
    if len(cuis) != 1 or next(iter(cuis)) in duplicate_cuis:
        return None, None, None
    match = sorted(matches, key=lambda row: (row["matchKind"], row["natcode"]))[0]
    return match["cui"], "transparenta-uat-cui-map", match["natcode"]


def unit_from_row(
    row: dict[str, str],
    counties_by_jud: dict[str, dict],
    matches: list[dict[str, str]] | None,
    duplicate_cuis: set[str],
) -> dict:
    level = LEVEL_BY_TYPE[row["TIP"]]
    county = counties_by_jud[row["JUD"]]
    cui, cui_source, crosswalk_key = crosswalk_assignment(matches, duplicate_cuis)
    parent = None if level == "county" else row["SIRSUP"]
    return {
        "siruta": row["SIRUTA"],
        "name": row["DENLOC"],
        "shortName": short_name(row["DENLOC"], level),
        "level": level,
        "countyCode": county["code"],
        "countyName": county["name"],
        "countySiruta": county["siruta"],
        "parentSiruta": parent,
        "sirutaType": int(row["TIP"]),
        "sirutaLevel": int(row["NIV"]),
        "lau": row["LAU"] or None,
        "nuts3": row["NUTS"] or None,
        "population": None,
        "cui": cui,
        "cuiSource": cui_source,
        "crosswalkKey": crosswalk_key,
    }


def build_documents(
    siruta_rows: list[dict[str, str]],
    crosswalk_rows: list[dict[str, str]],
    *,
    year: int,
    retrieved_date: str,
    siruta_locator: str,
    crosswalk_locator: str,
    siruta_sha256: str,
    crosswalk_sha256: str,
    require_complete_counties: bool = True,
) -> tuple[dict, dict]:
    siruta_counts = Counter(row["SIRUTA"] for row in siruta_rows)
    duplicates = [siruta for siruta, count in siruta_counts.items() if count > 1]
    if duplicates:
        raise SystemExit(f"duplicate SIRUTA codes in source: {', '.join(sorted(duplicates)[:10])}")

    all_siruta_rows = {row["SIRUTA"]: row for row in siruta_rows}
    registry_source_rows = [row for row in siruta_rows if is_registry_row(row)]
    registry_by_siruta = {row["SIRUTA"]: row for row in registry_source_rows}
    counties_by_jud, counties_by_code = county_metadata(
        siruta_rows, require_complete=require_complete_counties
    )
    crosswalk = analyse_crosswalk(
        crosswalk_rows, registry_by_siruta, all_siruta_rows, counties_by_code
    )

    units = [
        unit_from_row(
            row,
            counties_by_jud,
            crosswalk["matchesBySiruta"].get(row["SIRUTA"]),
            crosswalk["duplicateCuiValues"],
        )
        for row in registry_source_rows
    ]
    units.sort(key=lambda unit: int(unit["siruta"]))

    rows_without_cui = [
        {
            "siruta": unit["siruta"],
            "name": unit["name"],
            "level": unit["level"],
            "countyCode": unit["countyCode"],
            "reason": "no-unambiguous-crosswalk-row",
        }
        for unit in units
        if unit["cui"] is None
    ]
    by_level = Counter(unit["level"] for unit in units)
    matched_rows = sum(crosswalk["matchedBy"].values())
    unmatched_rows = len(crosswalk["unmatchedCrosswalkRows"])
    registry_id = f"uat-registry-{year}"

    limitations = [
        {
            "id": "transparenta-cui-crosswalk-provenance",
            "severity": "material",
            "affects": ["cui"],
            "text": (
                "CUI values are copied from the Transparenta repository crosswalk. The repository "
                "license covers code, but the underlying public-authority identifier provenance "
                "still needs an official source before this becomes a legal identity register."
            ),
        },
        {
            "id": "population-not-imported",
            "severity": "material",
            "affects": ["population"],
            "text": (
                "The registry exposes the population field required by downstream joins, but this "
                "slice does not import an official population source yet. Values are null until an "
                "INS population import is added."
            ),
        },
        {
            "id": "bucharest-county-placeholder-without-cui",
            "severity": "note",
            "affects": ["cui", "countyCode"],
            "text": (
                "INS carries Municipiul Bucuresti both as a county-level row and as a municipality "
                "row. The Transparenta CUI map resolves the municipality and sectors; the "
                "county-level placeholder has no separate CUI in this crosswalk."
            ),
        },
    ]

    registry = {
        "$schema": "../schema/uat-registry.schema.json",
        "id": registry_id,
        "title": f"Registrul SIRUTA pentru UAT-uri si CUI-uri, {year}",
        "publisher": "Institutul National de Statistica",
        "period": str(year),
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": f"data-gov-ro-siruta-{year}",
            "locator": f"{siruta_locator}; retrieved {retrieved_date}; sha256 {siruta_sha256}",
            "confidence": "derived",
            "note": (
                "Rows are selected from INS SIRUTA by TIP/NIV: counties, municipalities, towns, "
                "communes, Bucharest municipality and Bucharest sectors."
            ),
        },
        "crosswalkProvenance": {
            "source": "transparenta-uat-crosswalk",
            "locator": (
                f"{crosswalk_locator}; retrieved {retrieved_date}; "
                f"sha256 {crosswalk_sha256}"
            ),
            "confidence": "derived",
            "note": (
                "Numeric natcode values are matched to SIRUTA. Alphabetic natcode values are "
                "matched to countyCode and used for county council CUI rows."
            ),
        },
        "sourceHashes": {
            "sirutaSha256": siruta_sha256,
            "crosswalkSha256": crosswalk_sha256,
        },
        "transform": {
            "script": "packages/uat_registry/scripts/import_uat_registry.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": {
            "registryRows": len(units),
            "localAuthorityRows": len(units) - by_level["county"],
            "countyRows": by_level["county"],
            "withCui": sum(1 for unit in units if unit["cui"] is not None),
            "withoutCui": len(rows_without_cui),
            "withPopulation": sum(1 for unit in units if unit["population"] is not None),
            "crosswalkRows": len(crosswalk_rows),
            "crosswalkMatched": matched_rows,
            "crosswalkUnmatched": unmatched_rows,
            "crosswalkMatchedBy": crosswalk["matchedBy"],
            "byLevel": dict(sorted(by_level.items())),
        },
        "units": units,
        "limitations": limitations,
    }

    report = {
        "$schema": "../schema/uat-registry-report.schema.json",
        "id": f"uat-registry-mismatch-report-{year}",
        "title": f"Raport de potrivire SIRUTA/CUI, {year}",
        "period": str(year),
        "registryId": registry_id,
        "retrievedDate": retrieved_date,
        "summary": {
            "crosswalkRows": len(crosswalk_rows),
            "matchedRows": matched_rows,
            "unmatchedRows": unmatched_rows,
            "nonUatSirutaRows": len(crosswalk["nonUatSirutaRows"]),
            "duplicateSiruta": len(crosswalk["duplicateSiruta"]),
            "duplicateCui": len(crosswalk["duplicateCui"]),
            "registryRowsWithoutCui": len(rows_without_cui),
        },
        "matchedCountyCodeRows": crosswalk["matchedCountyCodeRows"],
        "unmatchedCrosswalkRows": crosswalk["unmatchedCrosswalkRows"],
        "nonUatSirutaRows": crosswalk["nonUatSirutaRows"],
        "duplicateSiruta": crosswalk["duplicateSiruta"],
        "duplicateCui": crosswalk["duplicateCui"],
        "registryRowsWithoutCui": rows_without_cui,
        "limitations": limitations,
    }
    return registry, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--siruta-source", default=SIRUTA_URL)
    parser.add_argument("--crosswalk-source", default=CROSSWALK_URL)
    parser.add_argument("--siruta-locator", default=SIRUTA_URL)
    parser.add_argument("--crosswalk-locator", default=CROSSWALK_URL)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    parser.add_argument("--out-dir", type=Path, default=PACKAGE_ROOT / "data")
    args = parser.parse_args()

    try:
        datetime.strptime(args.retrieved_date, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SystemExit("--retrieved-date must be YYYY-MM-DD") from exc

    siruta_bytes = read_source(args.siruta_source)
    crosswalk_bytes = read_source(args.crosswalk_source)
    siruta_rows = read_csv(siruta_bytes, ";", SIRUTA_COLUMNS)
    crosswalk_rows = read_csv(crosswalk_bytes, ",", CROSSWALK_COLUMNS)
    registry, report = build_documents(
        siruta_rows,
        crosswalk_rows,
        year=args.year,
        retrieved_date=args.retrieved_date,
        siruta_locator=args.siruta_locator,
        crosswalk_locator=args.crosswalk_locator,
        siruta_sha256=sha256(siruta_bytes),
        crosswalk_sha256=sha256(crosswalk_bytes),
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    registry_path = args.out_dir / f"uat-registry-{args.year}.json"
    report_path = args.out_dir / f"uat-registry-mismatch-report-{args.year}.json"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"{registry['summary']['registryRows']} registry rows, "
        f"{registry['summary']['withCui']} with CUI, "
        f"{report['summary']['registryRowsWithoutCui']} without CUI"
    )
    print(f"Wrote {registry_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
