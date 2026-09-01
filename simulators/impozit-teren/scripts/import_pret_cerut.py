"""What sellers ask for farmland, from the register the law makes them publish it in.

Everything else in this simulator is administrative. The notaries' grids are the floor under a
transaction, the Fiscal Code's tables are a coefficient, and the land register counts hectares.
None of them is a price anyone actually named for a specific field.

This one is. Legea 17/2014 gives pre-emption rights over **extravilan agricultural land** to
neighbours, tenants and the state, and to make that workable it requires the seller's offer —
plot, area, price — to be published at the town hall and on the ministry's portal. So there is
a national, public, per-commune register of what Romanian farmland is being offered at, kept
because the pre-emption procedure needs it rather than because anyone set out to measure the
market.

Verifi aggregates that register into county and UAT percentiles and publishes the result under
**CC BY 4.0**, which is why this reads their aggregate rather than re-scraping the ministry:
the aggregation is the work, it is licensed for reuse, and re-doing it would be worse
manners and a worse dataset. Their `dataset.json` is keyed by **SIRUTA**, which is the key
this repository already joins on, so nothing has to be matched by name.

**These are asking prices, and the distinction is the whole point of the file.** Verifi say so
themselves — *"Prețul la care se încheie efectiv tranzacția poate diferi și nu apare în această
sursă"*. An offer register records what was wanted, not what was paid, and the two differ by an
unknown margin in an unknown direction. The figures here are therefore an upper bound on what a
buyer paid and a lower bound on nothing at all.

**And it is only farmland.** The register exists for extravilan agricultural land, so there is
no curți-construcții price in it anywhere — which is 64% of the land value this simulator
computes, on 2,8% of its surface. Whatever this says about the gap between the grid and the
market, it says it about the cheap majority of hectares.

Usage:
    uv run python simulators/impozit-teren/scripts/import_pret_cerut.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://verifi.ro/pret-teren-agricol/dataset.json"
PAGE = "https://verifi.ro/pret-teren-agricol"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
CACHE = ROOT / "sources" / "verifi-pret-teren-agricol.json"
# County names as the barometer writes them, to the two-letter codes everything else here uses.
COUNTY_CODES = {
    "Alba": "AB", "Arad": "AR", "Argeș": "AG", "Bacău": "BC", "Bihor": "BH",
    "Bistrița-Năsăud": "BN", "Botoșani": "BT", "Brașov": "BV", "Brăila": "BR", "Buzău": "BZ",
    "Caraș-Severin": "CS", "Călărași": "CL", "Cluj": "CJ", "Constanța": "CT", "Covasna": "CV",
    "Dâmbovița": "DB", "Dolj": "DJ", "Galați": "GL", "Giurgiu": "GR", "Gorj": "GJ",
    "Harghita": "HR", "Hunedoara": "HD", "Ialomița": "IL", "Iași": "IS", "Ilfov": "IF",
    "Maramureș": "MM", "Mehedinți": "MH", "Mureș": "MS", "Neamț": "NT", "Olt": "OT",
    "Prahova": "PH", "Satu Mare": "SM", "Sălaj": "SJ", "Sibiu": "SB", "Suceava": "SV",
    "Teleorman": "TR", "Timiș": "TM", "Tulcea": "TL", "Vaslui": "VS", "Vâlcea": "VL",
    "Vrancea": "VN", "București": "B",
}
M2_PER_HA = 10_000


def fetch(refresh: bool) -> dict:
    """The barometer, cached beside the other sources so a rerun is not a second request."""
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    request = urllib.request.Request(SOURCE, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(body, encoding="utf-8")
    return json.loads(body)


def band(record: dict) -> dict[str, float] | None:
    """p25 / median / p75 in RON per hectare, or None if the row carries no usable band."""
    values = {
        "low": record.get("p25RonPerHa"),
        "central": record.get("medianRonPerHa"),
        "high": record.get("p75RonPerHa"),
    }
    if any(v is None or v <= 0 for v in values.values()):
        return None
    return {k: float(v) for k, v in values.items()}


def main() -> int:
    refresh = "--refresh" in sys.argv
    source = fetch(refresh)

    counties = []
    for record in source["counties"]:
        prices = band(record)
        if prices is None:
            continue
        code = COUNTY_CODES.get(record["county"])
        if code is None:
            print(f"county not recognised, skipped: {record['county']}", file=sys.stderr)
            continue
        localities = []
        for uat in record.get("uats", []):
            local = band(uat)
            if local is None or not uat.get("siruta"):
                continue
            localities.append(
                {
                    "siruta": str(uat["siruta"]),
                    "name": uat["uat"],
                    "offers": uat["n"],
                    "ronPerHa": local,
                    "eurPerM2": {k: round(v / M2_PER_HA, 6) for k, v in local.items()},
                }
            )
        counties.append(
            {
                "county": code,
                "name": record["county"],
                "offers": record["n"],
                "activeOffers": record.get("activeOffers"),
                "ronPerHa": prices,
                # Carried in the unit the rest of this simulator prices land in, so the two
                # can be compared without every consumer redoing the same division.
                "eurPerM2": {k: round(v / M2_PER_HA, 6) for k, v in prices.items()},
                "localities": sorted(localities, key=lambda x: x["siruta"]),
            }
        )
    counties.sort(key=lambda x: x["county"])

    document = {
        "$schema": "../schema/pret-cerut-agricol.schema.json",
        "id": "pret-cerut-agricol-2026",
        "title": "Prețul cerut pentru teren agricol extravilan, pe județe și UAT-uri, 2026",
        "publisher": "romania-reforms",
        "counties": [c["county"] for c in counties],
        "period": str(source["updated"])[:4],
        "currency": "RON",
        "provenance": {
            "source": "verifi-barometru-pret-teren-agricol",
            "locator": (
                f"{SOURCE} (metodologia v{source['methodologyVersion']}, "
                f"actualizat {source['updated']}), agregat din portalul ofertelor de vânzare "
                "Legea 17/2014 (MADR/RCT + direcțiile agricole județene)"
            ),
            "confidence": "verbatim",
            "note": (
                "Percentilele sunt preluate ca atare din setul publicat de Verifi sub licența "
                "CC BY 4.0; aici se adaugă doar codul de județ și conversia RON/ha → EUR/m². "
                f"Citare: {source['citation']}"
            ),
        },
        # The county records themselves. The top-level "counties" is the repository's list of
        # county codes and is not the data; these are.
        "prices": counties,
        "summary": {
            "counties": len(counties),
            "localities": sum(len(c["localities"]) for c in counties),
            "pricedOffers": source["totalPricedOffers"],
            "activeOffers": source["totalActiveOffers"],
            "minOffersPerCounty": source["minCountyN"],
            "minOffersPerLocality": source["minUatN"],
            "updated": source["updated"],
        },
        "limitations": [
            {
                "id": "preturi-cerute-nu-de-tranzactionare",
                "text": (
                    "Registrul Legii 17/2014 înregistrează prețul CERUT de vânzător în oferta "
                    "publicată, nu prețul la care s-a încheiat tranzacția. Verifi precizează "
                    "explicit că prețul efectiv poate diferi și nu apare în această sursă. "
                    "Orice raport calculat față de grila notarială este deci un raport între "
                    "un minim administrativ și o cerere, nu între două prețuri de piață."
                ),
                "severity": "blocking",
                "affects": ["pret-cerut-agricol", "multiplu-piata"],
            },
            {
                "id": "doar-teren-agricol-extravilan",
                "text": (
                    "Obligația de publicare privește doar terenul agricol din extravilan, deci "
                    "registrul nu conține niciun preț pentru curți-construcții. În datele "
                    "acestui simulator, curțile-construcții sunt 64% din valoarea terenului pe "
                    "2,8% din suprafață, așa că sursa acoperă majoritatea ieftină a hectarelor "
                    "și nu minoritatea scumpă."
                ),
                "severity": "blocking",
                "affects": ["pret-cerut-agricol", "multiplu-piata"],
            },
            {
                "id": "ofertele-nu-sunt-ponderate-pe-suprafata",
                "text": (
                    "Percentilele sunt calculate pe ofertă, nu pe hectar: o ofertă de 0,5 ha "
                    "cântărește cât una de 50 ha. Un județ în care se oferă multe parcele mici "
                    "și scumpe apare mai scump decât este pe hectar."
                ),
                "severity": "material",
                "affects": ["pret-cerut-agricol", "multiplu-piata"],
            },
            {
                "id": "acoperire-inegala-pe-judete",
                "text": (
                    f"Sunt publicate doar județele cu cel puțin {source['minCountyN']} oferte "
                    f"cu preț utilizabil și doar UAT-urile cu cel puțin {source['minUatN']}. "
                    f"Din {source['observedCountyCount']} județe observate rămân "
                    f"{source['countyCount']}; Mureș, între altele, lipsește."
                ),
                "severity": "material",
                "affects": ["pret-cerut-agricol", "multiplu-piata"],
            },
        ],
    }

    out = ROOT / "data" / "pret-cerut-agricol-2026.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{len(counties)} județe, {document['summary']['localities']} UAT-uri, "
        f"{source['totalPricedOffers']} oferte cu preț"
    )
    print(f"Wrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
