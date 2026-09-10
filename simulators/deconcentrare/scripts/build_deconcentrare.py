"""Deconcentrated services, by family, on the eight development regions.

The state's deconcentrated services are the layer no other simulator in this repository
touches. `administrativ` consolidates the 3 186 UATs but leaves the county line absolute;
`justitie` regionalises courts and prosecutors to the eight development regions but nothing
else; `transport` builds county networks. The 601 territorial services that report to ANFP in
2025 — a labour inspectorate, a public-health directorate, an employment agency, a pension
house, an agricultural payments centre in almost every county — are still organised on the
county map, one office per county per family.

This models the same move `curti-apel-regiuni` makes for courts: **one office per family per
development region, eight instead of forty-one.** The regions are not typed here either — the
county→region map is read from the one `justitie` already derived from `regions.geojson`, so
both simulators sit on the same eight areas.

Families are matched by an explicit table, not by fuzzy matching, because the source spells
the same service several ways (`DIRECTIA SANITAR-VETERINARA`, `DIRECTIA SANITAR -VETERINARA`,
`DIRECTIA SANITAR- VETERINARA`). A fuzzy matcher would fix those and quietly merge others; the
table is auditable and every unmatched name is reported rather than dropped.

Usage:
    uv run python scripts/build_deconcentrare.py
"""

from __future__ import annotations

import collections
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
INSTITUTIONS = ROOT / "data" / "institutii-2025.json"
REGISTRY = REPO / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"
REGION_MAP = REPO / "simulators" / "justitie" / "data" / "curti-apel-regiuni.json"
OUT = ROOT / "data" / "deconcentrare.json"

DECONCENTRATED = "TERITORIAL - SERVICIU PUBLIC DECONCENTRAT"

# code, canonical name, tier, prefixes (folded).
# tier "regional"     — today one per county, proposed one per development region.
# tier "regional-de-facto" — already organised on regions; reported, not merged.
# tier "special"      — neither; reported so the total reconciles.
FAMILIES = [
    ("cas", "Casa de Asigurări de Sănătate", "regional", ["CASA DE ASIGURARI DE SANATATE"]),
    ("itm", "Inspectoratul Teritorial de Muncă", "regional", ["INSPECTORATUL TERITORIAL DE MUNCA"]),
    (
        "ajofm",
        "Agenția Județeană pentru Ocuparea Forței de Muncă",
        "regional",
        ["AGENTIA JUDETEANA PENTRU OCUPAREA FORTEI DE MUNCA"],
    ),
    (
        "ajps",
        "Agenția Județeană pentru Plăți și Inspecție Socială",
        "regional",
        ["AGENTIA JUDETEANA PENTRU PLATI SI INSPECTIE SOCIALA"],
    ),
    ("apia", "APIA — Centrul Județean", "regional", ["APIA"]),
    ("dsp", "Direcția de Sănătate Publică", "regional", ["DIRECTIA DE SANATATE PUBLICA"]),
    (
        "djc",
        "Direcția Județeană pentru Cultură",
        "regional",
        ["DIRECTIA JUDETEANA PENTRU CULTURA"],
    ),
    (
        "daj",
        "Direcția pentru Agricultură Județeană",
        "regional",
        ["DIRECTIA PENTRU AGRICULTURA JUDETEANA"],
    ),
    ("cjp", "Casa Județeană de Pensii", "regional", ["CASA JUDETEANA DE PENSII"]),
    (
        "statistica",
        "Direcția Județeană/Regională de Statistică",
        "regional",
        ["DIRECTIA JUDETEANA DE STATISTICA", "DIRECTIA REGIONALA DE STATISTICA"],
    ),
    (
        "sport",
        "Direcția Județeană de Sport și Tineret",
        "regional",
        ["DIRECTIA JUDETEANA DE SPORT", "DIRECTIA JUDETEANA PENTRU SPORT"],
    ),
    (
        "dsv",
        "Direcția Sanitar-Veterinară și pentru Siguranța Alimentelor",
        "regional",
        ["DIRECTIA SANITAR"],
    ),
    (
        "itcsms",
        "Inspectoratul Teritorial pentru Calitatea Semințelor",
        "regional",
        ["INSPECTORATUL TERITORIAL PENTRU CALITATEA SEMINTELOR"],
    ),
    (
        "apm",
        "Agenția pentru Protecția Mediului",
        "regional",
        ["AGENTIA PENTRU PROTECTIA MEDIULUI", "AGENTIA JUDETEANA PENTRU PROTECTIA MEDIULUI"],
    ),
    (
        "djt",
        "Direcția Județeană pentru Familie și Tineret",
        "regional",
        ["DIRECTIA JUDETEANA PENTRU FAMILIE"],
    ),
    (
        "imm",
        "Agenția pentru Întreprinderi Mici și Mijlocii și Turism",
        "regional",
        ["AGENTIA PENTRU INTREPRINDERI MICI"],
    ),
    (
        "anpc",
        "Comisariatul Regional pentru Protecția Consumatorilor",
        "regional-de-facto",
        ["COMISARIATUL REGIONAL PENTRU PROTECTIA CONSUMATORILOR"],
    ),
    (
        "dgfp",
        "Direcția Generală Regională a Finanțelor Publice",
        "regional-de-facto",
        ["DIRECTIA GENERALA REGIONALA A FINANTELOR PUBLICE"],
    ),
    ("garda-forestiera", "Garda Forestieră", "regional-de-facto", ["GARDA FORESTIERA"]),
    (
        "anrsps",
        "Administrația Națională a Rezervelor de Stat și Probleme Speciale",
        "special",
        ["ADMINISTRATIA NATIONALA A REZERVELOR DE STAT"],
    ),
    (
        "delta",
        "Administrația Rezervației Biosferei Delta Dunării",
        "special",
        ["ADMINISTRATIA REZERVATIEI BIOSFEREI DELTA DUNARII"],
    ),
    (
        "cas-mai",
        "Casa Asigurărilor de Sănătate a Apărării, Ordinii Publice și Siguranței Naționale",
        "special",
        ["CASA ASIGURARILOR DE SANATATE A APARARII"],
    ),
    (
        "anofm-centru",
        "Centrul Național de Formare Profesională a Personalului ANOFM",
        "special",
        ["CENTRUL NATIONAL DE FORMARE PROFESIONALA"],
    ),
]

