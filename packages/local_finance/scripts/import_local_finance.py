"""Build the shared local finance mart from Transparenta budget execution.

The first committed slice is deliberately small: ten UATs over 2023-2025, enough to lock
down the data shape, classification choices and validation report before moving the full
national budget file out of `simulators/impozit-teren`.

Usage:
    uv run python packages/local_finance/scripts/import_local_finance.py \
        --data-gov-2024-workbook /tmp/local-finance/situatia-veniturilor-cheltuielilor-2024.xlsx
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
API: Final[str] = "https://api.transparenta.eu/graphql"
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
YEAR: Final[int] = 2025
DEFAULT_YEARS: Final[tuple[int, ...]] = (2023, 2024, 2025)
UAT_REGISTRY: Final[Path] = (
    REPO_ROOT / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"
)
TRANSFORM_VERSION: Final[str] = "2026-09-08"

DATA_GOV_2024_URL: Final[str] = (
    "https://data.gov.ro/dataset/c0d25ff7-27d5-4c31-9809-540f77b20180/resource/"
    "aac89795-56f0-41ee-a631-26695f73c5d6/download/"
    "situaia-veniturilor-i-cheltuielilor-2024.xlsx"
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
            f'  u{uat}: aggregatedLineItems(filter: {{account_category: {category}, '
            f"report_type: PRINCIPAL_AGGREGATED, {expense_filter}uat_ids: [\"{uat}\"], "
            f'report_period: {{type: YEAR, selection: {{interval: {{start: "{year}", '
            f'end: "{year}"}}}}}}}}, limit: 400, offset: {int(offset)}) '
            "{ nodes { functional_code economic_code amount } pageInfo { hasNextPage } }"
        )
    return "query Batch {\n" + "\n".join(parts) + "\n}"


def all_rows(
    uat_id: str, category: str, year: int, expense_type: str | None = None
) -> list[dict]:
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
        query = batch_query(
            [u["uatId"] for u in chunk], category, year, expense_type=expense_type
        )
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
    return {
        siruta: totals(rows)
        for siruta, rows in fetch_line_items(uats, category, year).items()
    }


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
    return sorted(records, key=lambda row: (row["year"], int(row["siruta"]))), raw


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


def finance_limitations(records: list[dict]) -> list[dict]:
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
        {
            "id": "arrears-not-imported-yet",
            "severity": "material",
            "affects": ["arrearsRon"],
            "text": (
                "The first slice does not import arrears. The field is present and null so "
                "downstream consumers can depend on the schema without mistaking missing arrears "
                "for zero arrears."
            ),
        },
    ]
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
) -> dict:
    sample = [
        {"siruta": siruta, "role": role}
        for siruta, role in SAMPLE_UATS
        if any(row["siruta"] == siruta for row in records)
    ]
    return {
        "$schema": "../schema/local-finance-mart.schema.json",
        "id": f"local-finance-mart-sample-{min(years)}-{max(years)}",
        "title": f"Local finance mart sample, {min(years)}-{max(years)}",
        "publisher": "transparenta.eu",
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
        "sourceHashes": {
            "transparentaResponsesSha256": transparenta_sha256,
            "uatRegistrySha256": registry_sha256,
        },
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
        "limitations": finance_limitations(records),
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
                "No data.gov.ro workbook was supplied, so the first slice records the "
                "comparison hook only."
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


def build_validation_report(
    mart: dict, data_gov: dict | None = None, transparenta: dict | None = None
) -> dict:
    records = mart["records"]
    roles = {row["siruta"]: row["sampleRole"] for row in records}
    commune_counties = {
        row["countyCode"]
        for row in records
        if row["sampleRole"] == "rural-commune" and row["level"] == "commune"
    }
    scope_ok = (
        mart["summary"]["uats"] == 10
        and "county-seat" in roles.values()
        and "bucharest-sector" in roles.values()
        and len(commune_counties) >= 3
    )
    all_have_finance = all(row["revenueRon"] > 0 or row["spendingRon"] > 0 for row in records)
    all_registry_matched = mart["summary"]["registryMatchedUats"] == mart["summary"]["uats"]
    development_missing_years = [
        year["year"] for year in mart["summary"]["byYear"] if year["developmentSpendingRon"] == 0
    ]
    checks = [
        {
            "id": "sample-scope",
            "status": "pass" if scope_ok else "fail",
            "text": (
                "Sample covers ten UATs over three years, including a county seat, a Bucharest "
                "sector and rural communes from at least three counties."
            ),
            "metrics": {
                "uats": mart["summary"]["uats"],
                "years": mart["summary"]["years"],
                "ruralCommuneCounties": len(commune_counties),
            },
        },
        {
            "id": "registry-join",
            "status": "pass" if all_registry_matched else "fail",
            "text": "Every sampled SIRUTA joins to the shared UAT registry and carries a CUI.",
            "metrics": {
                "registryMatchedUats": mart["summary"]["registryMatchedUats"],
                "sampleUats": mart["summary"]["uats"],
            },
        },
        {
            "id": "transparenta-line-items",
            "status": "pass" if all_have_finance else "fail",
            "text": "Every sampled UAT-year has at least one revenue or spending line item.",
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
                "Transparenta development-spending expense-type rows are present for each sampled "
                "year."
                if not development_missing_years
                else (
                    "Transparenta returns no development-spending expense-type rows for at least "
                    "one sampled year; the mart keeps those fields as source-missing zeros with a "
                    "named limitation."
                )
            ),
            "metrics": {
                "missingYears": ",".join(map(str, development_missing_years))
                if development_missing_years
                else None
            },
        },
        comparison_check(data_gov, transparenta),
    ]
    counts = Counter(check["status"] for check in checks)
    return {
        "$schema": "../schema/local-finance-validation-report.schema.json",
        "id": f"local-finance-validation-report-{mart['periodStart']}-{mart['periodEnd']}",
        "title": f"Local finance mart validation report, {mart['periodStart']}-{mart['periodEnd']}",
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
        "limitations": mart["limitations"],
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


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=list(DEFAULT_YEARS))
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    parser.add_argument("--registry", type=Path, default=UAT_REGISTRY)
    parser.add_argument("--out-dir", type=Path, default=PACKAGE_ROOT / "data")
    parser.add_argument("--data-gov-2024-workbook", type=Path)
    args = parser.parse_args()

    registry_document = read_registry(args.registry)
    uats = roster()
    if len(uats) < 3000:
        raise SystemExit(f"only {len(uats)} UATs came back; refusing to use a partial roster")
    validate_roster_against_registry(uats, shared_registry_sirutas(args.registry))
    prefer_registry_population(uats, shared_registry_population(args.registry))
    selected = select_sample_uats(uats)

    years = sorted(set(args.years))
    records, raw = fetch_mart_records(selected, years, registry_document)
    mart = build_mart_document(
        records,
        years,
        args.retrieved_date,
        registry_document,
        sha256_file(args.registry),
        sha256_json(raw),
    )

    data_gov = (
        data_gov_2024_totals(args.data_gov_2024_workbook)
        if args.data_gov_2024_workbook
        else None
    )
    transparenta = transparenta_national_totals(2024) if data_gov else None
    report = build_validation_report(mart, data_gov=data_gov, transparenta=transparenta)

    mart_path = args.out_dir / f"{mart['id']}.json"
    report_path = args.out_dir / f"{report['id']}.json"
    write_json(mart_path, mart)
    write_json(report_path, report)
    print(f"{mart['summary']['records']} finance records, {mart['summary']['uats']} UATs")
    print(f"Wrote {mart_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
