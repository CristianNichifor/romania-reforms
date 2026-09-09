"""Build the shared local finance mart from Transparenta budget execution.

The first committed slice was deliberately small: ten UATs over 2023-2025, enough to lock
down the data shape, classification choices and validation report. The same importer now
builds the full 2023-2025 mart published as a release asset and can emit the
`simulators/impozit-teren` compatibility export from it.

Usage:
    uv run python packages/local_finance/scripts/import_local_finance.py \
        --data-gov-2024-workbook /tmp/local-finance/situatia-veniturilor-cheltuielilor-2024.xlsx
    uv run python packages/local_finance/scripts/import_local_finance.py \
        --scope full --years 2023 2024 2025
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py \
        --out simulators/impozit-teren/app/public/data/buget-uat-2025.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
API: Final[str] = "https://api.transparenta.eu/graphql"
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
YEAR: Final[int] = 2025
DEFAULT_YEARS: Final[tuple[int, ...]] = (2023, 2024, 2025)
SCOPES: Final[tuple[str, ...]] = ("sample", "full")
UAT_REGISTRY: Final[Path] = (
    REPO_ROOT / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"
)
TRANSFORM_VERSION: Final[str] = "2026-09-08"

DATA_GOV_2024_URL: Final[str] = (
    "https://data.gov.ro/dataset/c0d25ff7-27d5-4c31-9809-540f77b20180/resource/"
    "aac89795-56f0-41ee-a631-26695f73c5d6/download/"
    "situaia-veniturilor-i-cheltuielilor-2024.xlsx"
)
DATA_GOV_ARREARS_DATASET_URL: Final[str] = "https://data.gov.ro/dataset/arierate"
DATA_GOV_ARREARS_PACKAGE_URL: Final[str] = (
    "https://data.gov.ro/api/3/action/package_show?id=arierate"
)

# Revenue that arrives from above rather than being raised locally. Chapter prefixes of the
# revenue classification: shares of income tax, sums broken out of VAT, subsidies from other
# budgets, and European money. Everything else is treated as own revenue.
TRANSFER_PREFIXES: Final[tuple[str, ...]] = (
    "04.",
    "11.",
    "42.",
    "43.",
    "44.",
    "45.",
    "46.",
    "48.",
)
PERSONNEL_ECONOMIC_PREFIXES: Final[tuple[str, ...]] = ("10",)
CAPITAL_ECONOMIC_PREFIXES: Final[tuple[str, ...]] = ("70", "71", "72")
SUSPECT_MULTIPLE: Final[int] = 20

# How many UATs are asked for in one HTTP request. The endpoint has no group-by for
# line-items, so GraphQL aliases let many authorities share a request.
BATCH: Final[int] = 40
MONTH_BY_NAME: Final[dict[str, int]] = {
    "IANUARIE": 1,
    "FEBRUARIE": 2,
    "MARTIE": 3,
    "APRILIE": 4,
    "MAI": 5,
    "IUNIE": 6,
    "IULIE": 7,
    "AUGUST": 8,
    "SEPTEMBRIE": 9,
    "OCTOMBRIE": 10,
    "NOIEMBRIE": 11,
    "DECEMBRIE": 12,
}

SAMPLE_UATS: Final[tuple[tuple[str, str], ...]] = (
    ("1017", "county-seat"),
    ("2309", "rural-commune"),
    ("1071", "rural-commune"),
    ("100004", "rural-commune"),
    ("97090", "rural-commune"),
    ("96478", "rural-commune"),
    ("127144", "rural-commune"),
    ("128711", "town"),
    ("146904", "rural-commune"),
    ("179150", "bucharest-sector"),
)

ROSTER = """
query Roster($limit: Int!, $offset: Int!) {
  entities(limit: $limit, offset: $offset, filter: {is_uat: true}) {
    nodes {
      name
      uat_id
      uat { siruta_code county_code population }
    }
    pageInfo { totalCount hasNextPage }
  }
}
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_json(document: object) -> str:
    data = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(data)


def read_source_bytes(location: str | Path) -> bytes:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    return Path(text).read_bytes()


def post(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json", "User-Agent": UA}
    )
    document = json.loads(urllib.request.urlopen(request, timeout=180).read())
    if document.get("errors"):
        raise SystemExit(f"transparenta.eu: {document['errors'][0]['message']}")
    return document["data"]


def roster() -> list[dict]:
    """Every reporting UAT, with the SIRUTA code that joins it to the shared registry."""
    out: list[dict] = []
    offset = 0
    while True:
        page = post(ROSTER, {"limit": 100, "offset": offset})["entities"]
        received = len(page["nodes"])
        if received == 0:
            break
        for node in page["nodes"]:
            uat = node.get("uat") or {}
            if not uat.get("siruta_code"):
                continue
            out.append(
                {
                    "uatId": node["uat_id"],
                    "siruta": str(uat["siruta_code"]),
                    "county": uat.get("county_code"),
                    "name": node["name"],
                    "population": uat.get("population"),
                }
            )
        offset += received
        if not page["pageInfo"]["hasNextPage"]:
            break
        print(f"  roster: {len(out)} of {page['pageInfo']['totalCount']}", file=sys.stderr)
    return out