MUNICIPAL = ("MUNICIPAL", "MUNICIPIULUI", "SECTOR")
MUNICIPAL_SENTINEL = "MUNICIPAL"


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def load_county_codes() -> dict[str, str]:
    """Folded county name -> county code, from the shared SIRUTA registry."""
    units = json.loads(REGISTRY.read_text(encoding="utf-8"))["units"]
    pairs = {}
    for unit in units:
        if unit.get("level") == "county" and unit.get("countyCode"):
            pairs[fold(unit["countyName"])] = unit["countyCode"]
    return pairs


def load_county_population() -> dict[str, int]:
    """County code -> population, from the shared SIRUTA registry."""
    units = json.loads(REGISTRY.read_text(encoding="utf-8"))["units"]
    pairs = {}
    for unit in units:
        if unit.get("level") == "county" and unit.get("countyCode") and unit.get("population"):
            pairs[unit["countyCode"]] = unit["population"]
    return pairs


def load_region_of_county() -> dict[str, str]:
    """County code -> development region, reused from the justitie variant."""
    regions = json.loads(REGION_MAP.read_text(encoding="utf-8"))["regions"]
    return {code: region["region"] for region in regions for code in region["counties"]}


def strip_county(name: str, counties: list[str]) -> str:
    folded = fold(name)
    for county in counties:
        if folded.endswith(" " + county):
            return folded[: -(len(county) + 1)].strip()
    folded = re.sub(r"\s*[- ]*UT\s*\d+$", "", folded)
    folded = re.sub(r"\s*UNITATEA TERITORIALA\s*\d+$", "", folded)
    return re.sub(r"\s*\d+$", "", folded).strip()


def classify(folded: str) -> str | None:
    """Canonical family code, the sentinel ``MUNICIPAL``, or ``None`` if unmatched."""
    if any(token in folded for token in MUNICIPAL):
        return MUNICIPAL_SENTINEL
    for code, _name, _tier, prefixes in FAMILIES:
        if any(folded.startswith(prefix) for prefix in prefixes):
            return code
    return None


def seat_of(region: str, county_list: list[str], population: dict[str, int]) -> str:
    """The region's seat: the county with the largest population. Tie-break by code.

    This is a policy assumption, not a fact in the source — the register does not designate
    seats. County populations are unchanged by the administrative consolidation, because the
    administrative model never merges across a county line; when that simulator's reference
    map is locked, the seat *city* should be upgraded from its absorber seats, which is the
    one input this rule deliberately keeps a single function away from.
    """
    return max(
        county_list,
        key=lambda county: (population.get(county, 0), county),
    )


