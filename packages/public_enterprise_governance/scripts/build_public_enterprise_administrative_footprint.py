"""Build an administrative aggregate from public-enterprise reference sources.

This deliberately emits UAT/authority/county aggregates, not company rows. The source layer is
currently companiidestat.ro's documented API, treated as a comparison/reference source with
CC BY 4.0 attribution. The output is small enough to commit and safe for consumer apps to load.

Usage:
    uv run python packages/public_enterprise_governance/scripts/\
build_public_enterprise_administrative_footprint.py --retrieved-date 2026-09-10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]

DOCUMENT_ID: Final[str] = "public-enterprise-administrative-footprint-2024-2026"
TRANSFORM_VERSION: Final[int] = 1
BASE_URL: Final[str] = "https://companiidestat.ro/date/v1/"
ANEXA3_URL: Final[str] = f"{BASE_URL}anexa3_summary.json"
MFIN_URL: Final[str] = f"{BASE_URL}mfin_bilanturi_2025.json"
SEARCH_URL: Final[str] = f"{BASE_URL}companii_search.json"
SUBSIDIES_URL: Final[str] = f"{BASE_URL}subventii-locale-data.json"
DEFAULT_REGISTRY: Final[Path] = REPO_ROOT / "packages/uat_registry/data/uat-registry-2026.json"
DEFAULT_OUT: Final[Path] = PACKAGE_ROOT / f"data/{DOCUMENT_ID}.json"
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
PUBLISHER: Final[str] = " / ".join(
    (
        "companiidestat.ro",
        "AMEPIP",
        "Ministerul Finantelor",
        "Institutul National de Statistica",
    )
)

COMPANY_LEVEL_EXCLUSION_TYPES = {
    "central minister",
    "local companie",
}


def read_bytes(location: str | Path) -> bytes:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    return Path(text).read_bytes()


def read_json_with_hash(location: str | Path) -> tuple[Any, str]:
    raw = read_bytes(location)
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def fold(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = text.replace("MUN.", "MUNICIPIUL").replace("MUN ", "MUNICIPIUL ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_siruta(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.lstrip("0") or "0"


def money(value: object) -> float:
    if value is None:
        return 0.0
    return round(float(value), 2)


def int_count(value: object) -> int:
    if value is None:
        return 0
    return int(round(float(value)))


def add_alias(index: dict[str, list[dict[str, Any]]], alias: str, unit: dict[str, Any]) -> None:
    key = fold(alias)
    if key:
        index[key].append(unit)


def build_authority_alias_index(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    aliases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in registry["units"]:
        name = unit["name"]
        short = unit["shortName"]
        level = unit["level"]
        for alias in (name, short, f"PRIMARIA {short}"):
            add_alias(aliases, alias, unit)

        if level == "county":
            county = unit["countyName"]
            add_alias(aliases, f"CONSILIUL JUDETEAN {county}", unit)
            add_alias(aliases, f"CONSILIUL JUDEȚEAN {county}", unit)
            add_alias(aliases, f"JUDETUL {county}", unit)
            continue

        for prefix in (
            "CONSILIUL LOCAL",
            "CONSILIUL LOCAL COMUNA",
            "CONSILIUL LOCAL ORAS",
            "CONSILIUL LOCAL ORASUL",
            "CONSILIUL LOCAL MUNICIPIUL",
            "CONSILIUL LOCAL MUNICIPIULUI",
        ):
            add_alias(aliases, f"{prefix} {short}", unit)
            add_alias(aliases, f"{prefix} {name}", unit)

        if level == "sector":
            number = re.search(r"([0-9]+)", short)
            if number:
                n = number.group(1)
                add_alias(aliases, f"CONSILIUL LOCAL AL SECTORULUI {n} BUCURESTI", unit)
                add_alias(aliases, f"CONSILIUL LOCAL SECTORUL {n}", unit)

        if normalise_siruta(unit["siruta"]) == "179132":
            add_alias(aliases, "CONSILIUL GENERAL AL MUNICIPIULUI BUCURESTI", unit)
            add_alias(aliases, "CONSILIUL LOCAL BUCURESTI", unit)

    return dict(aliases)


def county_code_for_company(
    company_ref: dict[str, Any] | None,
    county_name_to_code: dict[str, str],
) -> str | None:
    if not company_ref:
        return None
    name = company_ref.get("judet_nume")
    return county_name_to_code.get(fold(name)) if name else None


def resolve_authority(
    label: str,
    county_code: str | None,
    aliases: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str, str | None]:
    candidates = aliases.get(fold(label), [])
    if not candidates:
        return None, "unmatched-authority", None
    unique = {normalise_siruta(unit["siruta"]): unit for unit in candidates}
    candidates = list(unique.values())
    if len(candidates) == 1:
        return candidates[0], "registry-alias", None
    if county_code:
        narrowed = [unit for unit in candidates if unit["countyCode"] == county_code]
        if len(narrowed) == 1:
            return narrowed[0], "registry-alias-county", None
    options = ", ".join(sorted({f"{unit['name']} ({unit['countyCode']})" for unit in candidates}))
    return None, "ambiguous-authority", options


def authority_type(unit: dict[str, Any]) -> str:
    level = unit["level"]
    if level == "county":
        return "county-council"
    if level in {"municipality", "town", "commune", "sector"}:
        return level
    return "other-local"


def empty_metrics() -> dict[str, float | int | set[str]]:
    return {
        "companies": set(),
        "activeCompanies": set(),
        "companiesWithFinancials": set(),
        "lossMakingCompanies": set(),
        "subsidizedCompanies": set(),
        "employeeCount": 0,
        "revenueRon": 0.0,
        "profitLossRon": 0.0,
        "debtRon": 0.0,
        "subsidiesRon": 0.0,
    }


def financial_metrics(cui: str, finance_by_cui: dict[str, Any]) -> dict[str, float | int] | None:
    row = finance_by_cui.get(cui)
    if not row:
        return None
    profit_loss = money(row.get("profit_net")) - money(row.get("pierdere_neta"))
    return {
        "employeeCount": int_count(row.get("nr_salariati")),
        "revenueRon": money(row.get("cifra_afaceri") or row.get("venituri_totale")),
        "profitLossRon": round(profit_loss, 2),
        "debtRon": money(row.get("datorii")),
    }


def is_active(company: dict[str, Any], company_ref: dict[str, Any] | None) -> bool:
    state = fold(company.get("stare"))
    if "FUNCTIUNE" in state:
        return True
    if company_ref and company_ref.get("anaf_inactiv_fiscal") is True:
        return False
    onrc_state = fold(company_ref.get("stare_onrc") if company_ref else "")
    return not any(token in onrc_state for token in ("RADIATA", "FALIMENT", "INSOLVENTA"))


def status_is_loss(company: dict[str, Any], company_ref: dict[str, Any] | None) -> bool:
    return (
        fold(company.get("status") or (company_ref or {}).get("derived_status_2025")) == "PIERDERE"
    )


def add_company_metrics(
    metrics: dict[str, Any],
    cui: str,
    company: dict[str, Any],
    company_ref: dict[str, Any] | None,
    finance_by_cui: dict[str, Any],
) -> None:
    metrics["companies"].add(cui)
    if is_active(company, company_ref):
        metrics["activeCompanies"].add(cui)

    finance = financial_metrics(cui, finance_by_cui)
    if finance:
        metrics["companiesWithFinancials"].add(cui)
        metrics["employeeCount"] += finance["employeeCount"]
        metrics["revenueRon"] += finance["revenueRon"]
        metrics["profitLossRon"] += finance["profitLossRon"]
        metrics["debtRon"] += finance["debtRon"]
        if finance["profitLossRon"] < 0:
            metrics["lossMakingCompanies"].add(cui)
    elif status_is_loss(company, company_ref):
        metrics["lossMakingCompanies"].add(cui)


def add_subsidies(
    metrics_by_siruta: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    subsidies: dict[str, Any] | None,
    year: str,
) -> tuple[int, dict[str, int]]:
    if not subsidies:
        return 0, {}
    unit_by_cui = {
        str(unit["cui"]): unit for unit in registry["units"] if unit.get("cui") is not None
    }
    subsidy_rows = 0
    rows_by_siruta: dict[str, int] = defaultdict(int)
    for row in subsidies.get("years", {}).get(year, {}).get("uats", []):
        unit = unit_by_cui.get(str(row.get("cui")))
        if not unit:
            continue
        siruta = normalise_siruta(unit["siruta"])
        amount = money(row.get("total"))
        if amount <= 0:
            continue
        metrics_by_siruta[siruta]["subsidiesRon"] += amount
        rows_by_siruta[siruta] += 1
        subsidy_rows += 1
    return subsidy_rows, dict(rows_by_siruta)


def public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "companyCount": len(metrics["companies"]),
        "activeCompanyCount": len(metrics["activeCompanies"]),
        "companiesWithFinancials": len(metrics["companiesWithFinancials"]),
        "lossMakingCompanyCount": len(metrics["lossMakingCompanies"]),
        "subsidizedCompanyCount": len(metrics["subsidizedCompanies"]),
        "employeeCount": int(metrics["employeeCount"]),
        "revenueRon": round(metrics["revenueRon"], 2),
        "profitLossRon": round(metrics["profitLossRon"], 2),
        "debtRon": round(metrics["debtRon"], 2),
        "subsidiesRon": round(metrics["subsidiesRon"], 2),
    }


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def source(id_: str, url: str, role: str, license_: str, notes: str = "") -> dict[str, str]:
    result = {"id": id_, "url": url, "role": role, "license": license_}
    if notes:
        result["notes"] = notes
    return result


def build_document(
    *,
    anexa3: dict[str, Any],
    mfin: dict[str, Any],
    search: dict[str, Any],
    registry: dict[str, Any],
    subsidies: dict[str, Any] | None,
    hashes: dict[str, str | None],
    retrieved_date: str,
    subsidy_year: str = "2025",
) -> dict[str, Any]:
    aliases = build_authority_alias_index(registry)
    county_name_to_code = {
        fold(unit["countyName"]): unit["countyCode"] for unit in registry["units"]
    }
    company_ref_by_cui = {str(cui): row for cui, row in search.get("companii", {}).items()}
    finance_by_cui = {str(cui): row for cui, row in mfin.get("companii", {}).items()}
    unit_by_siruta = {normalise_siruta(unit["siruta"]): unit for unit in registry["units"]}

    authority_metrics: dict[tuple[str, str], dict[str, Any]] = defaultdict(empty_metrics)
    authority_units: dict[tuple[str, str], dict[str, Any]] = {}
    authority_methods: dict[tuple[str, str], str] = {}
    authority_labels: dict[tuple[str, str], str] = {}
    authority_source_rows: dict[tuple[str, str], int] = defaultdict(int)
    seen_company_authority: set[tuple[str, str, str]] = set()
    exclusions: dict[tuple[str, str, str | None], dict[str, Any]] = {}

    def exclude(reason: str, label: str, county_code: str | None, note: str | None = None) -> None:
        key = (reason, label, county_code)
        row = exclusions.setdefault(
            key,
            {
                "reason": reason,
                "sourceAuthorityLabel": label,
                "countyCode": county_code,
                "sourceRows": 0,
            },
        )
        row["sourceRows"] += 1
        if note:
            row["note"] = note

    for company in anexa3.get("companies", []):
        label = str(company.get("apt") or "").strip()
        if not label:
            exclude("unmatched-authority", "missing authority label", None)
            continue
        tip_apt = fold(company.get("tip_apt")).lower()
        if tip_apt in COMPANY_LEVEL_EXCLUSION_TYPES:
            reason = "central-authority" if "central" in tip_apt else "authority-company-not-uat"
            exclude(reason, label, None)
            continue

        cui = str(company.get("cui") or "").strip()
        company_ref = company_ref_by_cui.get(cui)
        county_code = county_code_for_company(company_ref, county_name_to_code)
        unit, method, note = resolve_authority(label, county_code, aliases)
        if not unit:
            exclude(method, label, county_code, note)
            continue

        siruta = normalise_siruta(unit["siruta"])
        authority_key = (siruta, fold(label))
        duplicate_key = (siruta, fold(label), cui)
        if duplicate_key in seen_company_authority:
            exclude("duplicate-company-authority", label, unit["countyCode"])
            continue
        seen_company_authority.add(duplicate_key)

        authority_units[authority_key] = unit
        authority_methods[authority_key] = method
        authority_labels[authority_key] = label
        authority_source_rows[authority_key] += 1
        add_company_metrics(
            authority_metrics[authority_key],
            cui,
            company,
            company_ref,
            finance_by_cui,
        )

    for row in (subsidies or {}).get("operators_2025", []):
        cui = str(row.get("cui") or "")
        if not cui:
            continue
        for metrics in authority_metrics.values():
            if cui in metrics["companies"]:
                metrics["subsidizedCompanies"].add(cui)

    uat_metrics: dict[str, dict[str, Any]] = defaultdict(empty_metrics)
    authority_count_by_siruta: dict[str, int] = defaultdict(int)
    for (siruta, _label), metrics in authority_metrics.items():
        target = uat_metrics[siruta]
        for key in (
            "companies",
            "activeCompanies",
            "companiesWithFinancials",
            "lossMakingCompanies",
            "subsidizedCompanies",
        ):
            target[key].update(metrics[key])
        for key in ("employeeCount", "revenueRon", "profitLossRon", "debtRon"):
            target[key] += metrics[key]
        authority_count_by_siruta[siruta] += 1

    subsidy_rows, subsidy_rows_by_siruta = add_subsidies(
        uat_metrics, registry, subsidies, subsidy_year
    )

    for _siruta, metrics in uat_metrics.items():
        metrics["subsidiesRon"] = round(metrics["subsidiesRon"], 2)

    authorities = []
    for authority_key, metrics in sorted(authority_metrics.items()):
        siruta, label_key = authority_key
        unit = authority_units[authority_key]
        subsidy_rows_for_uat = subsidy_rows_by_siruta.get(siruta, 0)
        row = {
            "authorityKey": f"siruta:{siruta}:{label_key.lower().replace(' ', '-')[:80]}",
            "authorityName": unit["name"],
            "sourceAuthorityLabel": authority_labels[authority_key],
            "authorityType": authority_type(unit),
            "ownershipLevel": "local",
            "siruta": siruta,
            "countyCode": unit["countyCode"],
            "countyName": unit["countyName"],
            "registryMatchMethod": authority_methods[authority_key],
            **public_metrics(metrics),
            "sourceCoverage": {
                "amepipCompanies": authority_source_rows[authority_key],
                "mfinCompanies": len(metrics["companiesWithFinancials"]),
                "subsidyRows": subsidy_rows_for_uat,
            },
            "provenance": {
                "source": "companiidestat-anexa3-mfin",
                "locator": f"{ANEXA3_URL}; {MFIN_URL}",
                "confidence": "derived",
                "note": (
                    "Authority-level aggregate from companiidestat Anexa 3 local-company "
                    "rows joined to MFin financials by CUI."
                ),
            },
        }
        authorities.append(row)

    uats = []
    for siruta, metrics in sorted(uat_metrics.items(), key=lambda item: item[0]):
        unit = unit_by_siruta[siruta]
        public = public_metrics(metrics)
        if public["companyCount"] == 0 and public["subsidiesRon"] <= 0:
            continue
        uats.append(
            {
                "siruta": siruta,
                "name": unit["name"],
                "level": unit["level"],
                "countyCode": unit["countyCode"],
                "countyName": unit["countyName"],
                "population": unit.get("population"),
                "authorityCount": authority_count_by_siruta.get(siruta, 0),
                **public,
            }
        )

    county_metrics: dict[str, dict[str, Any]] = defaultdict(empty_metrics)
    county_uats: dict[str, set[str]] = defaultdict(set)
    county_authorities: dict[str, int] = defaultdict(int)
    for row in uats:
        county_code = row["countyCode"]
        metrics = county_metrics[county_code]
        for key, row_key in (
            ("companies", "companyCount"),
            ("activeCompanies", "activeCompanyCount"),
            ("companiesWithFinancials", "companiesWithFinancials"),
            ("lossMakingCompanies", "lossMakingCompanyCount"),
            ("subsidizedCompanies", "subsidizedCompanyCount"),
        ):
            start = len(metrics[key])
            metrics[key].update(f"{row['siruta']}:{i}" for i in range(start, start + row[row_key]))
        for key in ("employeeCount", "revenueRon", "profitLossRon", "debtRon", "subsidiesRon"):
            metrics[key] += row[key]
        county_uats[county_code].add(row["siruta"])
        county_authorities[county_code] += row["authorityCount"]

    counties = []
    for county_code, metrics in sorted(county_metrics.items()):
        county_name = next(
            unit["countyName"] for unit in registry["units"] if unit["countyCode"] == county_code
        )
        public = public_metrics(metrics)
        counties.append(
            {
                "countyCode": county_code,
                "countyName": county_name,
                "uats": sum(1 for unit in registry["units"] if unit["countyCode"] == county_code),
                "uatsWithCompanies": len(county_uats[county_code]),
                "authorityCount": county_authorities[county_code],
                **public,
            }
        )

    summary_metrics = empty_metrics()
    for row in uats:
        for key, row_key in (
            ("companies", "companyCount"),
            ("activeCompanies", "activeCompanyCount"),
            ("companiesWithFinancials", "companiesWithFinancials"),
            ("lossMakingCompanies", "lossMakingCompanyCount"),
            ("subsidizedCompanies", "subsidizedCompanyCount"),
        ):
            start = len(summary_metrics[key])
            summary_metrics[key].update(
                f"{row['siruta']}:{i}" for i in range(start, start + row[row_key])
            )
        for key in ("employeeCount", "revenueRon", "profitLossRon", "debtRon", "subsidiesRon"):
            summary_metrics[key] += row[key]

    duplicate_rows = sum(
        row["sourceRows"]
        for row in exclusions.values()
        if row["reason"] == "duplicate-company-authority"
    )
    unmatched_rows = sum(
        row["sourceRows"]
        for row in exclusions.values()
        if row["reason"] in {"unmatched-authority", "ambiguous-authority"}
    )
    matched_companies = sum(len(metrics["companies"]) for metrics in authority_metrics.values())
    summary = {
        "sourceCompanies": len(anexa3.get("companies", [])),
        "matchedCompanies": matched_companies,
        "duplicateCompanyRows": duplicate_rows,
        "unmatchedCompanies": unmatched_rows,
        "authorities": len(authorities),
        "uats": len(uats),
        "counties": len(counties),
        "companiesWithFinancials": len(summary_metrics["companiesWithFinancials"]),
        "subsidizedUats": subsidy_rows,
        **public_metrics(summary_metrics),
    }

    return {
        "$schema": "../schema/public-enterprise-administrative-footprint.schema.json",
        "id": DOCUMENT_ID,
        "title": "Public-enterprise administrative footprint by authority, UAT and county",
        "publisher": PUBLISHER,
        "scope": "administrative-aggregate",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "license": (
            "CC BY 4.0 for companiidestat.ro API data; upstream official-source reuse "
            "limits still apply."
        ),
        "attribution": "companiidestat.ro",
        "sources": [
            source("companiidestat-anexa3-summary", ANEXA3_URL, "comparison", "CC BY 4.0"),
            source("companiidestat-mfin-bilanturi-2025", MFIN_URL, "comparison", "CC BY 4.0"),
            source("companiidestat-companii-search", SEARCH_URL, "comparison", "CC BY 4.0"),
            source(
                "companiidestat-subventii-locale",
                SUBSIDIES_URL,
                "comparison",
                "CC BY 4.0",
                "Partial large-UAT subsidy coverage; mapped by payer UAT CUI where available.",
            ),
            source(
                "uat-registry-2026",
                "https://data.gov.ro/dataset/721c9059-5f87-4c79-9854-a1d5c18f58d5",
                "registry",
                "Creative Commons Attribution 4.0",
            ),
        ],
        "sourceHashes": hashes,
        "registry": {
            "uatRegistryId": registry["id"],
            "uatRegistryPeriod": registry["period"],
        },
        "transform": {
            "script": (
                "packages/public_enterprise_governance/scripts/"
                "build_public_enterprise_administrative_footprint.py"
            ),
            "version": TRANSFORM_VERSION,
        },
        "provenance": {
            "source": "companiidestat-api-v1",
            "locator": BASE_URL,
            "confidence": "derived",
            "note": (
                "Civic API snapshot aggregated to administrative authorities and joined "
                "to the shared UAT registry; no company rows are emitted."
            ),
        },
        "summary": summary,
        "authorities": authorities,
        "uats": uats,
        "counties": counties,
        "exclusions": sorted(
            exclusions.values(), key=lambda row: (row["reason"], row["sourceAuthorityLabel"])
        ),
        "limitations": [
            limitation(
                "companiidestat-reference-not-primary",
                "material",
                ["all-metrics"],
                (
                    "This aggregate is derived from the companiidestat.ro API as a "
                    "reference layer; official AMEPIP and MFin files remain the preferred "
                    "source of truth for future production imports."
                ),
            ),
            limitation(
                "authority-name-matching-conservative",
                "material",
                ["authority-join"],
                (
                    "Authority labels are matched only through conservative aliases against "
                    "the shared UAT registry. Ambiguous or unmatched labels are reported as "
                    "exclusions."
                ),
            ),
            limitation(
                "subsidy-coverage-partial",
                "material",
                ["subsidiesRon"],
                (
                    "Local subsidy data covers a partial set of larger UATs and is joined "
                    "by payer UAT CUI where available."
                ),
            ),
            limitation(
                "bucharest-municipality-not-administrativ-polygon",
                "material",
                ["administrativ-consumer"],
                (
                    "Bucharest municipality-level rows use SIRUTA 179132; the administrativ "
                    "map carries the six sectors, so the browser adapter does not fan out "
                    "city-level rows to sectors."
                ),
            ),
        ],
        "nextSlice": {
            "scope": "official-source replacement",
            "deliverable": (
                "Replace the comparison aggregate with the same contract built from official "
                "AMEPIP annexes and MFin/data.gov.ro financial statements."
            ),
            "doneWhen": (
                "The administrativ app consumes the same SIRUTA-aligned aggregate contract "
                "with official-source hashes and a comparison-only companiidestat validation "
                "report."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anexa3", default=ANEXA3_URL)
    parser.add_argument("--mfin", default=MFIN_URL)
    parser.add_argument("--search", default=SEARCH_URL)
    parser.add_argument("--subsidies", default=SUBSIDIES_URL)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--retrieved-date", required=True)
    parser.add_argument("--subsidy-year", default="2025")
    args = parser.parse_args()

    anexa3, anexa3_hash = read_json_with_hash(args.anexa3)
    mfin, mfin_hash = read_json_with_hash(args.mfin)
    search, search_hash = read_json_with_hash(args.search)
    subsidies, subsidies_hash = read_json_with_hash(args.subsidies)
    registry, registry_hash = read_json_with_hash(args.registry)

    document = build_document(
        anexa3=anexa3,
        mfin=mfin,
        search=search,
        registry=registry,
        subsidies=subsidies,
        hashes={
            "anexa3SummarySha256": anexa3_hash,
            "mfinBilanturiSha256": mfin_hash,
            "companiiSearchSha256": search_hash,
            "subventiiLocaleSha256": subsidies_hash,
            "uatRegistrySha256": registry_hash,
        },
        retrieved_date=args.retrieved_date,
        subsidy_year=args.subsidy_year,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out} with {document['summary']['uats']} UATs, "
        f"{document['summary']['companyCount']} companies"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