def read_registry(path: Path = UAT_REGISTRY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def shared_registry_sirutas(path: Path = UAT_REGISTRY) -> set[str]:
    document = read_registry(path)
    return {str(unit["siruta"]) for unit in document["units"]}


def shared_registry_population(path: Path = UAT_REGISTRY) -> dict[str, int]:
    document = read_registry(path)
    return {
        str(unit["siruta"]): unit["population"]
        for unit in document["units"]
        if unit["population"] is not None
    }


def fold(text: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip().upper()


def arrears_join_key(text: object) -> str:
    folded = fold(text)
    folded = folded.replace("MUNICIPIUL BUCURESTI SECTORUL", "SECTORUL")
    folded = folded.replace("BUCURESTI SECTORUL", "SECTORUL")
    folded = re.sub(r"\b(SECTORUL|SECTOR)\s+([1-6])\b", r"SECTOR \2", folded)
    for prefix in (
        "CONSILIUL JUDETEAN AL ",
        "CONSILIUL JUDETEAN ",
        "JUDETUL ",
        "MUNICIPIUL ",
        "ORASUL ",
        "ORAS ",
        "COMUNA ",
    ):
        if folded.startswith(prefix):
            folded = folded[len(prefix) :]
            break
    folded = re.sub(r"\bDR\W*TR\b", "DROBETA TURNU", folded)
    folded = re.sub(r"\bTG\b", "TARGU", folded)
    for old, new in (
        ("SIRBI", "SARBI"),
        ("SIMBURESTI", "SAMBURESTI"),
        ("GIRCENI", "GARCENI"),
        ("BIRLAD", "BARLAD"),
    ):
        folded = folded.replace(old, new)
    folded = re.sub(r"[^A-Z0-9]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def is_county_council_name(name: object) -> bool:
    folded = fold(name)
    return "CONSILIUL" in folded and "JUDETEAN" in folded


def registry_arrears_indexes(
    registry_document: dict,
) -> tuple[dict[tuple[str, str], list[dict]], dict[str, str]]:
    unit_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    county_by_key: dict[str, str] = {}
    seen_unit_keys: set[tuple[str, str, str]] = set()
    for unit in registry_document["units"]:
        county_code = unit["countyCode"]
        if unit["level"] == "county":
            for name in (unit["shortName"], unit["countyName"], unit["name"]):
                county_by_key[arrears_join_key(name)] = county_code
            continue
        for name in {unit["name"], unit["shortName"]}:
            key = arrears_join_key(name)
            unique_key = (county_code, key, unit["siruta"])
            if key and unique_key not in seen_unit_keys:
                unit_index[(county_code, key)].append(unit)
                seen_unit_keys.add(unique_key)
    return unit_index, county_by_key


def arrears_candidates(
    unit_index: dict[tuple[str, str], list[dict]], county_code: str, key: str
) -> list[dict]:
    candidates = unit_index.get((county_code, key), [])
    if candidates:
        return candidates

    prefix_matches = []
    for (index_county_code, index_key), units in unit_index.items():
        if index_county_code == county_code and index_key.startswith(f"{key} "):
            prefix_matches.extend(units)
    by_siruta = {unit["siruta"]: unit for unit in prefix_matches}
    return list(by_siruta.values())


def date_from_parts(day: str, month: str, year: str) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def parse_arrears_snapshot_date(*texts: object) -> str | None:
    joined = " ".join(str(text or "") for text in texts)
    folded = fold(joined)
    for match in re.finditer(r"\b([0-3]?\d)[.\-/]([01]?\d)[.\-/]((?:19|20)\d{2})\b", folded):
        parsed = date_from_parts(match.group(1), match.group(2), match.group(3))
        if parsed:
            return parsed
    for match in re.finditer(r"\b([0-3]?\d)\s+([A-Z]+)\s+((?:19|20)\d{2})\b", folded):
        month = MONTH_BY_NAME.get(match.group(2))
        if month:
            parsed = date_from_parts(match.group(1), str(month), match.group(3))
            if parsed:
                return parsed
    for match in re.finditer(r"(?<!\d)([0-3]\d)([01]\d)((?:19|20)\d{2})(?!\d)", folded):
        parsed = date_from_parts(match.group(1), match.group(2), match.group(3))
        if parsed:
            return parsed
    return None


def is_uat_arrears_resource(resource: dict) -> bool:
    text = fold(" ".join(str(resource.get(key) or "") for key in ("name", "description", "url")))
    if "BUGETULUI GENERAL CONSOLIDAT" in text and "UNITATILOR" not in text:
        return False
    return "UAT" in text or ("UNITATILOR" in text and "TERITORIALE" in text)


def compact_arrears_resource(resource: dict, snapshot_date: str, duplicate_resources: int) -> dict:
    return {
        "snapshotDate": snapshot_date,
        "year": int(snapshot_date[:4]),
        "month": int(snapshot_date[5:7]),
        "resourceId": resource["id"],
        "name": resource.get("name") or "",
        "url": resource.get("url") or "",
        "format": resource.get("format") or "XLS",
        "created": resource.get("created") or None,
        "lastModified": resource.get("last_modified") or None,
        "duplicateResources": duplicate_resources,
    }


def build_arrears_resource_index(
    package_document: dict,
    retrieved_date: str,
    package_sha256: str | None = None,
) -> dict:
    result = package_document["result"] if package_document.get("success") else package_document
    grouped: dict[str, list[dict]] = defaultdict(list)
    for resource in result.get("resources", []):
        if not is_uat_arrears_resource(resource):
            continue
        snapshot_date = parse_arrears_snapshot_date(
            resource.get("description"), resource.get("name"), resource.get("url")
        )
        if snapshot_date:
            grouped[snapshot_date].append(resource)

    uat_resources = []
    for snapshot_date, resources in grouped.items():
        selected = sorted(
            resources,
            key=lambda resource: (
                resource.get("created") or "",
                int(resource.get("position") or 0),
            ),
        )[-1]
        uat_resources.append(compact_arrears_resource(selected, snapshot_date, len(resources)))
    uat_resources.sort(key=lambda resource: resource["snapshotDate"])

    covered_years = sorted({resource["year"] for resource in uat_resources})
    latest = uat_resources[-1] if uat_resources else None
    limitations = []
    if latest and latest["year"] < YEAR:
        limitations.append(
            {
                "id": "data-gov-arrears-current-years-unavailable",
                "severity": "material",
                "affects": ["arrearsRon"],
                "text": (
                    "The official data.gov.ro Arierate package has no UAT arrears resources "
                    f"after {latest['snapshotDate']} in the CKAN metadata inspected for this "
                    "import, so current mart years must keep arrears null unless a newer "
                    "official workbook is supplied separately."
                ),
            }
        )
    if any(resource["duplicateResources"] > 1 for resource in uat_resources):
        limitations.append(
            {
                "id": "data-gov-arrears-duplicate-uploads",
                "severity": "note",
                "affects": ["source"],
                "text": (
                    "Several monthly UAT arrears snapshots have duplicate resource uploads. "
                    "The compact index keeps one resource per snapshot date, preferring the "
                    "later CKAN resource creation timestamp."
                ),
            }
        )

    return {
        "$schema": "../schema/data-gov-arrears-resources.schema.json",
        "id": "data-gov-ro-arrears-resources",
        "title": "data.gov.ro Arierate UAT resource index",
        "publisher": result.get("organization", {}).get("title")
        or result.get("publisher")
        or "Ministerul Finantelor Publice",
        "license": result.get("license_title") or "",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": "data-gov-ro-ckan-package-show",
            "locator": f"{DATA_GOV_ARREARS_PACKAGE_URL}; {DATA_GOV_ARREARS_DATASET_URL}",
            "confidence": "verbatim",
            "note": (
                "Compact index derived from CKAN package metadata for the Arierate dataset. "
                "Only UAT-level monthly arrears resources are retained here."
            ),
        },
        "sourceHashes": {
            "ckanPackageSha256": package_sha256 or sha256_json(package_document),
        },
        "summary": {
            "resources": len(result.get("resources", [])),
            "uatResources": len(uat_resources),
            "firstUatSnapshotDate": uat_resources[0]["snapshotDate"] if uat_resources else None,
            "latestUatSnapshotDate": latest["snapshotDate"] if latest else None,
            "coveredYears": covered_years,
            "has2025UatResource": any(resource["year"] == 2025 for resource in uat_resources),
        },
        "latestUatResource": latest,
        "uatResources": uat_resources,
        "limitations": limitations,
    }


def read_arrears_resource_index(location: str | Path, retrieved_date: str) -> dict:
    raw = read_source_bytes(location)
    return build_arrears_resource_index(json.loads(raw), retrieved_date, sha256_bytes(raw))


def prefer_registry_population(uats: list[dict], population_by_siruta: dict[str, int]) -> None:
    for uat in uats:
        if uat["siruta"].isdigit() and uat["siruta"] in population_by_siruta:
            uat["population"] = population_by_siruta[uat["siruta"]]


def validate_roster_against_registry(uats: list[dict], registry_sirutas: set[str]) -> None:
    missing = sorted(
        {
            uat["siruta"]
            for uat in uats
            if uat["siruta"].isdigit() and uat["siruta"] not in registry_sirutas
        },
        key=int,
    )
    if missing:
        sample = ", ".join(missing[:10])
        raise SystemExit(
            f"transparenta.eu returned {len(missing)} numeric SIRUTA codes outside the "
            f"shared UAT registry: {sample}"
        )


def batch_query(
    uat_ids: list[str], category: str, year: int, offset: int = 0, expense_type: str | None = None
) -> str:
    parts = []
    expense_filter = f"expense_types: [{expense_type}], " if expense_type else ""
    for uat in uat_ids:
        if not re.fullmatch(r"\d+", uat):
            raise SystemExit(f"uat id is not a number: {uat!r}")
        parts.append(
            f"  u{uat}: aggregatedLineItems(filter: {{account_category: {category}, "
            f'report_type: PRINCIPAL_AGGREGATED, {expense_filter}uat_ids: ["{uat}"], '
            f'report_period: {{type: YEAR, selection: {{interval: {{start: "{year}", '
            f'end: "{year}"}}}}}}}}, limit: 400, offset: {int(offset)}) '
            "{ nodes { functional_code economic_code amount } pageInfo { hasNextPage } }"
        )
    return "query Batch {\n" + "\n".join(parts) + "\n}"


def all_rows(uat_id: str, category: str, year: int, expense_type: str | None = None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        query = batch_query([uat_id], category, year, offset=offset, expense_type=expense_type)
        page = post(query)[f"u{uat_id}"]
        rows.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"] or not page["nodes"]:
            return rows
        offset += len(page["nodes"])


def fetch_line_items(
    uats: list[dict], category: str, year: int, expense_type: str | None = None
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    label = f"{category}:{expense_type}" if expense_type else category
    for start in range(0, len(uats), BATCH):
        chunk = uats[start : start + BATCH]
        query = batch_query([u["uatId"] for u in chunk], category, year, expense_type=expense_type)
        data = post(query)
        for uat in chunk:
            found = data.get(f"u{uat['uatId']}")
            if not found:
                continue
            nodes = found["nodes"]
            if found["pageInfo"]["hasNextPage"]:
                nodes = all_rows(uat["uatId"], category, year, expense_type=expense_type)
                print(
                    f"  {year} {label} {uat['siruta']}: {len(nodes)} linii, paginat",
                    file=sys.stderr,
                )
            out[uat["siruta"]] = nodes
        print(
            f"  {year} {label}: {min(start + BATCH, len(uats))} of {len(uats)}",
            file=sys.stderr,
        )
    return out


def totals(rows: list[dict]) -> tuple[float, float]:
    """(everything, the part raised locally), in lei."""
    total = 0.0
    own = 0.0
    for row in rows:
        code = str(row.get("functional_code") or "")
        amount = float(row.get("amount") or 0.0)
        total += amount
        if not code.startswith(TRANSFER_PREFIXES):
            own += amount
    return total, own


def fetch(uats: list[dict], category: str, year: int) -> dict[str, tuple[float, float]]:
    return {siruta: totals(rows) for siruta, rows in fetch_line_items(uats, category, year).items()}


def code_matches_prefix(code: str, prefixes: tuple[str, ...]) -> bool:
    value = str(code or "")
    return any(value == prefix or value.startswith(f"{prefix}.") for prefix in prefixes)


def sum_amount(rows: list[dict]) -> float:
    return sum(float(row.get("amount") or 0.0) for row in rows)


def sum_by_economic_prefix(rows: list[dict], prefixes: tuple[str, ...]) -> float:
    return sum(
        float(row.get("amount") or 0.0)
        for row in rows
        if code_matches_prefix(str(row.get("economic_code") or ""), prefixes)
    )


def round_money(value: float) -> float:
    return round(value, 2)


def share(part: float, total: float) -> float | None:
    return round(part / total, 4) if total else None


def per_inhabitant(value: float, population: int | None) -> float | None:
    return round(value / population, 2) if population and population > 0 else None


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def as_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace("\xa0", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def read_xls_workbook(data: bytes, label: str):
    import xlrd

    try:
        return xlrd.open_workbook(file_contents=data)
    except Exception as original_error:
        try:
            repaired = data.decode("utf-8").encode("latin-1")
        except UnicodeError:
            repaired = b""
        if repaired.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            try:
                return xlrd.open_workbook(file_contents=repaired)
            except Exception:
                pass
        raise SystemExit(f"{label}: could not read legacy XLS workbook: {original_error}") from (
            original_error
        )


def parse_arrears_rows(
    rows: list[list[object]],
    registry_document: dict,
    snapshot_date: str,
) -> dict:
    unit_index, county_by_key = registry_arrears_indexes(registry_document)
    current_county_code: str | None = None
    workbook_total: float | None = None
    county_totals: dict[str, float] = {}
    records_by_siruta: dict[str, float] = {}
    matched_rows = []
    unmatched_rows = []
    ambiguous_rows = []

    for row in rows:
        number = as_number(row[0]) if len(row) > 0 else None
        name = as_text(row[1]) if len(row) > 1 else ""
        amount = as_number(row[2]) if len(row) > 2 else None
        key = arrears_join_key(name)
        if not key:
            continue
        if key == "TOTAL":
            if amount is not None:
                workbook_total = amount
            continue
        if key in {"DIN CARE", "NR CRT", "UNITATEA SUBDIVIZIUNEA ADMINISTRATIV TERITORIALA"}:
            continue

        county_code = county_by_key.get(key)
        if county_code and number is not None:
            current_county_code = county_code
            if amount is not None:
                county_totals[county_code] = round_money(amount)
            continue
        if amount is None or current_county_code is None:
            continue

        if is_county_council_name(name):
            siruta = current_county_code
            match_kind = "county-council"
        else:
            candidates = arrears_candidates(unit_index, current_county_code, key)
            if len(candidates) > 1:
                ambiguous_rows.append(
                    {
                        "countyCode": current_county_code,
                        "sourceName": name,
                        "amountRon": round_money(amount),
                        "candidateSirutas": ",".join(sorted(unit["siruta"] for unit in candidates)),
                    }
                )
                continue
            if not candidates:
                unmatched_rows.append(
                    {
                        "countyCode": current_county_code,
                        "sourceName": name,
                        "amountRon": round_money(amount),
                    }
                )
                continue
            siruta = candidates[0]["siruta"]
            match_kind = "name-within-county"

        records_by_siruta[siruta] = round_money(records_by_siruta.get(siruta, 0.0) + amount)
        matched_rows.append(
            {
                "siruta": siruta,
                "countyCode": current_county_code,
                "sourceName": name,
                "amountRon": round_money(amount),
                "matchKind": match_kind,
            }
        )

    authority_total = round_money(
        sum(row["amountRon"] for row in matched_rows)
        + sum(row["amountRon"] for row in unmatched_rows)
        + sum(row["amountRon"] for row in ambiguous_rows)
    )
    matched_total = round_money(sum(records_by_siruta.values()))
    return {
        "snapshotDate": snapshot_date,
        "amountUnit": "RON",
        "recordsBySiruta": dict(
            sorted(records_by_siruta.items(), key=lambda item: siruta_sort_key(item[0]))
        ),
        "matchedRows": sorted(matched_rows, key=lambda row: (row["countyCode"], row["sourceName"])),
        "unmatchedRows": unmatched_rows,
        "ambiguousRows": ambiguous_rows,
        "summary": {
            "countySubtotalRows": len(county_totals),
            "authorityRows": len(matched_rows) + len(unmatched_rows) + len(ambiguous_rows),
            "matchedRows": len(matched_rows),
            "unmatchedRows": len(unmatched_rows),
            "ambiguousRows": len(ambiguous_rows),
            "workbookTotalArrearsRon": round_money(workbook_total)
            if workbook_total is not None
            else None,
            "authorityRowsArrearsRon": authority_total,
            "matchedArrearsRon": matched_total,
            "unmatchedArrearsRon": round_money(authority_total - matched_total),
        },
    }


def read_arrears_workbook(
    location: str | Path,
    registry_document: dict,
    snapshot_date: str | None = None,
) -> dict:
    raw = read_source_bytes(location)
    workbook = read_xls_workbook(raw, str(location))
    sheet = workbook.sheet_by_index(0)
    rows = [
        [sheet.cell_value(row_index, column_index) for column_index in range(sheet.ncols)]
        for row_index in range(sheet.nrows)
    ]
    found_date = snapshot_date or parse_arrears_snapshot_date(str(location), *rows[:8])
    if not found_date:
        raise SystemExit(f"{location}: could not infer arrears snapshot date")
    snapshot = parse_arrears_rows(rows, registry_document, found_date)
    snapshot["source"] = {
        "source": "data-gov-ro-arierate-uat-xls",
        "locator": f"{location}; sheet {sheet.name!r}",
        "sha256": sha256_bytes(raw),
    }
    return snapshot


def apply_arrears_snapshot(records: list[dict], snapshot: dict) -> int:
    year = int(snapshot["snapshotDate"][:4])
    amounts = snapshot["recordsBySiruta"]
    changed = 0
    for record in records:
        if record["year"] != year:
            continue
        amount = round_money(amounts.get(record["siruta"], 0.0))
        record["arrearsRon"] = amount
        record["arrearsPerInhabitantRon"] = per_inhabitant(amount, record.get("population"))
        changed += 1
    return changed


def select_sample_uats(
    uats: list[dict], sample: tuple[tuple[str, str], ...] = SAMPLE_UATS
) -> list[dict]:
    by_siruta = {uat["siruta"]: uat for uat in uats}
    missing = [siruta for siruta, _ in sample if siruta not in by_siruta]
    if missing:
        raise SystemExit(
            f"sample SIRUTA codes missing from Transparenta roster: {', '.join(missing)}"
        )
    return [by_siruta[siruta] | {"sampleRole": role} for siruta, role in sample]


def select_uats_for_scope(uats: list[dict], scope: str) -> list[dict]:
    if scope == "sample":
        return select_sample_uats(uats)
    if scope == "full":
        return [uat | {"sampleRole": "full-import"} for uat in uats]
    raise SystemExit(f"unknown local finance scope {scope!r}; expected one of {SCOPES}")


def siruta_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def period_slug(years: list[int]) -> str:
    return str(min(years)) if min(years) == max(years) else f"{min(years)}-{max(years)}"


def mart_id(scope: str, years: list[int]) -> str:
    prefix = "local-finance-mart-sample" if scope == "sample" else "local-finance-mart"
    return f"{prefix}-{period_slug(years)}"


def mart_title(scope: str, years: list[int]) -> str:
    label = "Local finance mart sample" if scope == "sample" else "Local finance mart"
    return f"{label}, {period_slug(years)}"


def default_mart_path(year: int, out_dir: Path = PACKAGE_ROOT / "data") -> Path:
    return out_dir / f"{mart_id('full', [year])}.json"


def record_from_lines(
    uat: dict,
    registry_unit: dict | None,
    year: int,
    revenue_rows: list[dict],
    spending_rows: list[dict],
    development_rows: list[dict],
) -> dict:
    revenue, own_revenue = totals(revenue_rows)
    transfer_revenue = revenue - own_revenue
    spending = sum_amount(spending_rows)
    personnel = sum_by_economic_prefix(spending_rows, PERSONNEL_ECONOMIC_PREFIXES)
    capital = sum_by_economic_prefix(spending_rows, CAPITAL_ECONOMIC_PREFIXES)
    development = sum_amount(development_rows)

    registry_population = registry_unit.get("population") if registry_unit else None
    roster_population = uat.get("population")
    population = registry_population if registry_population is not None else roster_population
    if registry_population is not None:
        population_source = registry_unit.get("populationSource")
    elif roster_population is not None:
        population_source = "transparenta-eu-uat-roster-fallback"
    else:
        population_source = None

    level = (
        registry_unit["level"]
        if registry_unit
        else ("county" if not uat["siruta"].isdigit() else "uat")
    )
    county = registry_unit["countyCode"] if registry_unit else uat.get("county")
    name = registry_unit["name"] if registry_unit else uat["name"]

    return {
        "year": year,
        "siruta": uat["siruta"],
        "cui": registry_unit.get("cui") if registry_unit else None,
        "level": level,
        "sampleRole": uat.get("sampleRole", "full-import"),
        "name": name,
        "transparentaName": uat["name"],
        "countyCode": county,
        "population": int(population) if population is not None else None,
        "populationSource": population_source,
        "revenueRon": round_money(revenue),
        "ownRevenueRon": round_money(own_revenue),
        "transferRevenueRon": round_money(transfer_revenue),
        "spendingRon": round_money(spending),
        "personnelSpendingRon": round_money(personnel),
        "capitalSpendingRon": round_money(capital),
        "developmentSpendingRon": round_money(development),
        "arrearsRon": None,
        "arrearsPerInhabitantRon": None,
        "ownRevenueShare": share(own_revenue, revenue),
        "personnelSpendingShare": share(personnel, spending),
        "capitalSpendingShare": share(capital, spending),
        "developmentSpendingShare": share(development, spending),
        "revenuePerInhabitantRon": per_inhabitant(revenue, population),
        "ownRevenuePerInhabitantRon": per_inhabitant(own_revenue, population),
        "spendingPerInhabitantRon": per_inhabitant(spending, population),
        "sourceLineCounts": {
            "revenue": len(revenue_rows),
            "spending": len(spending_rows),
            "development": len(development_rows),
        },
    }


def fetch_mart_records(
    uats: list[dict], years: list[int], registry_document: dict
) -> tuple[list[dict], dict]:
    registry_by_siruta = {unit["siruta"]: unit for unit in registry_document["units"]}
    records = []
    raw: dict[str, object] = {"years": years, "uats": uats, "lineItems": {}}
    for year in years:
        revenue = fetch_line_items(uats, "vn", year)
        spending = fetch_line_items(uats, "ch", year)
        development = fetch_line_items(uats, "ch", year, expense_type="dezvoltare")
        raw["lineItems"][str(year)] = {  # type: ignore[index]
            "revenue": revenue,
            "spending": spending,
            "development": development,
        }
        for uat in uats:
            records.append(
                record_from_lines(
                    uat,
                    registry_by_siruta.get(uat["siruta"]),
                    year,
                    revenue.get(uat["siruta"], []),
                    spending.get(uat["siruta"], []),
                    development.get(uat["siruta"], []),
                )
            )
    return sorted(records, key=lambda row: (row["year"], siruta_sort_key(row["siruta"]))), raw


def build_year_summary(records: list[dict]) -> list[dict]:
    years = sorted({row["year"] for row in records})
    out = []
    for year in years:
        rows = [row for row in records if row["year"] == year]
        out.append(
            {
                "year": year,
                "records": len(rows),
                "revenueRon": round_money(sum(row["revenueRon"] for row in rows)),
                "ownRevenueRon": round_money(sum(row["ownRevenueRon"] for row in rows)),
                "spendingRon": round_money(sum(row["spendingRon"] for row in rows)),
                "personnelSpendingRon": round_money(
                    sum(row["personnelSpendingRon"] for row in rows)
                ),
                "capitalSpendingRon": round_money(sum(row["capitalSpendingRon"] for row in rows)),
                "developmentSpendingRon": round_money(
                    sum(row["developmentSpendingRon"] for row in rows)
                ),
            }
        )
    return out


def finance_limitations(
    records: list[dict],
    arrears_snapshot: dict | None = None,
    arrears_resources: dict | None = None,
) -> list[dict]:
    has_population_fallback = any(
        row["populationSource"] == "transparenta-eu-uat-roster-fallback" for row in records
    )
    missing_development_years = [
        year
        for year in sorted({row["year"] for row in records})
        if all(row["developmentSpendingRon"] == 0 for row in records if row["year"] == year)
    ]
    limitations = [
        {
            "id": "transparenta-data-license-snapshot",
            "severity": "material",
            "affects": ["local-finance"],
            "text": (
                "Transparenta publishes the API and reference repositories openly, but this mart "
                "does not treat repository licenses as licenses for the underlying official budget "
                "data. Each snapshot keeps its own retrieval date and checksum."
            ),
        },
        {
            "id": "own-revenue-classification-prefixes",
            "severity": "material",
            "affects": ["ownRevenueRon", "ownRevenueShare"],
            "text": (
                "Own revenue is derived by excluding functional-code prefixes for income-tax "
                "shares, VAT allocations, subsidies and EU funds. Moving a prefix changes the "
                "indicator, so the prefix list is published with the mart."
            ),
        },
    ]
    rows_with_arrears = sum(1 for row in records if row.get("arrearsRon") is not None)
    if rows_with_arrears:
        limitations.append(
            {
                "id": "data-gov-arrears-name-county-join",
                "severity": "material",
                "affects": ["arrearsRon", "arrearsPerInhabitantRon"],
                "text": (
                    "The official UAT arrears workbook does not publish SIRUTA or CUI columns. "
                    "Imported arrears are joined by normalized authority name within county; "
                    "unlisted authorities in the workbook snapshot are treated as zero arrears."
                ),
            }
        )
        if arrears_snapshot and arrears_snapshot["summary"]["unmatchedRows"]:
            limitations.append(
                {
                    "id": "data-gov-arrears-unmatched-source-rows",
                    "severity": "material",
                    "affects": ["arrearsRon", "siruta"],
                    "text": (
                        "Some named authority rows in the official arrears workbook could not "
                        "be matched unambiguously to the shared UAT registry. Their arrears are "
                        "reported in the import summary and excluded from per-UAT records."
                    ),
                }
            )
    else:
        latest = (arrears_resources or {}).get("summary", {}).get("latestUatSnapshotDate")
        limitations.append(
            {
                "id": (
                    "data-gov-arrears-period-unavailable"
                    if arrears_resources
                    else "arrears-not-imported-yet"
                ),
                "severity": "material",
                "affects": ["arrearsRon", "arrearsPerInhabitantRon"],
                "text": (
                    "The official data.gov.ro arrears package was inspected, but it has no UAT "
                    f"arrears resource covering this mart period; the latest indexed UAT "
                    f"snapshot is {latest}. Arrears stay null rather than being backfilled from "
                    "stale data."
                    if latest
                    else (
                        "This mart was generated without an arrears workbook. The field is "
                        "present and null so downstream consumers can depend on the schema "
                        "without mistaking missing arrears for zero arrears."
                    )
                ),
            }
        )
    if missing_development_years:
        limitations.append(
            {
                "id": "development-expense-type-missing-for-year",
                "severity": "material",
                "affects": ["developmentSpendingRon", "developmentSpendingShare"],
                "text": (
                    "Transparenta returns no `expense_types: dezvoltare` line items for "
                    f"{', '.join(map(str, missing_development_years))}. Development fields are "
                    "therefore source-missing for those years, not evidence that development "
                    "spending was zero."
                ),
            }
        )
    if has_population_fallback:
        limitations.append(
            {
                "id": "bucharest-sector-population-fallback",
                "severity": "material",
                "affects": ["population", "perInhabitantIndicators"],
                "text": (
                    "The shared UAT registry has no official POP107D population split for "
                    "Bucharest sectors. Sector rows keep Transparenta roster population as a "
                    "fallback and mark the source on each record."
                ),
            }
        )
    return limitations


def build_mart_document(
    records: list[dict],
    years: list[int],
    retrieved_date: str,
    registry_document: dict,
    registry_sha256: str,
    transparenta_sha256: str,
    scope: str = "sample",
    arrears_snapshot: dict | None = None,
    arrears_resources: dict | None = None,
) -> dict:
    sample = [
        {"siruta": siruta, "role": role}
        for siruta, role in SAMPLE_UATS
        if any(row["siruta"] == siruta for row in records)
    ]
    source_hashes = {
        "transparentaResponsesSha256": transparenta_sha256,
        "uatRegistrySha256": registry_sha256,
    }
    if arrears_snapshot:
        source_hashes["dataGovArrearsWorkbookSha256"] = arrears_snapshot["source"]["sha256"]

    return {
        "$schema": "../schema/local-finance-mart.schema.json",
        "id": mart_id(scope, years),
        "title": mart_title(scope, years),
        "publisher": "transparenta.eu",
        "scope": scope,
        "periodStart": str(min(years)),
        "periodEnd": str(max(years)),
        "currency": "RON",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": "transparenta-eu-graphql",
            "locator": (
                f"{API}, aggregatedLineItems, account_category vn/ch, "
                "expense_types dezvoltare for development spending, "
                f"report_type PRINCIPAL_AGGREGATED, years {min(years)}-{max(years)}, per uat_ids"
            ),
            "confidence": "derived",
            "note": (
                "Revenue, spending and development spending are summed from Transparenta line "
                "items. Own revenue, personnel and capital spending are derived from published "
                "classification-code prefixes."
            ),
        },
        "sourceHashes": source_hashes,
        "registry": {
            "id": registry_document["id"],
            "period": registry_document["period"],
        },
        "assumptions": {
            "reportType": "PRINCIPAL_AGGREGATED",
            "transferPrefixes": list(TRANSFER_PREFIXES),
            "personnelEconomicPrefixes": list(PERSONNEL_ECONOMIC_PREFIXES),
            "capitalEconomicPrefixes": list(CAPITAL_ECONOMIC_PREFIXES),
            "developmentExpenseType": "dezvoltare",
            "suspectMultipleOfMedian": SUSPECT_MULTIPLE,
        },
        "sample": sample,
        "summary": {
            "uats": len({row["siruta"] for row in records}),
            "years": len(years),
            "records": len(records),
            "registryMatchedUats": len(
                {row["siruta"] for row in records if row["cui"] is not None}
            ),
            "rowsWithPopulation": sum(1 for row in records if row["population"] is not None),
            "revenueRon": round_money(sum(row["revenueRon"] for row in records)),
            "ownRevenueRon": round_money(sum(row["ownRevenueRon"] for row in records)),
            "spendingRon": round_money(sum(row["spendingRon"] for row in records)),
            "personnelSpendingRon": round_money(
                sum(row["personnelSpendingRon"] for row in records)
            ),
            "capitalSpendingRon": round_money(sum(row["capitalSpendingRon"] for row in records)),
            "developmentSpendingRon": round_money(
                sum(row["developmentSpendingRon"] for row in records)
            ),
            "byYear": build_year_summary(records),
        },
        "records": records,
        "limitations": finance_limitations(
            records, arrears_snapshot=arrears_snapshot, arrears_resources=arrears_resources
        ),
    }


def heatmap_total(category: str, year: int) -> tuple[int, float]:
    query = f"""
    query Total($year: PeriodDate!) {{
      heatmapUATData(
        filter: {{
          account_category: {category}
          report_type: PRINCIPAL_AGGREGATED
          is_uat: true
          report_period: {{ type: YEAR, selection: {{ dates: [$year] }} }}
        }}
      ) {{
        siruta_code
        total_amount
      }}
    }}
    """
    rows = post(query, {"year": str(year)})["heatmapUATData"]
    return len(rows), sum(float(row.get("total_amount") or 0.0) for row in rows)


def transparenta_national_totals(year: int) -> dict:
    revenue_rows, revenue = heatmap_total("vn", year)
    spending_rows, spending = heatmap_total("ch", year)
    return {
        "period": str(year),
        "source": "transparenta-eu-graphql",
        "revenueRows": revenue_rows,
        "spendingRows": spending_rows,
        "revenueRon": round_money(revenue),
        "spendingRon": round_money(spending),
    }


def data_gov_2024_totals(path: Path) -> dict:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook["total TARA"]
    total_row = None
    for row in worksheet.iter_rows(values_only=True):
        if row[0] == "TOTAL" and isinstance(row[2], int | float):
            total_row = row
            break
    if total_row is None:
        raise SystemExit(f"{path}: could not find TOTAL row in 'total TARA'")
    return {
        "period": "2024",
        "source": "data-gov-ro-local-revenue-expense-2024",
        "locator": f"{DATA_GOV_2024_URL}; workbook sheet 'total TARA', row TOTAL",
        "sha256": sha256_file(path),
        "revenueRon": round_money(float(total_row[2])),
        "ownRevenueRon": round_money(float(total_row[3])),
        "spendingRon": round_money(float(total_row[23])),
        "personnelSpendingRon": round_money(float(total_row[24])),
        "capitalSpendingRon": round_money(float(total_row[36])),
    }


def comparison_check(data_gov: dict | None, transparenta: dict | None) -> dict:
    if not data_gov or not transparenta:
        return {
            "id": "data-gov-2024-national-comparison",
            "status": "not_run",
            "text": (
                "No data.gov.ro workbook was supplied, so the report records the comparison "
                "hook only."
            ),
            "metrics": {},
        }

    revenue_delta = transparenta["revenueRon"] - data_gov["revenueRon"]
    spending_delta = transparenta["spendingRon"] - data_gov["spendingRon"]
    revenue_relative = revenue_delta / data_gov["revenueRon"] if data_gov["revenueRon"] else None
    spending_relative = (
        spending_delta / data_gov["spendingRon"] if data_gov["spendingRon"] else None
    )
    status = "pass"
    text = "Transparenta and data.gov.ro 2024 national totals are within the 5% comparison band."
    if (
        revenue_relative is None
        or spending_relative is None
        or abs(revenue_relative) > 0.05
        or abs(spending_relative) > 0.05
    ):
        status = "warning"
        text = (
            "Transparenta and the data.gov.ro workbook do not reconcile at national level in "
            "this first slice; the report keeps the gap visible before treating either scope as "
            "canonical."
        )
    return {
        "id": "data-gov-2024-national-comparison",
        "status": status,
        "text": text,
        "metrics": {
            "transparentaRevenueRon": transparenta["revenueRon"],
            "dataGovRevenueRon": data_gov["revenueRon"],
            "revenueRelativeDifference": round(revenue_relative, 4)
            if revenue_relative is not None
            else None,
            "transparentaSpendingRon": transparenta["spendingRon"],
            "dataGovSpendingRon": data_gov["spendingRon"],
            "spendingRelativeDifference": round(spending_relative, 4)
            if spending_relative is not None
            else None,
        },
    }


def arrears_coverage_check(mart: dict, arrears_resources: dict | None = None) -> dict:
    records = mart["records"]
    years = sorted({row["year"] for row in records})
    rows_with_arrears = sum(1 for row in records if row.get("arrearsRon") is not None)
    if rows_with_arrears:
        target_years = sorted({row["year"] for row in records if row.get("arrearsRon") is not None})
        return {
            "id": "data-gov-arrears-coverage",
            "status": "pass",
            "text": "Arrears values are populated for at least one mart year.",
            "metrics": {
                "recordsWithArrears": rows_with_arrears,
                "yearsWithArrears": ",".join(map(str, target_years)),
            },
        }
    if not arrears_resources:
        return {
            "id": "data-gov-arrears-coverage",
            "status": "not_run",
            "text": (
                "No data.gov.ro Arierate package metadata or workbook was supplied, so arrears "
                "coverage was not checked."
            ),
            "metrics": {
                "requestedYears": ",".join(map(str, years)),
                "recordsWithArrears": 0,
            },
        }

    summary = arrears_resources["summary"]
    covered_years = set(summary["coveredYears"])
    missing_years = [year for year in years if year not in covered_years]
    return {
        "id": "data-gov-arrears-coverage",
        "status": "warning" if missing_years else "not_run",
        "text": (
            "The official data.gov.ro Arierate package was inspected, but it has no UAT arrears "
            "resource for the mart year(s); arrears remain null rather than using stale source "
            "snapshots."
            if missing_years
            else (
                "The data.gov.ro Arierate package has UAT resources for the mart year(s), but "
                "no workbook was supplied to populate per-UAT arrears."
            )
        ),
        "metrics": {
            "requestedYears": ",".join(map(str, years)),
            "coveredYears": ",".join(map(str, summary["coveredYears"])),
            "missingYears": ",".join(map(str, missing_years)) if missing_years else None,
            "latestUatSnapshotDate": summary["latestUatSnapshotDate"],
            "recordsWithArrears": 0,
        },
    }


def build_validation_report(
    mart: dict,
    data_gov: dict | None = None,
    transparenta: dict | None = None,
    arrears_resources: dict | None = None,
) -> dict:
    records = mart["records"]
    scope = mart.get("scope", "sample" if "-sample-" in mart["id"] else "full")
    roles = {row["siruta"]: row["sampleRole"] for row in records}
    commune_counties = {
        row["countyCode"]
        for row in records
        if row["sampleRole"] == "rural-commune" and row["level"] == "commune"
    }
    unique_sirutas = {row["siruta"] for row in records}
    numeric_sirutas = {siruta for siruta in unique_sirutas if siruta.isdigit()}
    county_codes = {siruta for siruta in unique_sirutas if not siruta.isdigit()}
    if scope == "sample":
        scope_check = {
            "id": "sample-scope",
            "status": (
                "pass"
                if (
                    mart["summary"]["uats"] == 10
                    and "county-seat" in roles.values()
                    and "bucharest-sector" in roles.values()
                    and len(commune_counties) >= 3
                )
                else "fail"
            ),
            "text": (
                "Sample covers ten UATs over three years, including a county seat, a Bucharest "
                "sector and rural communes from at least three counties."
            ),
            "metrics": {
                "uats": mart["summary"]["uats"],
                "years": mart["summary"]["years"],
                "ruralCommuneCounties": len(commune_counties),
            },
        }
    else:
        expected_records = len(unique_sirutas) * mart["summary"]["years"]
        scope_check = {
            "id": "full-national-scope",
            "status": (
                "pass"
                if (
                    len(unique_sirutas) > 3000
                    and len(numeric_sirutas) > 3000
                    and len(county_codes) >= 40
                    and mart["summary"]["records"] == expected_records
                )
                else "fail"
            ),
            "text": (
                "Full mart covers the national Transparenta UAT roster, including county "
                "councils that file under county letter codes."
            ),
            "metrics": {
                "uats": len(unique_sirutas),
                "numericUats": len(numeric_sirutas),
                "countyCouncils": len(county_codes),
                "years": mart["summary"]["years"],
                "records": mart["summary"]["records"],
                "expectedRecords": expected_records,
            },
        }
    all_have_finance = all(row["revenueRon"] > 0 or row["spendingRon"] > 0 for row in records)
    all_registry_matched = mart["summary"]["registryMatchedUats"] == len(numeric_sirutas)
    development_missing_years = [
        year["year"] for year in mart["summary"]["byYear"] if year["developmentSpendingRon"] == 0
    ]
    checks = [
        scope_check,
        {
            "id": "registry-join",
            "status": "pass" if all_registry_matched else "fail",
            "text": (
                "Every numeric SIRUTA joins to the shared UAT registry and carries a CUI; "
                "county-council letter codes are kept outside that join."
            ),
            "metrics": {
                "registryMatchedUats": mart["summary"]["registryMatchedUats"],
                "numericUats": len(numeric_sirutas),
                "countyCouncils": len(county_codes),
            },
        },
        {
            "id": "transparenta-line-items",
            "status": "pass" if all_have_finance else "fail",
            "text": "Every UAT-year has at least one revenue or spending line item.",
            "metrics": {
                "records": mart["summary"]["records"],
                "emptyRecords": sum(
                    1 for row in records if row["revenueRon"] == 0 and row["spendingRon"] == 0
                ),
            },
        },
        {
            "id": "development-expense-type-coverage",
            "status": "warning" if development_missing_years else "pass",
            "text": (
                "Transparenta development-spending expense-type rows are present for each "
                "requested year."
                if not development_missing_years
                else (
                    "Transparenta returns no development-spending expense-type rows for at least "
                    "one requested year; the mart keeps those fields as source-missing zeros "
                    "with a named limitation."
                )
            ),
            "metrics": {
                "missingYears": ",".join(map(str, development_missing_years))
                if development_missing_years
                else None
            },
        },
        comparison_check(data_gov, transparenta),
        arrears_coverage_check(mart, arrears_resources),
    ]
    counts = Counter(check["status"] for check in checks)
    report_period = period_slug([int(mart["periodStart"]), int(mart["periodEnd"])])
    limitations = (
        finance_limitations(records, arrears_resources=arrears_resources)
        if arrears_resources
        else list(mart["limitations"])
    )
    known_limitation_ids = {limitation["id"] for limitation in limitations}
    for limitation in (arrears_resources or {}).get("limitations", []):
        if limitation["id"] not in known_limitation_ids:
            limitations.append(limitation)
            known_limitation_ids.add(limitation["id"])
    return {
        "$schema": "../schema/local-finance-validation-report.schema.json",
        "id": f"local-finance-validation-report-{report_period}",
        "title": f"Local finance mart validation report, {report_period}",
        "martId": mart["id"],
        "periodStart": mart["periodStart"],
        "periodEnd": mart["periodEnd"],
        "retrievedDate": mart["retrievedDate"],
        "summary": {
            "checks": len(checks),
            "passed": counts["pass"],
            "warnings": counts["warning"],
            "failed": counts["fail"],
            "notRun": counts["not_run"],
        },
        "checks": checks,
        "dataGovComparison": (
            {
                "dataGov": data_gov,
                "transparenta": transparenta,
            }
            if data_gov and transparenta
            else None
        ),
        "limitations": limitations,
    }


def quarantine(rows: list[dict]) -> list[dict]:
    per_capita = [
        (r["spendingRon"] / r["population"], r)
        for r in rows
        if (r.get("population") or 0) > 0 and r["spendingRon"] > 0
    ]
    if not per_capita:
        return []
    ordered = sorted(value for value, _ in per_capita)
    median = ordered[len(ordered) // 2]
    suspects = []
    for value, row in per_capita:
        if value <= SUSPECT_MULTIPLE * median:
            continue
        row["suspect"] = True
        suspects.append(
            {
                "siruta": row["siruta"],
                "name": row["name"],
                "reportedSpendingRon": row["spendingRon"],
                "perInhabitantRon": round(value, 2),
                "timesMedian": round(value / median, 1),
            }
        )
    return sorted(suspects, key=lambda s: -s["timesMedian"])


def build_legacy_budget_document(
    uats: list[dict],
    revenue: dict[str, tuple[float, float]],
    spending: dict[str, tuple[float, float]],
    year: int,
) -> dict:
    rows = []
    for uat in sorted(uats, key=lambda u: u["siruta"]):
        total_revenue, own_revenue = revenue.get(uat["siruta"], (0.0, 0.0))
        total_spend, _ = spending.get(uat["siruta"], (0.0, 0.0))
        if total_revenue == 0 and total_spend == 0:
            continue
        rows.append(
            {
                "siruta": uat["siruta"],
                "level": "county" if not uat["siruta"].isdigit() else "uat",
                "name": uat["name"],
                "county": uat["county"],
                "population": uat["population"],
                "revenueRon": round_money(total_revenue),
                "ownRevenueRon": round_money(own_revenue),
                "spendingRon": round_money(total_spend),
                "ownShare": share(own_revenue, total_revenue),
            }
        )

    return build_legacy_budget_document_from_rows(rows, year)


def build_legacy_budget_document_from_records(records: list[dict], year: int) -> dict:
    rows = []
    for record in sorted(records, key=lambda row: row["siruta"]):
        if record["year"] != year:
            continue
        if record["revenueRon"] == 0 and record["spendingRon"] == 0:
            continue
        rows.append(
            {
                "siruta": record["siruta"],
                "level": "county" if not record["siruta"].isdigit() else "uat",
                "name": record.get("transparentaName") or record["name"],
                "county": record["countyCode"],
                "population": record["population"],
                "revenueRon": record["revenueRon"],
                "ownRevenueRon": record["ownRevenueRon"],
                "spendingRon": record["spendingRon"],
                "ownShare": share(record["ownRevenueRon"], record["revenueRon"]),
            }
        )
    return build_legacy_budget_document_from_rows(rows, year)


def build_legacy_budget_document_from_mart(mart: dict, year: int | None = None) -> dict:
    years = sorted({row["year"] for row in mart["records"]})
    selected_year = year if year is not None else years[-1]
    if selected_year not in years:
        raise SystemExit(f"{mart['id']} has no records for {selected_year}")
    return build_legacy_budget_document_from_records(mart["records"], selected_year)


def build_legacy_budget_document_from_rows(rows: list[dict], year: int) -> dict:
    suspects = quarantine(rows)
    rows = [row for row in rows if not row.get("suspect")]
    reporting = len(rows)
    with_own = [row for row in rows if row["ownShare"] is not None]
    median_own = (
        sorted(row["ownShare"] for row in with_own)[len(with_own) // 2] if with_own else None
    )

    return {
        "$schema": "../schema/buget-uat.schema.json",
        "id": f"buget-uat-{year}",
        "title": f"Veniturile și cheltuielile fiecărei UAT, execuție {year}",
        "publisher": "transparenta.eu",
        "period": str(year),
        "currency": "RON",
        "provenance": {
            "source": "transparenta-eu-graphql",
            "locator": (
                f"{API}, aggregatedLineItems, account_category vn și ch, "
                f"report_type PRINCIPAL_AGGREGATED, anul {year}, pe uat_ids"
            ),
            "confidence": "verbatim",
            "note": (
                "Sumele sunt execuția bugetară raportată de fiecare ordonator principal, "
                "preluate ca atare. Împărțirea în venituri proprii și transferuri este a "
                "acestui import, după capitolele din clasificația veniturilor."
            ),
        },
        "assumptions": {
            "transferPrefixes": list(TRANSFER_PREFIXES),
            "suspectMultipleOfMedian": SUSPECT_MULTIPLE,
        },
        "excluded": suspects,
        "summary": {
            "uatsReporting": reporting,
            "revenueRon": round_money(sum(row["revenueRon"] for row in rows)),
            "ownRevenueRon": round_money(sum(row["ownRevenueRon"] for row in rows)),
            "spendingRon": round_money(sum(row["spendingRon"] for row in rows)),
            "medianOwnShare": median_own,
        },
        "uats": rows,
        "limitations": [
            {
                "id": "venituri-proprii-dupa-capitol",
                "severity": "material",
                "text": (
                    "Ce se numește „venit propriu” este o alegere făcută aici, pe capitole de "
                    "clasificație: cotele defalcate din impozitul pe venit, sumele defalcate din "
                    "TVA, subvențiile și banii europeni sunt scoase, restul rămâne. Un cititor "
                    "care mută un capitol schimbă cifra — de aceea lista e publicată în fișier."
                ),
            },
            {
                "id": "consiliile-judetene-in-total",
                "severity": "note",
                "text": (
                    "Consiliile județene depun fără cod SIRUTA, sub codul de județ, și sunt "
                    "păstrate în total cu „level”: „county”. Cheltuiala lor este tot "
                    "cheltuială locală; harta, care se leagă pe SIRUTA numeric, nu le atinge."
                ),
            },
            {
                "id": "executie-nu-buget",
                "severity": "note",
                "text": (
                    "Este execuția, adică ce s-a încasat și s-a plătit efectiv, nu bugetul "
                    "aprobat. Un an cu o investiție mare arată o cheltuială mare care nu se "
                    "repetă."
                ),
            },
            {
                "id": "raportari-imposibile-scoase",
                "severity": "blocking",
                "text": (
                    "Trei sectoare ale Bucureștiului raportează sume care nu pot fi cheltuieli "
                    "de primărie — Sectorul 1 depune 441 de miliarde de lei la 225 000 de "
                    "locuitori, de 391 de ori mediana pe cap de locuitor a țării, cu aceleași "
                    "coduri de clasificație repetate de sute de ori. Aceleași cifre vin și din "
                    "agregarea pe județ a API-ului, deci problema e în sursă, nu în întrebare. "
                    "Sunt scoase din total și numite în „excluded”, fiindcă altfel ar fi 80% "
                    "din ce cheltuiesc primăriile din România."
                ),
            },
            {
                "id": "sectoarele-bucurestiului",
                "severity": "note",
                "text": (
                    "Bucureștiul raportează separat pe sectoare și pe municipiu. Restul sumelor "
                    "sunt lăsate așa cum sunt depuse, fiecare cu SIRUTA lui."
                ),
            },
        ],
    }


def build_finance_documents(
    scope: str,
    years: list[int],
    retrieved_date: str,
    registry: Path,
    data_gov_2024_workbook: Path | None = None,
    arrears_workbook: str | Path | None = None,
    arrears_snapshot_date: str | None = None,
    arrears_resources: dict | None = None,
) -> tuple[dict, dict]:
    registry_document = read_registry(registry)
    uats = roster()
    if len(uats) < 3000:
        raise SystemExit(f"only {len(uats)} UATs came back; refusing to use a partial roster")
    validate_roster_against_registry(uats, shared_registry_sirutas(registry))
    prefer_registry_population(uats, shared_registry_population(registry))
    selected = select_uats_for_scope(uats, scope)

    requested_years = sorted(set(years))
    records, raw = fetch_mart_records(selected, requested_years, registry_document)
    arrears_snapshot = None
    if arrears_workbook:
        arrears_snapshot = read_arrears_workbook(
            arrears_workbook, registry_document, snapshot_date=arrears_snapshot_date
        )
        apply_arrears_snapshot(records, arrears_snapshot)
    mart = build_mart_document(
        records,
        requested_years,
        retrieved_date,
        registry_document,
        sha256_file(registry),
        sha256_json(raw),
        scope=scope,
        arrears_snapshot=arrears_snapshot,
        arrears_resources=arrears_resources,
    )

    data_gov = data_gov_2024_totals(data_gov_2024_workbook) if data_gov_2024_workbook else None
    transparenta = transparenta_national_totals(2024) if data_gov else None
    report = build_validation_report(
        mart, data_gov=data_gov, transparenta=transparenta, arrears_resources=arrears_resources
    )
    return mart, report


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=SCOPES, default="sample")
    parser.add_argument("--years", type=int, nargs="+", default=list(DEFAULT_YEARS))
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    parser.add_argument("--registry", type=Path, default=UAT_REGISTRY)
    parser.add_argument("--out-dir", type=Path, default=PACKAGE_ROOT / "data")
    parser.add_argument("--data-gov-2024-workbook", type=Path)
    parser.add_argument(
        "--data-gov-arrears-package",
        help="CKAN package_show JSON path or URL for the official data.gov.ro Arierate dataset",
    )
    parser.add_argument(
        "--data-gov-arrears-index-out",
        type=Path,
        help="also write a compact data.gov.ro Arierate UAT resource index",
    )
    parser.add_argument(
        "--arrears-workbook",
        help="official UAT arrears XLS workbook path or URL to join into matching mart years",
    )
    parser.add_argument(
        "--arrears-snapshot-date",
        help="override workbook snapshot date, YYYY-MM-DD",
    )
    parser.add_argument(
        "--existing-mart",
        type=Path,
        help=(
            "read an existing mart and rebuild only report/index unless an arrears workbook "
            "is supplied"
        ),
    )
    parser.add_argument(
        "--legacy-budget-out",
        type=Path,
        help="also write the impozit-teren buget-uat compatibility export",
    )
    args = parser.parse_args()

    arrears_resources = (
        read_arrears_resource_index(args.data_gov_arrears_package, args.retrieved_date)
        if args.data_gov_arrears_package
        else None
    )
    if args.data_gov_arrears_index_out:
        if not arrears_resources:
            raise SystemExit("--data-gov-arrears-index-out requires --data-gov-arrears-package")
        write_json(args.data_gov_arrears_index_out, arrears_resources)
        print(f"Wrote {display_path(args.data_gov_arrears_index_out)}")

    data_gov = (
        data_gov_2024_totals(args.data_gov_2024_workbook) if args.data_gov_2024_workbook else None
    )
    transparenta = transparenta_national_totals(2024) if data_gov else None

    if args.existing_mart:
        mart = json.loads(args.existing_mart.read_text(encoding="utf-8"))
        if args.arrears_workbook:
            registry_document = read_registry(args.registry)
            arrears_snapshot = read_arrears_workbook(
                args.arrears_workbook,
                registry_document,
                snapshot_date=args.arrears_snapshot_date,
            )
            changed = apply_arrears_snapshot(mart["records"], arrears_snapshot)
            if not changed:
                raise SystemExit(
                    f"{mart['id']} has no records for arrears snapshot "
                    f"{arrears_snapshot['snapshotDate'][:4]}"
                )
            mart["sourceHashes"]["dataGovArrearsWorkbookSha256"] = arrears_snapshot["source"][
                "sha256"
            ]
            mart["limitations"] = finance_limitations(
                mart["records"],
                arrears_snapshot=arrears_snapshot,
                arrears_resources=arrears_resources,
            )
            write_json(args.existing_mart, mart)
        report = build_validation_report(
            mart, data_gov=data_gov, transparenta=transparenta, arrears_resources=arrears_resources
        )
        report_path = args.out_dir / f"{report['id']}.json"
        write_json(report_path, report)
        print(f"Wrote {report_path.relative_to(REPO_ROOT)}")
        return 0

    mart, report = build_finance_documents(
        args.scope,
        args.years,
        args.retrieved_date,
        args.registry,
        data_gov_2024_workbook=args.data_gov_2024_workbook,
        arrears_workbook=args.arrears_workbook,
        arrears_snapshot_date=args.arrears_snapshot_date,
        arrears_resources=arrears_resources,
    )

    mart_path = args.out_dir / f"{mart['id']}.json"
    report_path = args.out_dir / f"{report['id']}.json"
    write_json(mart_path, mart)
    write_json(report_path, report)
    if args.legacy_budget_out:
        legacy_budget_out = (
            args.legacy_budget_out
            if args.legacy_budget_out.is_absolute()
            else REPO_ROOT / args.legacy_budget_out
        )
        legacy = build_legacy_budget_document_from_mart(mart, max(args.years))
        write_json(legacy_budget_out, legacy)
    print(f"{mart['summary']['records']} finance records, {mart['summary']['uats']} UATs")
    print(f"Wrote {mart_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")
    if args.legacy_budget_out:
        print(f"Wrote {legacy_budget_out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
