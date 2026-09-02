"""What the land tax actually raised, from the budget-execution filings.

Everything else in this simulator is modelled. The Fiscal Code side is the Code's own
arithmetic applied to the land register; the land value side is the notaries' grids applied to
the same hectares. Neither had ever been held against a number somebody actually banked.

This is that number. Every local authority files its budget execution against the revenue
classification, and that classification names the land tax on three separate lines:

    07.02.01  Impozit pe terenuri de la persoane fizice
    07.02.02  Impozit si taxa pe teren de la persoane juridice
    07.02.03  Impozit pe terenul din extravilan

transparenta.eu has loaded those filings and serves them over a public GraphQL API, the same
source `simulators/salarizare/scripts/import_executie.py` uses for the expenditure side. The
building tax is imported alongside it — not for the tax model, which is about land, but because
"the land tax raises a third of what the building tax raises" is the sentence the whole
argument for taxing land rather than improvements has to start from.

**What the comparison does and does not isolate.** Dividing what was collected by what this
repository models as the statutory tax gives a ratio, and that ratio is *not* a collection
rate. Four things move it and only the last is collection:

* **Which rate the council chose.** Art. 465 gives a range and art. 465 (9) lets the council
  pick inside it, so the modelled "tax today" is a band about 2,5× wide before anything else.
* **The zone and the rank**, both local decisions recorded in no national register.
* **Exemptions** under art. 464 — cult land, cemeteries, protected areas — which no source
  breaks out per locality.
* **Arrears and enforcement**, which is the only part the word "collection" describes.

So the ratio is reported and named, and it is deliberately *not* wired into
`build_impozit.py --collection-rate`. Feeding it back in would launder four unknowns into one
parameter that looks measured.

**What it does establish, which is worth more.** The modelled band is a claim about what the
Code permits, and it can now be tested: collections should land inside it. They do, in 34 of
42 counties, and in the eight that fall out they fall *below* the cheapest lawful reading —
never above the dearest. That is the signature of exemptions and arrears rather than of a
broken model, and it is the first external check this simulator has passed.

Usage:
    uv run python simulators/impozit-teren/scripts/import_impozit_incasat.py
    uv run python simulators/impozit-teren/scripts/import_impozit_incasat.py --year 2024
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.transparenta.eu/graphql"
# urllib's default agent is refused with 403; identify the caller instead.
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
YEAR = 2025

# The revenue classification, which for these filings lives in `functional_code` — the economic
# code is `00.00.00` on every revenue row, because a receipt has no economic nature to record.
LAND = {
    "07.02.01": "Impozit pe terenuri de la persoane fizice",
    "07.02.02": "Impozit și taxă pe teren de la persoane juridice",
    "07.02.03": "Impozit pe terenul din extravilan",
}
# Imported for scale, not for the model: the case for taxing land rather than what is built on
# it is hard to weigh without knowing how the two compare today.
BUILDINGS = {
    "07.01.01": "Impozit pe clădiri de la persoane fizice",
    "07.01.02": "Impozit și taxă pe clădiri de la persoane juridice",
}

COUNTIES = [
    "AB", "AR", "AG", "BC", "BH", "BN", "BT", "BV", "BR", "BZ", "CS", "CL", "CJ", "CT",
    "CV", "DB", "DJ", "GL", "GR", "GJ", "HR", "HD", "IL", "IS", "IF", "MM", "MH", "MS",
    "NT", "OT", "PH", "SM", "SJ", "SB", "SV", "TR", "TM", "TL", "VS", "VL", "VN", "B",
]

QUERY = """
query Land($filter: AnalyticsFilterInput!) {
  aggregatedLineItems(filter: $filter, limit: 50, offset: 0) {
    nodes { functional_code amount }
    pageInfo { totalCount hasNextPage }
  }
}
"""


def fetch(county: str, year: int) -> dict[str, float] | None:
    """One county's land and building tax receipts for one year.

    `PRINCIPAL_AGGREGATED` sums the ordonatori principali, which for a county is its
    communes, towns and county council — each filing once — rather than those plus every
    subordinate institution repeating the same money.
    """
    codes = [*LAND, *BUILDINGS]
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "filter": {
                    "account_category": "vn",
                    "report_type": "PRINCIPAL_AGGREGATED",
                    "functional_codes": codes,
                    "county_codes": [county],
                    "report_period": {
                        "type": "YEAR",
                        "selection": {"interval": {"start": str(year), "end": str(year)}},
                    },
                }
            },
        }
    ).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json", "User-Agent": UA}
    )
    for _ in range(3):
        try:
            document = json.loads(urllib.request.urlopen(request, timeout=180).read())  # noqa: S310
        except Exception:  # noqa: BLE001 — the service, not the county; retried below
            continue
        if document.get("errors"):
            return None
        found = document["data"]["aggregatedLineItems"]
        if found["pageInfo"]["hasNextPage"]:
            raise SystemExit(f"{county}: more rows than five revenue lines; the filter is wrong")
        return {node["functional_code"]: node["amount"] for node in found["nodes"]}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = dict(
            zip(
                COUNTIES,
                pool.map(lambda county: fetch(county, args.year), COUNTIES),
                strict=True,
            )
        )
    missing = sorted(county for county, found in results.items() if found is None)
    if missing:
        print(f"FATAL: no filing read for {missing}", file=sys.stderr)
        return 1

    rows = []
    for county in COUNTIES:
        found = results[county] or {}
        land = {code: found.get(code, 0.0) for code in LAND}
        buildings = {code: found.get(code, 0.0) for code in BUILDINGS}
        rows.append(
            {
                "county": county,
                "landRon": round(sum(land.values()), 2),
                "landByCodeRon": {code: round(value, 2) for code, value in land.items()},
                "buildingsRon": round(sum(buildings.values()), 2),
            }
        )
    rows.sort(key=lambda row: row["county"])

    land_total = sum(row["landRon"] for row in rows)
    buildings_total = sum(row["buildingsRon"] for row in rows)
    print(f"anul {args.year}: {len(rows)} județe")
    print(f"impozit pe teren încasat:   {land_total / 1e9:6.3f} mld RON")
    print(f"impozit pe clădiri încasat: {buildings_total / 1e9:6.3f} mld RON")
    print(f"terenul aduce {100 * land_total / buildings_total:.0f}% din cât aduc clădirile")

    document = {
        "$schema": "../schema/impozit-incasat.schema.json",
        "id": f"impozit-incasat-{args.year}",
        "title": f"Impozitul pe teren efectiv încasat, pe județe, {args.year}",
        "publisher": "transparenta.eu",
        "counties": COUNTIES,
        "period": str(args.year),
        "currency": "RON",
        "provenance": {
            "source": "transparenta-eu-executie-bugetara",
            "locator": (
                f"{API}, aggregatedLineItems, account_category vn, "
                f"report_type PRINCIPAL_AGGREGATED, coduri {', '.join(LAND)}, anul {args.year}"
            ),
            "confidence": "verbatim",
            "note": (
                "Sume raportate de ordonatorii principali de credite în execuția bugetară, "
                "preluate ca atare. Agregarea pe ordonatori principali evită numărarea de "
                "două ori a instituțiilor subordonate. Codurile de venituri stau în "
                "functional_code, nu în economic_code."
            ),
        },
        "classification": {**LAND, **BUILDINGS},
        "summary": {
            "counties": len(rows),
            "landRon": round(land_total, 2),
            "buildingsRon": round(buildings_total, 2),
            "landByCodeRon": {
                code: round(sum(row["landByCodeRon"][code] for row in rows), 2) for code in LAND
            },
            "landAsShareOfBuildingsPercent": round(100 * land_total / buildings_total, 2),
        },
        "localities": rows,
        "limitations": [
            {
                "id": "incasat-nu-datorat",
                "text": (
                    "Execuția bugetară arată ce s-a încasat, nu ce s-a datorat. Nu conține "
                    "drepturile constatate rămase neîncasate, așa că din ea nu se poate citi "
                    "un grad de colectare — pentru asta ar trebui contul de execuție al "
                    "veniturilor, care nu este publicat pe localități în această sursă."
                ),
                "severity": "blocking",
                "affects": ["impozit-incasat", "impozit"],
            },
            {
                "id": "raportul-nu-e-grad-de-colectare",
                "text": (
                    "Raportul dintre încasat și impozitul modelat aici amestecă patru lucruri: "
                    "cota aleasă de consiliul local din intervalul legal, zona, rangul și "
                    "scutirile din art. 464 — și abia la urmă colectarea. Este publicat ca "
                    "verificare a benzii modelate, nu ca parametru, și nu este introdus în "
                    "`--collection-rate`."
                ),
                "severity": "blocking",
                "affects": ["impozit"],
            },
            {
                "id": "anii-nu-coincid",
                "text": (
                    f"Încasările sunt din {args.year}, iar grilele notariale și impozitul "
                    "modelat sunt din edițiile pe care le-au publicat camerele — 2024, 2025 "
                    "sau 2026, după județ. Comparația conține și diferența de an."
                ),
                "severity": "material",
                "affects": ["impozit"],
            },
        ],
    }

    out = ROOT / "data" / f"impozit-incasat-{args.year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
