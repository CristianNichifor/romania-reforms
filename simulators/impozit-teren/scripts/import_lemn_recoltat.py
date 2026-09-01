"""How much timber a county's forests actually give up in a year.

This exists to answer one question the rest of the simulator could not: what does forest land
*earn*? Farmland has a measured yield because INS surveys both its price and its rent. Forest
has no rent anywhere — nobody leases a hectare of woodland by the year — so its return has to
be built from the thing forest actually produces, which is timber.

    rentă forestieră ≈ recolta anuală pe hectar × prețul masei lemnoase pe picior

INS matrix **AGR306A**, *Volumul de lemn recoltat pe specii, macroregiuni, regiuni de dezvoltare
și judete*, gives the first half per county and per year, in thousands of cubic metres. This
reads it and divides by the forest area the land register reports for the same county, which is
already imported.

**Realised harvest, not allowable cut.** The figure is what was actually taken, which is below
what the forest grows in a normal year and can be far below it where harvesting is restricted or
access is poor. That makes this a conservative measure of what the land yields, and the
direction of the error is worth knowing: it understates forest rent, and therefore understates
what a tax would take from forest owners.

**Gross volume.** AGR306A reports volum brut, timber before extraction losses, and the auction
price it is multiplied by is for standing timber — which is also gross. The two match, and that
is the reason for pairing this series with a stumpage price rather than with a sawn-timber one.

Usage:
    uv run python simulators/impozit-teren/scripts/import_lemn_recoltat.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPO = "http://statistici.insse.ro:8077/tempo-ins"
MATRIX = "AGR306A"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
# The counties as INS spells them here, to the codes the rest of the repository uses. Same
# spellings as the land register's matrix, which is not a coincidence — one institution.
COUNTY_CODES = {
    "Alba": "AB", "Arad": "AR", "Arges": "AG", "Bacau": "BC", "Bihor": "BH",
    "Bistrita-Nasaud": "BN", "Botosani": "BT", "Braila": "BR", "Brasov": "BV", "Buzau": "BZ",
    "Caras-Severin": "CS", "Calarasi": "CL", "Cluj": "CJ", "Constanta": "CT", "Covasna": "CV",
    "Dambovita": "DB", "Dolj": "DJ", "Galati": "GL", "Giurgiu": "GR", "Gorj": "GJ",
    "Harghita": "HR", "Hunedoara": "HD", "Ialomita": "IL", "Iasi": "IS", "Ilfov": "IF",
    "Maramures": "MM", "Mehedinti": "MH", "Mures": "MS", "Neamt": "NT", "Olt": "OT",
    "Prahova": "PH", "Satu Mare": "SM", "Salaj": "SJ", "Sibiu": "SB", "Suceava": "SV",
    "Teleorman": "TR", "Timis": "TM", "Tulcea": "TL", "Vaslui": "VS", "Valcea": "VL",
    "Vrancea": "VN", "Municipiul Bucuresti": "B",
}
THOUSAND_M3 = 1_000
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
# The closing tag is tolerated with attributes on it because TEMPO emits
# `<td align='right'>503,4</td align='right'>` — malformed, and the reason a strict
# `</td>` matched nothing at all.
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh][^>]*>", re.S)


def metadata() -> dict:
    cache = ROOT / "sources" / f"ins-{MATRIX.lower()}-metadata.json"
    if not cache.exists():
        print(f"downloading {TEMPO}/matrix/{MATRIX} ...")
        request = urllib.request.Request(f"{TEMPO}/matrix/{MATRIX}", headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(response.read())
    return json.loads(cache.read_text(encoding="utf-8"))


def latest_year(meta: dict) -> str:
    years = [o["label"] for o in meta["dimensionsMap"][2]["options"]]
    return max(years, key=lambda label: int(re.sub(r"\D", "", label) or 0))


def query(meta: dict, year: str) -> str:
    """Every county's total harvest for one year, as the HTML the endpoint answers with.

    Options are posted back as the objects the metadata gave, not as bare ids — the endpoint
    deserialises each into a typed object and rejects a number, which is why the metadata is
    read first here as it is for the land register.
    """
    dims = meta["dimensionsMap"]
    categories = [o for o in dims[0]["options"] if o["label"].strip() == "Total"]
    counties = [o for o in dims[1]["options"] if o["label"].strip() in COUNTY_CODES]
    years = [o for o in dims[2]["options"] if o["label"].strip() == year]
    arr = [categories, counties, years, dims[3]["options"]]
    for index, group in enumerate(arr):
        if not group:
            raise SystemExit(f"{MATRIX}: nothing selected for dimension {index + 1}")
    body = json.dumps(
        {
            "language": "ro",
            "arr": arr,
            "matrixName": meta["matrixName"],
            "matrixDetails": meta["details"],
        }
    ).encode()
    request = urllib.request.Request(
        f"{TEMPO}/matrix/{MATRIX}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.loads(response.read())["resultTable"]


def parse(table: str) -> dict[str, float]:
    """County code to cubic metres harvested, out of the answer's HTML table."""
    found: dict[str, float] = {}
    for row in ROW.findall(table):
        cells = [unescape(re.sub(r"<.*?>", "", c)).strip() for c in CELL.findall(row)]
        if len(cells) < 2:
            continue
        code = next((COUNTY_CODES[c] for c in cells if c in COUNTY_CODES), None)
        if code is None:
            continue
        figures = [
            float(c.replace(".", "").replace(",", "."))
            for c in cells
            if re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?", c)
        ]
        if figures:
            found[code] = figures[-1] * THOUSAND_M3
    return found


