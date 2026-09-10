"""Read the state-company indicator workbook into one row per company.

The workbook has three sheets. `Indicatori calculati` carries the financial ratios per company
and year; `Indicatori formular` carries the non-financial indicators, including the one this
simulator needs — the full-time-equivalent headcount; `kpi` is the indicator dictionary. This
import keeps identity, activity (CAEN), status and headcount, and drops the ratio columns: a
consolidation argument is about how many operators exist and how big they are, not about their
ROA.

Headcount is the latest year a company reports it. It is present for a minority of companies,
so every employee total this feeds is a **lower bound**, carried as a limitation rather than
smoothed over.

Usage:
    uv run python scripts/import_soe.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "companii-stat-finnefin.xlsx"
SEARCH = ROOT / "sources" / "companii-search-2026-09-10.json"
BILANTURI = ROOT / "sources" / "mfin-bilanturi-2025.json"
OWNERS = ROOT / "sources" / "anexa3-owner-extract.json"
SUBVENTII = ROOT / "sources" / "subventii-locale-data.json"
REGISTRY = ROOT.parents[1] / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"
OUT = ROOT / "data" / "companii-2025.json"

FINANCIAL_SHEET = "Indicatori calculati"
NONFINANCIAL_SHEET = "Indicatori formular"
HEADCOUNT = "Număr de angajați cu echivalent normă întreagă"

SEARCH_URL = "https://companiidestat.ro/date/v1/companii_search.json"
BILANTURI_URL = "https://companiidestat.ro/date/v1/mfin_bilanturi_2025.json"
OWNERS_URL = "https://companiidestat.ro/date/v1/anexa3_summary.json"
SUBVENTII_URL = "https://companiidestat.ro/date/v1/subventii-locale-data.json"

# Company ids whose reported headcount is a data-entry error, checked against the workbook
# itself. A generic threshold would quietly discard a genuinely large operator, so the guard
# is this explicit table: each row is one company, one reported figure, and the reason it is
# excluded. Excluded, not dropped — the entries travel in dataQuality, so a reader can see
# what was removed and argue with it.
HEADCOUNT_OUTLIERS = {
    1217: {
        "cui": 27811667,
        "name": "UTILITĂŢI ŞI SERVICII PUBLICE MURIGHIOL SRL",
        "reported": 10776,
        "year": 2023,
        "reason": "2019–2022 report no headcount; the 2023 figure exceeds the commune's "
        "population several times over and is an entry error in the source.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_sheet(name: str) -> list[dict]:
    import openpyxl  # noqa: PLC0415

    workbook = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    rows = workbook[name].iter_rows(values_only=True)
    header = next(rows)
    return [dict(zip(header, row, strict=False)) for row in rows if row and row[0]]


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def load_county_by_name() -> dict[str, str]:
    """Folded county name -> county code, from the shared SIRUTA registry."""
    units = json.loads(REGISTRY.read_text(encoding="utf-8"))["units"]
    pairs = {}
    for unit in units:
        if unit.get("level") == "county" and unit.get("countyCode"):
            pairs[fold(unit["countyName"])] = unit["countyCode"]
    return pairs


def load_county_search() -> dict[str, dict]:
    """CUI -> row of the companiidestat.ro search snapshot, which carries the county name.

    The snapshot is committed with the workbook so the import stays offline and reproducible;
    refresh it with the documented API under CC BY 4.0 and re-pin the checksum below.
    """
    if not SEARCH.exists():
        raise SystemExit(f"missing source {SEARCH}")
    payload = json.loads(SEARCH.read_text(encoding="utf-8"))
    rows = payload.get("companii", payload)
    return (
        {str(row["cui"]): row for row in rows.values()}
        if isinstance(rows, dict)
        else {str(row["cui"]): row for row in rows}
    )


def load_owners() -> dict[str, dict]:
    """CUI -> owning authority (apt, tip_apt), extracted from the AMEPIP anexa3 list.

    The full anexa3 download is 8 MB; the committed extract keeps only identity and owner,
    and carries the original file's SHA-256 so the extraction can be checked.
    """
    if not OWNERS.exists():
        raise SystemExit(f"missing source {OWNERS}")
    payload = json.loads(OWNERS.read_text(encoding="utf-8"))
    return payload["companies"]


def load_subventii() -> dict[str, float]:
    """CUI -> reported subsidy (RON, 2025) from the committed subventii snapshot."""
    if not SUBVENTII.exists():
        raise SystemExit(f"missing source {SUBVENTII}")
    payload = json.loads(SUBVENTII.read_text(encoding="utf-8"))
    return {
        str(row["cui"]): float(row.get("subv") or 0) for row in payload.get("operators_2025", [])
    }


def load_bilanturi() -> dict[str, dict]:
    """CUI -> MFin financial statements, from the committed bilanturi snapshot.

    The snapshot is derived by companiidestat.ro from the data.gov.ro financial statements,
    published under CC BY 4.0; it carries revenue, net result, debt and an official headcount
    (nr_salariati). Committed with the other sources so the import stays offline.
    """
    if not BILANTURI.exists():
        raise SystemExit(f"missing source {BILANTURI}")
    payload = json.loads(BILANTURI.read_text(encoding="utf-8"))
    return {str(cui): row for cui, row in payload.get("companii", {}).items()}


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing source {SOURCE}")

    financial = load_sheet(FINANCIAL_SHEET)
    nonfinancial = load_sheet(NONFINANCIAL_SHEET)
    county_by_name = load_county_by_name()
    search = load_county_search()
    bilanturi = load_bilanturi()
    owners = load_owners()
    subventii = load_subventii()

    headcount: dict[int, dict[int, float]] = collections.defaultdict(dict)
    for row in nonfinancial:
        value = row.get(HEADCOUNT)
        if value is not None:
            headcount[row["company_id"]][row["year"]] = value

    companies: dict[int, dict] = {}
    for row in financial:
        company = companies.setdefault(
            row["company_id"],
            {
                "id": row["company_id"],
                "cui": row["cui"],
                "name": row["company"],
                "registrationNumber": row["registration_number"],
                "caen": (row["CAEN(ONRC)"] or "").strip() or None,
                "status": row["status"],
            },
        )
        # Headcount precedence: the official MFin figure first, the workbook form only where
        # MFin has no row. The workbook outlier stays excluded as a source, but a company it
        # touched can still carry a headcount from MFin.
        mfin = bilanturi.get(str(row["cui"]))
        mfin_headcount = mfin.get("nr_salariati") if mfin else None
        years = headcount.get(row["company_id"], {})
        reported = years[max(years)] if years else None
        if mfin_headcount is not None:
            company["employees"] = mfin_headcount
            company["employeesSource"] = "mfin"
        elif reported is not None and row["company_id"] not in HEADCOUNT_OUTLIERS:
            company["employees"] = reported
            company["employeesYear"] = max(years)
            company["employeesSource"] = "formular"
        if mfin:
            company["revenueRon"] = mfin.get("cifra_afaceri")
            company["netResultRon"] = (mfin.get("profit_net") or 0) - (
                mfin.get("pierdere_neta") or 0
            )
            company["debtRon"] = mfin.get("datorii")

    unmatched_counties: list[dict] = []
    unmatched_owners: list[dict] = []
    for company in companies.values():
        match = search.get(str(company["cui"]))
        name = match.get("judet_nume") if match else None
        county = county_by_name.get(fold(name or "")) if name else None
        if match and not county:
            unmatched_counties.append(
                {"cui": company["cui"], "name": company["name"], "reportedCounty": name}
            )
        if county:
            company["county"] = county
            company["countySource"] = "companiidestat"
        owner = owners.get(str(company["cui"]))
        if owner:
            company["owner"] = owner.get("apt")
            company["ownerType"] = owner.get("tip_apt")
        else:
            unmatched_owners.append({"cui": company["cui"], "name": company["name"]})
        subsidy = subventii.get(str(company["cui"]))
        if subsidy is not None:
            company["subsidyRon"] = subsidy

    rows = sorted(companies.values(), key=lambda c: c["name"])
    by_status = collections.Counter(c["status"] for c in rows)
    with_headcount = sum(1 for c in rows if c.get("employees") is not None)

    payload = {
        "$schema": "../schema/companii.schema.json",
        "id": "companii-stat-2025",
        "title": "Companiile de stat: identitate, activitate și angajați",
        "publisher": "Cristian Nichifor",
        "period": "2019-2024",
        "provenance": {
            "source": "companii-stat-finnefin",
            "locator": "foaia Indicatori calculati (identitate, CAEN, status) și foaia "
            "Indicatori formular (Număr de angajați cu echivalent normă întreagă)",
            "confidence": "verbatim",
            "note": "Angajații sunt ultimul an raportat de fiecare companie, cu excepțiile "
            "din dataQuality. Fișierul sursă este reținut în sources/ cu amprenta SHA-256.",
        },
        "countySource": {
            "source": "companiidestat-search",
            "url": SEARCH_URL,
            "license": "CC BY 4.0",
            "confidence": "derived",
            "note": "Județul vine din snapshotul committed al companiidestat.ro "
            "companii_search.json, potrivit pe CUI. Este județul de înregistrare a "
            "companiei (sediul), nu teritoriul de servire. Nepotrivirile sunt listate în "
            "dataQuality, nu ghicite.",
            "snapshotChecksum": {"sha256": sha256(SEARCH), "file": SEARCH.name},
        },
        "financialsSource": {
            "source": "mfin-bilanturi-2025",
            "url": BILANTURI_URL,
            "license": "CC BY 4.0",
            "confidence": "derived",
            "note": "Veniturile, rezultatul net, datoriile și efectivul oficial (nr_salariati) "
            "vin din bilanțurile MFin publicate pe data.gov.ro, potrivite pe CUI prin "
            "companiidestat.ro. Acolo unde MFin are efectiv, el este folosit înaintea "
            "formularului; unde nu are rând, compania rămâne fără cifre financiare.",
            "snapshotChecksum": {"sha256": sha256(BILANTURI), "file": BILANTURI.name},
        },
        "ownerSource": {
            "source": "amepip-anexa3",
            "url": OWNERS_URL,
            "license": "CC BY 4.0",
            "confidence": "verbatim",
            "note": "Proprietarul (apt) vine din lista AMEPIP Anexa 3, păstrată ca extras compact; "
            "amprenta fișierului original este în extras. Companiile fără rând sunt listate în "
            "dataQuality, nu ghicite.",
            "snapshotChecksum": {"sha256": sha256(OWNERS), "file": OWNERS.name},
        },
        "subsidySource": {
            "source": "subventii-locale-2025",
            "url": SUBVENTII_URL,
            "license": "CC BY 4.0",
            "confidence": "derived",
            "note": "Subvenția vine din raportarea per firmă 2025 (Anexe SFA 2025, col. Subvenții "
            "și transferuri). Lista acoperă operatorii raportați, nu orice subvenție posibilă; "
            "absența unui rând nu înseamnă că o companie nu primește subvenții.",
            "snapshotChecksum": {"sha256": sha256(SUBVENTII), "file": SUBVENTII.name},
        },
        "sourceChecksum": {"sha256": sha256(SOURCE), "file": SOURCE.name},
        "dataQuality": {
            "headcountExcluded": [
                {"companyId": company_id, **entry}
                for company_id, entry in sorted(HEADCOUNT_OUTLIERS.items())
            ],
            "unmatchedCounties": sorted(unmatched_counties, key=lambda c: c["name"]),
            "unmatchedOwners": sorted(unmatched_owners, key=lambda c: c["name"]),
        },
        "summary": {
            "companies": len(rows),
            "withHeadcount": with_headcount,
            "byStatus": dict(by_status.most_common()),
        },
        "companies": rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} companies ({with_headcount} with headcount) -> {OUT}")


if __name__ == "__main__":
    main()