def main() -> None:
    source = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    county_codes = load_county_codes()
    region_of_county = load_region_of_county()
    population = load_county_population()
    counties = sorted(county_codes, key=len, reverse=True)

    families = {code: {"counties": set(), "count": 0} for code, *_ in FAMILIES}
    meta = {code: (name, tier) for code, name, tier, _ in FAMILIES}
    unmatched: list[str] = []
    municipal: list[str] = []
    deconcentrated_total = 0

    for row in source["institutions"]:
        if not row["type"].startswith(DECONCENTRATED):
            continue
        deconcentrated_total += 1
        code = classify(strip_county(row["name"], counties))
        if code == MUNICIPAL_SENTINEL:
            municipal.append(row["name"])
            continue
        if code is None:
            unmatched.append(row["name"])
            continue
        county = county_codes.get(fold(row["county"]))
        if county:
            families[code]["counties"].add(county)
        families[code]["count"] += 1

    out_families = []
    offices_today = offices_proposed = matched_offices = 0
    for code, *_ in FAMILIES:
        name, tier = meta[code]
        present = sorted(families[code]["counties"])
        count = families[code]["count"]
        matched_offices += count
        by_region = collections.defaultdict(list)
        for county in present:
            by_region[region_of_county.get(county, "?").strip()].append(county)
        proposed = len(by_region) if tier == "regional" else count
        if tier == "regional":
            offices_today += count
            offices_proposed += proposed
        out_families.append(
            {
                "code": code,
                "name": name,
                "tier": tier,
                "officesToday": count,
                "officesProposed": proposed,
                "counties": present,
                "regions": [
                    {
                        "region": region,
                        "seat": seat_of(region, sorted(county_list), population),
                        "seatPopulation": population.get(
                            seat_of(region, sorted(county_list), population)
                        ),
                        "counties": sorted(county_list),
                    }
                    for region, county_list in sorted(by_region.items())
                ],
            }
        )

    payload = {
        "$schema": "../schema/deconcentrare.schema.json",
        "id": "deconcentrare-2025",
        "title": "Servicii publice deconcentrate: de la județe la regiunile de dezvoltare",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "anfp-institutii-2025",
            "locator": "rândurile cu TipInstitutie „TERITORIAL - SERVICIU PUBLIC DECONCENTRAT”; "
            "împărțirea pe regiuni preluată din justitie/data/curti-apel-regiuni.json",
            "confidence": "derived",
            "note": "Regruparea pe familii folosește un tabel explicit de prefixe, nu potrivire "
            "fuzzy. Serviciile municipale (București, sectoare) sunt excluse și raportate separat.",
        },
        "seatRule": {
            "confidence": "assumed",
            "note": "Sediul unei direcții regionale nu este în sursă. Regula de aici: județul cu "
            "cea mai mare populație din regiune, din registrul SIRUTA partajat. Populațiile "
            "județene sunt neschimbate de comasarea administrativă — modelul administrativ nu "
            "unește niciodată peste granița de județ — iar când harta de referință a acelui "
            "simulator va fi blocată, sediul se poate rafina de la județ la orașul-absorbant "
            "din el, fără a atinge altceva.",
        },
        "families": out_families,
        "summary": {
            "deconcentratedOfficesTotal": deconcentrated_total,
            "matchedOffices": matched_offices,
            "regionalFamilies": sum(1 for f in out_families if f["tier"] == "regional"),
            "officesTodayInRegionalFamilies": offices_today,
            "officesProposedOnEightRegions": offices_proposed,
            "reductionPercent": round(100 * (offices_today - offices_proposed) / offices_today, 1)
            if offices_today
            else 0,
            "municipalExcluded": len(municipal),
            "unmatched": len(unmatched),
        },
        "municipalNames": sorted(municipal),
        "unmatchedNames": sorted(unmatched),
        "limitations": [
            {
                "id": "anfp-scope",
                "text": "Lista ANFP cuprinde instituțiile care gestionează funcții publice. Unele "
                "servicii deconcentrate cu personal contractual apar incomplet — de exemplu doar "
                "14 agenții de mediu și un singur comisariat pentru protecția consumatorilor. "
                "Numărul real de birouri de închis poate fi mai mare, nu mai mic.",
                "severity": "material",
                "affects": ["families", "summary"],
            },
            {
                "id": "naming-variants",
                "text": "Sursa scrie aceeași instituție în mai multe feluri; un tabel explicit de "
                "prefixe le grupează, iar numele nepotrivite sunt listate în unmatchedNames în loc "
                "să fie șterse.",
                "severity": "note",
                "affects": ["families"],
            },
            {
                "id": "seat-is-assumed",
                "text": "Sursa nu desemnează sediile regionale. Regula de aici — județul cel mai "
                "populat din regiune — este o presupunere de politică publică, nu un fapt din "
                "sursă; este scrisă în seatRule și poate fi contrazisă.",
                "severity": "material",
                "affects": ["families"],
            },
            {
                "id": "municipal-excluded",
                "text": "Serviciile municipale (inclusiv sectoarele Bucureștiului) nu se "
                "regionalizează prin județ și sunt excluse din socoteală.",
                "severity": "note",
                "affects": ["families"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = payload["summary"]
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print(f"-> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
