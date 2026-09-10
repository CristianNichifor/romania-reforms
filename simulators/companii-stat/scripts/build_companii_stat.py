"""State companies, clustered by activity, with a one-operator-per-region scenario.

The state's company portfolio is not one portfolio. It is a few hundred water operators, a
hundred-plus waste operators, dozens of landscaping firms and thermal plants and road builders,
each in its own commune, town or county, and beside them the strategic national holdings
(electricity, weapons, airports) that are a different argument entirely.

This groups the companies by four-digit CAEN and applies the same rule `deconcentrare` applies
to the deconcentrated services: for the **network utilities whose service area is a region or a
basin** — water, waste, wastewater, thermal, forestry, roads, landscaping — one operator per
development region, eight instead of however many exist. Everything else is reported and left
alone.

The choice of which activities are regionalisable is a policy judgement, not a fact in the
source, so the tier table is marked `assumed` in provenance and is one editable list at the top
of this file. The counts of companies, headcounts and statuses are verbatim or derived.

Headcount is a lower bound: only a minority of companies report it, and the total is over what
the register actually contains, never over an estimate.

Usage:
    uv run python scripts/build_companii_stat.py
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = ROOT / "data" / "companii-2025.json"
REGION_MAP = ROOT.parents[1] / "simulators" / "justitie" / "data" / "curti-apel-regiuni.json"
OUT = ROOT / "data" / "companii-stat.json"

REGIONS = 8
MICRO = 20

CAEN_NAMES = {
    "3600": "Captarea, tratarea și distribuția apei",
    "3811": "Colectarea deșeurilor nepericuloase",
    "3700": "Colectarea și epurarea apelor uzate",
    "3530": "Furnizarea de abur și aer condiționat",
    "0210": "Silvicultură și alte activități forestiere",
    "4211": "Lucrări de construcții a drumurilor și autostrăzilor",
    "8130": "Activități de întreținere peisagistică",
    "4931": "Transporturi urbane, suburbane și metropolitane de călători",
    "3511": "Producția de energie electrică",
    "2540": "Fabricarea armamentului și muniției",
    "5223": "Activități de servicii anexe transporturilor aeriene",
    "6832": "Administrarea imobilelor pe bază de tarife sau contract",
    "4120": "Lucrări de construcții a clădirilor rezidențiale și nerezidențiale",
    "8129": "Alte activități de curățenie",
    "6820": "Închirierea și subînchirierea bunurilor imobiliare proprii",
    "8010": "Activități de protecție și gardă",
    "5222": "Activități de servicii anexe transportului pe apă",
    "9411": "Activități ale organizațiilor patronale și profesionale",
}

# caen -> tier. Only "regional" is merged; everything else is reported.
TIERS = {
    "3600": "regional",
    "3811": "regional",
    "3700": "regional",
    "3530": "regional",
    "0210": "regional",
    "4211": "regional",
    "8130": "regional",
    "4931": "local",
    "3511": "national",
    "2540": "national",
    "5223": "national",
}


def load_region_of_county() -> dict[str, str]:
    """County code -> development region, reused from the justitie variant."""
    regions = json.loads(REGION_MAP.read_text(encoding="utf-8"))["regions"]
    return {code: region["region"] for region in regions for code in region["counties"]}


def regionalization(caen: str, companies: list[dict]) -> list[dict]:
    """The proposed operators for one regional cluster: seat county, named absorber, absorbed.

    The rule, in a paragraph: companies are grouped by their registration county, folded into
    the eight development regions; the seat is the county in the region with the most companies
    in the activity (ties: largest headcount sum, then code); the absorber is the largest
    company there by reported headcount — and where none report a headcount, the operator is
    left unnamed rather than guessed.
    """
    region_of_county = load_region_of_county()
    by_region: dict[str, dict[str, list[dict]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for company in companies:
        county = company.get("county")
        if not county:
            continue
        region = region_of_county.get(county, "?").strip()
        by_region[region][county].append(company)

    out = []
    for region, by_county in sorted(by_region.items()):
        seat = max(
            by_county,
            key=lambda county: (
                len(by_county[county]),
                sum(c.get("employees") or 0 for c in by_county[county]),
                county,
            ),
        )
        with_headcount = [c for c in by_county[seat] if c.get("employees") is not None]
        absorber = max(with_headcount, key=lambda c: c["employees"]) if with_headcount else None
        members = [c for county in by_county.values() for c in county]
        absorbed = [c for c in members if absorber is None or c["cui"] != absorber["cui"]]
        out.append(
            {
                "region": region,
                "seatCounty": seat,
                "absorber": {
                    "cui": absorber["cui"],
                    "name": absorber["name"],
                    "employees": absorber["employees"],
                }
                if absorber
                else None,
                "absorbedCount": len(absorbed),
                "absorbed": sorted(
                    (
                        {
                            "cui": c["cui"],
                            "name": c["name"],
                            "county": c.get("county"),
                            "owner": c.get("owner"),
                        }
                        for c in absorbed
                    ),
                    key=lambda c: c["name"],
                ),
            }
        )
    return out


def main() -> None:
    source = json.loads(COMPANIES.read_text(encoding="utf-8"))

    clusters: dict[str, dict] = {}
    for company in source["companies"]:
        caen = (company.get("caen") or "")[:4] or "????"
        cluster = clusters.setdefault(
            caen,
            {
                "caen": caen,
                "name": CAEN_NAMES.get(caen, f"CAEN {caen}"),
                "companies": 0,
                "employees": 0,
                "headcountKnown": 0,
                "micro": 0,
                "revenueRon": 0,
                "lossCount": 0,
                "debtRon": 0,
                "distinctOwners": 0,
                "subsidisedCount": 0,
                "subsidyRon": 0,
                "_owners": set(),
            },
        )
        cluster["companies"] += 1
        employees = company.get("employees")
        if employees is not None:
            cluster["employees"] += employees
            cluster["headcountKnown"] += 1
            if employees < MICRO:
                cluster["micro"] += 1
        revenue = company.get("revenueRon")
        if revenue is not None:
            cluster["revenueRon"] += revenue
        result = company.get("netResultRon")
        if result is not None and result < 0:
            cluster["lossCount"] += 1
        debt = company.get("debtRon")
        if debt is not None:
            cluster["debtRon"] += debt
        owner = company.get("owner")
        if owner:
            cluster["_owners"].add(owner)
        subsidy = company.get("subsidyRon")
        if subsidy is not None:
            cluster["subsidyRon"] += subsidy
            cluster["subsidisedCount"] += 1

    out = []
    companies_by_caen: dict[str, list[dict]] = collections.defaultdict(list)
    for company in source["companies"]:
        companies_by_caen[(company.get("caen") or "")[:4] or "????"].append(company)
    for cluster in clusters.values():
        cluster["distinctOwners"] = len(cluster.pop("_owners"))
        tier = TIERS.get(cluster["caen"], "other")
        cluster["tier"] = tier
        cluster["proposed"] = REGIONS if tier == "regional" else cluster["companies"]
        if tier == "regional":
            cluster["regions"] = regionalization(
                cluster["caen"], companies_by_caen[cluster["caen"]]
            )
        out.append(cluster)
    out.sort(key=lambda c: (-c["companies"], c["caen"]))

    regional = [c for c in out if c["tier"] == "regional"]
    companies_in_regional = sum(c["companies"] for c in regional)
    operators_today = companies_in_regional
    operators_proposed = REGIONS * len(regional)

    in_flight = [
        {
            "cui": c["cui"],
            "name": c["name"],
            "caen": c["caen"],
            "status": c["status"],
        }
        for c in source["companies"]
        if "fuziune" in (c["status"] or "") or "absorb" in (c["status"] or "").lower()
    ]

    payload = {
        "$schema": "../schema/companii-stat.schema.json",
        "id": "companii-stat",
        "title": "Companiile de stat pe activități: câte sunt și câte ar rămâne",
        "publisher": "Cristian Nichifor",
        "period": "2019-2024",
        "provenance": {
            "source": "companii-stat-finnefin",
            "locator": "gruparea pe cod CAEN din foaia Indicatori calculati; scenariul de "
            "consolidare aplicat utilităților de rețea",
            "confidence": "assumed",
            "note": "Cifrele pe companii, angajați și status sunt din sursă (verbatim/derived). "
            "Împărțirea pe niveluri (regional / local / național / altele) este o judecată de "
            "politică publică, nu un fapt din sursă, și este un singur tabel editabil în script.",
        },
        "clusters": out,
        "operatorRule": {
            "confidence": "assumed",
            "note": "Sursa nu desemnează operatorul regional. Regula de aici: companiile sunt "
            "grupate după județul de înregistrare, pliat pe cele opt regiuni; sediul este județul "
            "cu cele mai multe companii din activitate (egalitate: cei mai mulți angajați, apoi "
            "codul), iar nucleul absorbant este cea mai mare companie din acel județ după "
            "efectivul raportat — iar unde nimeni nu raportează efectiv, operatorul rămâne "
            "nenumit, nu ghicit.",
        },
        "inFlightMergers": in_flight,
        "summary": {
            "companies": source["summary"]["companies"],
            "clusters": len(out),
            "regionalClusters": len(regional),
            "companiesInRegionalClusters": companies_in_regional,
            "operatorsProposedOnEightRegions": operators_proposed,
            "reductionPercent": round(
                100 * (operators_today - operators_proposed) / operators_today, 1
            )
            if operators_today
            else 0,
            "microUnder20": sum(c["micro"] for c in out),
            "headcountKnown": sum(c["headcountKnown"] for c in out),
            "revenueRon": sum(c["revenueRon"] for c in out),
            "lossMaking": sum(c["lossCount"] for c in out),
            "subsidisedCount": sum(c["subsidisedCount"] for c in out),
            "subsidyRon": sum(c["subsidyRon"] for c in out),
            "inFlightMergers": len(in_flight),
        },
        "limitations": [
            {
                "id": "owner-partial",
                "text": "Proprietarul vine din lista AMEPIP Anexa 3 și lipsește pentru unele "
                "companii; acestea rămân fără proprietar, iar numărul de proprietari distincți "
                "este o limită inferioară.",
                "severity": "material",
                "affects": ["clusters", "regions"],
            },
            {
                "id": "subsidy-scope",
                "text": "Subvenția este cea raportată per firmă în Anexele SFA 2025. Lista "
                "acoperă operatorii raportați; o companie poate primi subvenții care nu apar "
                "aici, deci totalurile sunt limite inferioare.",
                "severity": "material",
                "affects": ["clusters", "summary"],
            },
            {
                "id": "financials-partial",
                "text": "Cifrele financiare vin din bilanțurile MFin 2025 și acoperă o parte "
                "din companii; acolo unde lipsește rândul, compania rămâne fără venituri, "
                "rezultat și datorii, iar totalurile sunt limite inferioare.",
                "severity": "material",
                "affects": ["clusters", "summary"],
            },
            {
                "id": "headcount-partial",
                "text": "Doar o parte dintre companii raportează numărul de angajați, deci "
                "totalurile de angajați sunt limite inferioare, nu estimări.",
                "severity": "material",
                "affects": ["clusters", "summary"],
            },
            {
                "id": "tier-is-policy",
                "text": "Care activități se regionalizează este o alegere de politică publică. "
                "Tabelul este marcat assumed și poate fi schimbat fără a atinge cifrele din sursă.",
                "severity": "material",
                "affects": ["clusters", "summary"],
            },
            {
                "id": "county-is-registration",
                "text": "Județul vine din registrul companiidestat.ro și este județul de "
                "înregistrare (sediul), nu teritoriul de servire. Un operator înregistrat în "
                "capitală poate servi alt județ; gruparea pe regiuni rămâne o aproximare.",
                "severity": "material",
                "affects": ["clusters", "regions"],
            },
            {
                "id": "operator-rule-assumed",
                "text": "Cine absoarbe pe cine este o regulă scrisă în operatorRule, marcată "
                "assumed: sursa spune câte companii sunt, nu care dintre ele devine nucleul.",
                "severity": "material",
                "affects": ["clusters", "regions"],
            },
            {
                "id": "in-flight-status-only",
                "text": "Statusul „fuziune prin absorbție” din sursă spune că o fuziune este "
                "în curs, nu cine absoarbe pe cine; lista inFlightMergers o raportează ca atare.",
                "severity": "note",
                "affects": ["inFlightMergers"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
