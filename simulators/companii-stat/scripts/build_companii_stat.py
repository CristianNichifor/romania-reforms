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

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = ROOT / "data" / "companii-2025.json"
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
            },
        )
        cluster["companies"] += 1
        employees = company.get("employees")
        if employees is not None:
            cluster["employees"] += employees
            cluster["headcountKnown"] += 1
            if employees < MICRO:
                cluster["micro"] += 1

    out = []
    for cluster in clusters.values():
        tier = TIERS.get(cluster["caen"], "other")
        cluster["tier"] = tier
        cluster["proposed"] = REGIONS if tier == "regional" else cluster["companies"]
        out.append(cluster)
    out.sort(key=lambda c: (-c["companies"], c["caen"]))

    regional = [c for c in out if c["tier"] == "regional"]
    companies_in_regional = sum(c["companies"] for c in regional)
    operators_today = companies_in_regional
    operators_proposed = REGIONS * len(regional)

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
        },
        "limitations": [
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
                "id": "no-geography",
                "text": "Sursa nu dă județul fiecărei companii, deci scenariul numără operatorii "
                "regionali, nu îi așază pe hartă.",
                "severity": "note",
                "affects": ["summary"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