def main() -> int:
    meta = metadata()
    year = latest_year(meta)
    period = re.sub(r"\D", "", year)
    harvest = parse(query(meta, year))
    if len(harvest) < 35:
        raise SystemExit(f"{MATRIX}: only {len(harvest)} counties came back; refusing to write")

    areas = {}
    for path in sorted((ROOT / "data").glob("fond-funciar-*-2014.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        code = document["counties"][0]
        areas[code] = sum(row["forestHa"] for row in document["localities"])

    rows = []
    for code, volume in sorted(harvest.items()):
        forest = areas.get(code)
        rows.append(
            {
                "county": code,
                "harvestM3": round(volume),
                "forestHa": round(forest, 2) if forest else None,
                # The number this file exists for. None where the register has not been
                # imported for that county rather than filled with a national average.
                "m3PerHaPerYear": round(volume / forest, 4) if forest else None,
            }
        )
    measured = [r["m3PerHaPerYear"] for r in rows if r["m3PerHaPerYear"]]
    national = sum(r["harvestM3"] for r in rows) / sum(
        r["forestHa"] for r in rows if r["forestHa"]
    )

    document = {
        "$schema": "../schema/lemn-recoltat.schema.json",
        "id": f"lemn-recoltat-{period}",
        "title": f"Volumul de lemn recoltat pe județe, {year}",
        "publisher": "romania-reforms",
        "counties": [r["county"] for r in rows],
        "period": period,
        "provenance": {
            "source": "ins-tempo-agr306a",
            "locator": (
                f"{TEMPO}/matrix/{MATRIX}, {year}, categorii de păduri: Total, volum brut; "
                "suprafața pădurii din fondul funciar INS AGR101B 2014"
            ),
            "confidence": "derived",
            "note": (
                "Recolta este preluată ca atare; singurul calcul este împărțirea la suprafața "
                "pădurii aceluiași județ, ca să dea metri cubi pe hectar pe an."
            ),
        },
        "summary": {
            "counties": len(rows),
            "withForestArea": len(measured),
            "harvestM3": round(sum(r["harvestM3"] for r in rows)),
            "nationalM3PerHaPerYear": round(national, 4),
        },
        "counties_measured": rows,
        "limitations": [
            {
                "id": "recolta-nu-cresterea",
                "text": (
                    "Este recolta efectivă, nu creșterea anuală a pădurii. Se taie mai puțin "
                    "decât crește, iar acolo unde accesul e greu sau tăierile sunt restricționate "
                    "se taie mult mai puțin. Renta forestieră calculată din această cifră este "
                    "deci subestimată, iar captura impozitului din ea, supraestimată."
                ),
                "severity": "material",
                "affects": ["lemn-recoltat", "randament-padure"],
            },
            {
                "id": "suprafata-padurii-e-din-2014",
                "text": (
                    "Recolta este din anul curent, iar suprafața pădurii din registrul funciar "
                    "2014, singurul an cu detaliu pe localități. Fondul forestier s-a schimbat "
                    "puțin între timp, dar raportul dintre cele două nu este dintr-un singur an."
                ),
                "severity": "material",
                "affects": ["lemn-recoltat"],
            },
        ],
    }

    out = ROOT / "data" / f"{document['id']}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} județe, {document['summary']['harvestM3'] / 1e6:.2f} mil. m³ în {year}")
    print(f"recolta națională: {national:.2f} m³/ha/an")
    print(f"Wrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
