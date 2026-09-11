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
from pathlib import Path

from common import (
    fold,
    load_county_codes,
    load_county_population,
    load_region_of_county,
    strip_county,
)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
INSTITUTIONS = ROOT / "data" / "institutii-2025.json"
REGISTRY = REPO / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"
REGION_MAP = REPO / "simulators" / "justitie" / "data" / "curti-apel-regiuni.json"
OUT = ROOT / "data" / "deconcentrare.json"
REGISTRY_OUT = ROOT / "data" / "deconcentrare-registry.json"
PORTAL = ROOT / "data" / "portal-ep-2026.json"

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
    registry_rows: list[dict] = []

    for row in source["institutions"]:
        if not row["type"].startswith(DECONCENTRATED):
            continue
        deconcentrated_total += 1
        code = classify(strip_county(row["name"], counties))
        county = county_codes.get(fold(row["county"]))
        if code == MUNICIPAL_SENTINEL:
            municipal.append(row["name"])
            registry_rows.append(
                {
                    "name": row["name"],
                    "type": row["type"],
                    "county": county,
                    "locality": row.get("locality") or "",
                    "family": None,
                    "familyName": None,
                    "tier": "municipal",
                    "source": "anfp",
                }
            )
            continue
        if code is None:
            unmatched.append(row["name"])
            registry_rows.append(
                {
                    "name": row["name"],
                    "type": row["type"],
                    "county": county,
                    "locality": row.get("locality") or "",
                    "family": None,
                    "familyName": None,
                    "tier": "unmatched",
                    "source": "anfp",
                }
            )
            continue
        if county:
            families[code]["counties"].add(county)
        families[code]["count"] += 1
        registry_rows.append(
            {
                "name": row["name"],
                "type": row["type"],
                "county": county,
                "locality": row.get("locality") or "",
                "family": code,
                "familyName": meta[code][0],
                "tier": meta[code][1],
                "source": "anfp",
            }
        )

    out_families = []
    offices_today = offices_proposed = matched_offices = 0
    portal_matched = portal_kept = 0
    portal_by_family: dict[str, dict] = collections.defaultdict(
        lambda: {"counties": set(), "count": 0, "name": "", "tier": ""}
    )
    portal_regionals = collections.defaultdict(int)

    if PORTAL.exists():
        portal = json.loads(PORTAL.read_text(encoding="utf-8"))
        for office in portal["offices"]:
            code = office["family"]
            portal_matched += 1
            info = portal_by_family[code]
            info["name"] = office["familyName"]
            info["tier"] = office["tier"]
            # A row the ANFP source already covers in the same family and county is not a
            # complement — counting it again would double-count the same office. The
            # (family, county) pair is the conservative dedupe key.
            if code in families and office["county"] in families[code]["counties"]:
                continue
            portal_kept += 1
            if office["county"]:
                info["counties"].add(office["county"])
            info["count"] += 1
            registry_rows.append(
                {
                    "name": office["name"],
                    "type": "",
                    "county": office["county"],
                    "locality": office["locality"],
                    "family": code,
                    "familyName": office["familyName"],
                    "tier": office["tier"],
                    "source": "portal",
                    "ordonator": office["ordonator"],
                }
            )
        portal_municipal = portal["summary"]["municipalExcluded"]
        portal_unmatched = portal["summary"]["unmatched"]
    else:
        portal_municipal = portal_unmatched = 0

    for code, *_ in FAMILIES:
        name, tier = meta[code]
        anfp_count = families[code]["count"]
        portal_info = portal_by_family.get(code)
        portal_count = portal_info["count"] if portal_info else 0
        present = sorted(
            families[code]["counties"] | (portal_info["counties"] if portal_info else set())
        )
        count = anfp_count + portal_count
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
                "sources": {"anfp": anfp_count, "portal": portal_count},
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

    # Portal-only families: services the ANFP register does not carry at all. Their office
    # counts come entirely from the complement source; the rule applies to them unchanged.
    anfp_codes = {code for code, *_ in FAMILIES}
    portal_order = [code for code in portal_by_family if code not in anfp_codes]
    for code in portal_order:
        info = portal_by_family.get(code)
        if not info or info["count"] == 0:
            continue
        name, tier = info["name"], info["tier"]
        anfp_count = 0
        portal_count = info["count"]
        present = sorted(info["counties"])
        count = portal_count
        matched_offices += count
        by_region = collections.defaultdict(list)
        for county in present:
            by_region[region_of_county.get(county, "?").strip()].append(county)
        proposed = len(by_region) if tier == "regional" else count
        if tier == "regional":
            offices_today += count
            offices_proposed += proposed
            portal_regionals[code] = count
        out_families.append(
            {
                "code": code,
                "name": name,
                "tier": tier,
                "officesToday": count,
                "officesProposed": proposed,
                "sources": {"anfp": anfp_count, "portal": portal_count},
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
            "deconcentratedOfficesTotal": deconcentrated_total + portal_kept,
            "matchedOffices": matched_offices,
            "regionalFamilies": sum(1 for f in out_families if f["tier"] == "regional"),
            "officesTodayInRegionalFamilies": offices_today,
            "officesProposedOnEightRegions": offices_proposed,
            "reductionPercent": round(100 * (offices_today - offices_proposed) / offices_today, 1)
            if offices_today
            else 0,
            "municipalExcluded": len(municipal),
            "unmatched": len(unmatched),
            "anfp": {
                "deconcentratedOfficesTotal": deconcentrated_total,
                "matchedOffices": deconcentrated_total - len(municipal) - len(unmatched),
                "regionalFamilies": sum(
                    1 for f in out_families if f["tier"] == "regional" and f["sources"]["anfp"] > 0
                ),
                "officesTodayInRegionalFamilies": sum(
                    f["sources"]["anfp"] for f in out_families if f["tier"] == "regional"
                ),
                "officesProposedOnEightRegions": sum(
                    f["officesProposed"]
                    for f in out_families
                    if f["tier"] == "regional" and f["sources"]["portal"] == 0
                ),
            },
            "portal": {
                "matched": portal_matched,
                "kept": portal_kept,
                "droppedDuplicate": portal_matched - portal_kept,
                "municipalExcluded": portal_municipal,
                "unmatched": portal_unmatched,
            },
        },
        "municipalNames": sorted(municipal),
        "unmatchedNames": sorted(unmatched),
        "limitations": [
            {
                "id": "anfp-scope",
                "text": "Lista ANFP cuprinde instituțiile care gestionează funcții publice. "
                "Serviciile deconcentrate cu personal contractual sunt complementate din lista "
                "MFin a entităților publice (câmpul sources pe fiecare familie); chiar și "
                "împreună, agențiile județene de mediu, comisariatele județene ANPC și GNM, "
                "unitățile ANIF, sistemele județene ANAR și oficiile de zootehnie rămân absente "
                "din ambele surse. Numărul real de birouri de închis poate fi mai mare, nu "
                "mai mic.",
                "severity": "material",
                "affects": ["families", "summary"],
            },
            {
                "id": "portal-scope",
                "text": "Complementul vine din lista MFin a entităților publice (snapshot "
                "01.07.2026): entități cu CIF și ordonator de credite, fără efective de personal. "
                "O filială fără CIF propriu sau finanțată prin altă structură nu apare; "
                "duplicarea cu ANFP este tăiată per perechea (familie, județ), deci un birou "
                "listat diferit în cele două surse poate rămâne numărat o singură dată, nu de "
                "două ori.",
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

    registry = {
        "$schema": "../schema/deconcentrare-registry.schema.json",
        "id": "deconcentrare-registry",
        "title": "Birourile deconcentrate, rând cu rând",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "anfp-institutii-2025 + mfin-portal-entitati-publice",
            "locator": "rândurile cu TipInstitutie „TERITORIAL - SERVICIU PUBLIC DECONCENTRAT” din "
            "ANFP, plus rândurile complementate din portalul MFin; familia din tabelul de prefixe "
            "al acestui simulator, câmpul source distinge sursa fiecărui rând",
            "confidence": "derived",
            "note": "Câmpurile de rând sunt copiate din sursă; familia și nivelul vin din același "
            "tabel de prefixe ca payload-ul principal.",
        },
        "summary": {
            "offices": deconcentrated_total + portal_kept,
            "withCounty": sum(1 for row in registry_rows if row["county"]),
            "matched": matched_offices,
            "regional": offices_today,
            "municipal": len(municipal),
            "unmatched": len(unmatched),
            "sources": {"anfp": deconcentrated_total, "portal": portal_kept},
        },
        "offices": registry_rows,
    }
    REGISTRY_OUT.write_text(
        json.dumps(registry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"-> {REGISTRY_OUT} ({len(registry_rows)} rows)")


if __name__ == "__main__":
    main()
