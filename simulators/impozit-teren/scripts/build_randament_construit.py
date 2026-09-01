"""What the land under a house earns, bounded — because nobody in Romania publishes it.

Farmland's yield is measured: INS surveys both the price and the rent, and the ratio is about
1,5%. For building land there is no equivalent anywhere. The notaries' studies price land but
publish no rents — all 115 volumes were searched and the only matches are prose. Municipal
concession fees would be a land rent, but they are negotiated contract by contract and the
decisions leave the figure blank. ANEVAR publishes portfolio composition, not capitalisation
rates for land.

So this does not measure it. It **bounds** it, from an identity and three inputs that are each
named, sourced and movable:

    a property earns   NOI = r·L + (r + δ)·B        L land, B building, δ depreciation
    so                 y_net = NOI/V = r + δ·(1 − λ)     λ = L/V, the land share
    therefore          r = y_net − δ·(1 − λ)

The point of writing it this way is that every term is observable except the one being solved
for. A property yield is published. A depreciation rate is in Romanian law. And the land share
can be computed from the notaries' own grids, because several chambers price the land and the
building **separately, on the same page, for the same locality** — and say so: Mureș prints
*"Valoarea caselor de locuit individuale nu includ terenul aferent"*, Hunedoara's commercial
tables print *"Nu include Terenul"*. Without that sentence the whole calculation would be
circular, so it is quoted rather than assumed.

**The land share is the surprise.** It comes out near 7% of property value at a plot four times
the floor area — far below the 20–50% usual in western European cities, and matching ANEVAR's
own finding that land is 7,6% of the portfolios its members value. Romanian construction costs
what it costs everywhere and Romanian land outside the big cities does not.

**Which makes the derived yield low.** A property yielding 4,4% net where 93% of the value is a
depreciating building is mostly returning capital, not earning it; what is left as a pure
return — what land earns — is about **2,5%**, against the 3–7% this simulator assumes.

Three things keep it a bound rather than an answer, and all three are limitations in the file.
The sample is three counties, and poor ones: no grid exists for Bucharest, Cluj or Timiș, where
land is dear and the land share would be far higher, so this is biased low. The plot-to-floor
ratio is an assumption, not a measurement. And the identity assumes an investor requires the
same return on both halves of a property, which is the standard simplification and still a
simplification.

Usage:
    uv run python simulators/impozit-teren/scripts/build_randament_construit.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dialect_hunedoara as hd  # noqa: E402
from extract_cache import load  # noqa: E402
from import_ghid import key_of, keys_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Observed gross residential yield, Global Property Guide, research of July 2026: 5,87% in
# Q3 2026, easing from 6,02% in Q1 2026 and 6,33% in Q3 2025. Gross, so operating costs,
# vacancy and management still have to come out of it before it is a return on capital.
GROSS_YIELD = 5.87
GROSS_YIELD_SOURCE = (
    "Global Property Guide, randament brut rezidențial România 5,87% în T3 2026 "
    "(6,02% T1 2026, 6,33% T3 2025)"
)
# What a landlord loses to costs, management and empty months. Not published for Romania; the
# band is wide on purpose because it is the least defensible number here.
OPEX_SHARE = {"low": 0.30, "central": 0.25, "high": 0.20}
# HG nr. 2139/2004, catalogul mijloacelor fixe, clasa 1.6.1 — clădiri de locuit: 40–60 de ani.
# The band is the catalogue's own, not a guess around a point.
BUILDING_LIFE_YEARS = {"low": 60, "central": 50, "high": 40}
DEPRECIATION_SOURCE = (
    "HG nr. 2139/2004, Catalogul privind clasificarea și duratele normale de funcționare a "
    "mijloacelor fixe, clasa 1.6.1 „clădiri de locuit”: 40–60 de ani"
)
# Plot area over built floor area. A 500 m² plot under a 125 m² house is 4. Assumed, and the
# land share moves with it, so it is reported as a band and carried in the output.
PLOT_TO_FLOOR = {"low": 3.0, "central": 4.0, "high": 6.0}

BANDS = ("low", "central", "high")
HOUSE_TABLE = re.compile(r"CL[ĂA]DIRI DE LOCUIT INDIVIDUALE")
# Iași heads each table with the place and the zone it prices — "IAŞI - ZONA A" — and puts
# the house price on the row that names individual dwellings.
IASI_HEADING = re.compile(r"^\s*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.]{2,}?)\s*[-–]\s*ZONA\s+([A-L])\s*$")
IASI_HOUSE_ROW = re.compile(r"locuinte\s+individuale", re.I)
HOUSE_HEADER = re.compile(r"AN\s+EDIFICARE", re.I)
LOCALITY_HEADER = re.compile(r"LOCALITATEA", re.I)
HOUSE_COLUMN = re.compile(r"cas[ae]", re.I)
NOT_A_HOUSE = re.compile(r"teren|anexe|garaj|apartam|industrial|comercial", re.I)
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)


def number(cell: str) -> float | None:
    text = re.sub(r"\s+", "", cell or "")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+([.,]\d+)?", text):
        return None
    value = float(text.replace(".", "").replace(",", ".")) if "." in text and "," in text else (
        float(text.replace(".", "")) if re.fullmatch(r"\d{1,3}(\.\d{3})+", text)
        else float(text.replace(",", "."))
    )
    return value if 0 < value < 100_000 else None


def pairs_hunedoara(document: str, grid: dict) -> list[tuple[str, float, float, bool]]:
    """Hunedoara prices the land and the house in the same row, so the pair is the row."""
    urban = {k for z in grid["zoned"] for k in keys_of(z["name"])}
    found: list[tuple[str, float, float, bool]] = []
    for page in load(document)["pages"]:
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 2:
                continue
            heads = hd.captions(cells)
            land = next(
                (
                    i
                    for i, caption in heads.items()
                    if hd.CC_CAPTION.search(caption) and not hd.AGRICOL.search(caption)
                ),
                None,
            )
            house = next(
                (
                    i
                    for i, caption in heads.items()
                    if HOUSE_COLUMN.search(caption) and not NOT_A_HOUSE.search(caption)
                ),
                None,
            )
            if land is None or house is None:
                continue
            for row in cells[hd.header_depth(cells) :]:
                line = [hd.clean(c) for c in row]
                if max(land, house) >= len(line):
                    continue
                soil, built = hd.number(line[land]), hd.number(line[house])
                label = next((c for c in line if NAME.match(c)), "")
                # A house that costs less than three times its own land is a data error or a
                # cell read out of the wrong column, not a Romanian house.
                if soil and built and built > soil * 3:
                    key = key_of(label) if label else ""
                    found.append((key, soil, built, key in urban))
    return found


def pairs_targumures(document: str, grid: dict) -> list[tuple[str, float, float, bool]]:
    """Mureș and Harghita price houses and land in separate tables, joined by locality.

    The house tables are the ones headed CLĂDIRI DE LOCUIT INDIVIDUALE with an AN EDIFICARE
    column pair; the newer of the two build periods is taken, because a land yield is about
    what the property is worth now and a house built before 2000 has already depreciated —
    counting it whole would overstate the building and understate the land share.
    """
    land: dict[str, float] = {}
    for entry in grid["zoned"]:
        prices = [v for v in entry["intravilan"]["CC"].values() if v]
        if prices:
            for key in keys_of(entry["name"]):
                land[key] = max(prices)
    for commune in grid["communes"]:
        prices = [
            v["intravilan"]["CC"] for v in commune["villages"] if v["intravilan"].get("CC")
        ]
        if prices:
            for key in keys_of(commune["name"]):
                land.setdefault(key, max(prices))

    urban = {k for z in grid["zoned"] for k in keys_of(z["name"])}
    found: list[tuple[str, float, float, bool]] = []
    active = False
    for page in load(document)["pages"]:
        if HOUSE_TABLE.search(page["text"]):
            active = True
        elif re.search(r"ANEXE|APARTAMENTE|COSTRUC[ŢT]II|SPA[ŢT]II", page["text"]):
            active = False
        if not active:
            continue
        for table in page["tables"]:
            cells = [[re.sub(r"\s+", " ", c or "").strip() for c in row] for row in table["cells"]]
            if len(cells) < 3 or len(cells[0]) != 4:
                continue
            head = " ".join(c for row in cells[:2] for c in row)
            if not (LOCALITY_HEADER.search(head) and HOUSE_HEADER.search(head)):
                continue
            for row in cells[2:]:
                if len(row) < 4 or not NAME.match(row[0]):
                    continue
                built = number(row[3]) or number(row[2])
                soil = land.get(key_of(row[0]))
                if soil and built and built > soil * 3:
                    found.append((key_of(row[0]), soil, built, key_of(row[0]) in urban))
    return found


def pairs_iasi(document: str, grid: dict) -> list[tuple[str, float, float, bool]]:
    """Iași: one table per town and zone, with the land price for the same pair in the grid.

    This is the county that matters most for the land share. Everywhere else in the sample
    building land is cheap and the share comes out near 6%; Iași zone A is 600 euro a square
    metre against 1 800 for the house on it, which is a different world and the reason the
    first estimate was biased low.
    """
    land: dict[tuple[str, str], float] = {}
    for entry in grid["zoned"]:
        for zone, price in entry["intravilan"]["CC"].items():
            if price:
                for key in keys_of(entry["name"]):
                    land[(key, zone)] = price

    # Every row here is a zoned town, because that is all this annex prices.
    found: list[tuple[str, float, float, bool]] = []
    place: tuple[str, str] | None = None
    for page in load(document)["pages"]:
        for line in page["text"].splitlines():
            heading = IASI_HEADING.match(line.strip())
            if heading:
                place = (key_of(heading.group(1)), heading.group(2).upper())
        if place is None:
            continue
        for table in page["tables"]:
            for row in table["cells"]:
                line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
                if not any(IASI_HOUSE_ROW.search(c) for c in line):
                    continue
                figures = [v for v in (number(c) for c in line) if v is not None and v > 50]
                soil = land.get(place)
                # A house has to cost more per square metre than a fifth of its land, or the
                # two figures are not about the same kind of thing.
                if figures and soil and figures[0] > soil * 0.2:
                    found.append((place[0], soil, figures[0], True))
    return found


def main() -> int:
    grids = {
        p.stem.replace("ghid-teren-", "").rsplit("-", 1)[0]: json.loads(
            p.read_text(encoding="utf-8")
        )
        for p in sorted((ROOT / "data").glob("ghid-teren-*.json"))
    }
    sources: list[tuple[str, str, list[tuple[str, float, float, bool]]]] = []
    if "hunedoara" in grids:
        sources.append(
            ("HD", "Hunedoara_2026.pdf",
             pairs_hunedoara("Hunedoara_2026.pdf", grids["hunedoara"]))
        )
    if "iasi" in grids:
        sources.append(
            ("IS", "studiu_de_piata_Iasi_2026.pdf",
             pairs_iasi("studiu_de_piata_Iasi_2026.pdf", grids["iasi"]))
        )
    for county, chamber, document in (
        (
            "MS",
            "mures",
            "28_03_2026_STUDIU_JUDETUL_MURES_PT_2026_republicare_compressed_(4)_16_03_2026.pdf",
        ),
        (
            "HR",
            "harghita",
            "28_03_2026_STUDIU_JUDETUL_HARGHITA_PT_2026_republicare_compressed_(1)_16_03_2026.pdf",
        ),
    ):
        if chamber in grids:
            sources.append((county, document, pairs_targumures(document, grids[chamber])))

    counties = []
    every_share: dict[str, list[float]] = {b: [] for b in BANDS}
    for county, document, found in sources:
        if len(found) < 8:
            print(f"{county}: only {len(found)} pairs, skipped", file=sys.stderr)
            continue
        shares = {
            b: [
                PLOT_TO_FLOOR[b] * soil / (PLOT_TO_FLOOR[b] * soil + built)
                for _, soil, built, _urban in found
            ]
            for b in BANDS
        }
        for b in BANDS:
            every_share[b].extend(shares[b])
        counties.append(
            {
                "county": county,
                "source": document,
                "pairs": len(found),
                "landSharePercent": {
                    b: round(100 * statistics.median(shares[b]), 3) for b in BANDS
                },
            }
        )
    if not counties:
        raise SystemExit("no county prices land and buildings together; nothing to derive")

    net = {b: GROSS_YIELD * (1 - OPEX_SHARE[b]) for b in BANDS}
    depreciation = {b: 100 / BUILDING_LIFE_YEARS[b] for b in BANDS}
    # Split, because pooling them is the wrong statistic. Building land in a village and in
    # the centre of Iași are not the same asset: the land share is about 6% in one and a third
    # in the other, and 97% of the rows are villages while most of the country's building-land
    # *value* is towns. A single median over rows answers a question nobody asked.
    def median_of(rows: list[tuple[str, float, float, bool]], want_urban: bool) -> dict | None:
        picked = [(soil, built) for _, soil, built, urban in rows if urban == want_urban]
        if len(picked) < 8:
            return None
        return {
            b: statistics.median(
                PLOT_TO_FLOOR[b] * soil / (PLOT_TO_FLOOR[b] * soil + built)
                for soil, built in picked
            )
            for b in BANDS
        }

    every_pair = [pair for _, _, found in sources for pair in found]
    urban_share = median_of(every_pair, True)
    rural_share = median_of(every_pair, False)
    share = {b: statistics.median(every_share[b]) for b in BANDS}

    def derive(from_share: dict[str, float]) -> dict[str, float]:
        return {
            "low": net["low"] - max(depreciation.values()) * (1 - from_share["low"]),
            "central": net["central"]
            - depreciation["central"] * (1 - from_share["central"]),
            "high": net["high"] - min(depreciation.values()) * (1 - from_share["high"]),
        }
    # Each end is built from the inputs that push the answer the *same* way, which is not the
    # same as taking each input's own "low". A thin property yield hurts the land yield and so
    # does fast depreciation, but fast depreciation is the *short* building life — so the
    # pessimistic end pairs the low net yield with the 40-year life and the small land share,
    # and the optimistic end pairs the opposite three. Reading each input's "low" together
    # made the two effects cancel and collapsed the band to a point, 2,52–2,42, which looked
    # like precision and was arithmetic.
    derived = {
        "low": net["low"] - max(depreciation.values()) * (1 - share["low"]),
        "central": net["central"] - depreciation["central"] * (1 - share["central"]),
        "high": net["high"] - min(depreciation.values()) * (1 - share["high"]),
    }

    document = {
        "$schema": "../schema/randament-teren-construit.schema.json",
        "id": "randament-teren-construit-2026",
        "title": "Randamentul terenului de sub clădiri, dedus din randamentul proprietății",
        "publisher": "romania-reforms",
        "counties": [c["county"] for c in counties],
        "period": "2026",
        "currency": "RON",
        "provenance": {
            "source": "global-property-guide-hg-2139-2004-grile-notariale",
            "locator": (
                "randament brut rezidențial (Global Property Guide) − amortizare "
                "(HG 2139/2004, clasa 1.6.1) × ponderea clădirii, unde ponderea terenului "
                "este calculată din prețurile de teren și de construcție publicate pe aceeași "
                "pagină în grilele notariale ale județelor HD, MS și HR"
            ),
            "confidence": "derived",
            "note": (
                "r_teren = randament_net − amortizare × (1 − pondere_teren). "
                "Nu este o măsurătoare: în România nu se publică nicăieri o chirie a terenului "
                "de sub clădiri. Toate cele trei intrări sunt parametri declarați."
            ),
        },
        "assumptions": {
            "grossYieldPercent": GROSS_YIELD,
            "grossYieldSource": GROSS_YIELD_SOURCE,
            "operatingCostShare": OPEX_SHARE,
            "netYieldPercent": {b: round(net[b], 4) for b in BANDS},
            "buildingLifeYears": BUILDING_LIFE_YEARS,
            "depreciationPercent": {b: round(depreciation[b], 4) for b in BANDS},
            "depreciationSource": DEPRECIATION_SOURCE,
            "plotToFloorRatio": PLOT_TO_FLOOR,
        },
        "summary": {
            "counties": len(counties),
            "pairs": sum(c["pairs"] for c in counties),
            "landSharePercent": {b: round(100 * share[b], 3) for b in BANDS},
            "derivedYieldPercent": {b: round(derived[b], 4) for b in BANDS},
            "urbanLandSharePercent": (
                {b: round(100 * urban_share[b], 3) for b in BANDS} if urban_share else None
            ),
            "urbanDerivedYieldPercent": (
                {b: round(v, 4) for b, v in derive(urban_share).items()}
                if urban_share
                else None
            ),
            "ruralLandSharePercent": (
                {b: round(100 * rural_share[b], 3) for b in BANDS} if rural_share else None
            ),
            "ruralDerivedYieldPercent": (
                {b: round(v, 4) for b, v in derive(rural_share).items()}
                if rural_share
                else None
            ),
            "urbanPairs": sum(1 for _, _, _, u in every_pair if u),
            "ruralPairs": sum(1 for _, _, _, u in every_pair if not u),
            "assumedYieldPercent": {"low": 3.0, "central": 5.0, "high": 7.0},
        },
        "counties_measured": counties,
        "limitations": [
            {
                "id": "nu-e-masuratoare-ci-deducere",
                "text": (
                    "Nu există nicăieri în România o chirie publicată a terenului de sub "
                    "clădiri: grilele notariale publică prețuri, nu chirii, iar redevențele de "
                    "concesiune se negociază contract cu contract. Cifra de aici este dedusă "
                    "dintr-o identitate cu trei intrări declarate, nu observată."
                ),
                "severity": "blocking",
                "affects": ["randament-teren-construit", "renta"],
            },
            {
                "id": "esantion-de-judete-sarace",
                "text": (
                    "Ponderea terenului este calculată din trei județe — Hunedoara, Mureș, "
                    "Harghita — pentru că doar acolo grila publică prețul terenului și pe cel "
                    "al construcției pentru aceeași localitate. Nu există grilă pentru "
                    "București, Cluj sau Timiș, unde terenul e scump și ponderea lui ar fi mult "
                    "mai mare. Estimarea este deci înclinată în jos."
                ),
                "severity": "material",
                "affects": ["randament-teren-construit"],
            },
            {
                "id": "raportul-lot-suprafata-construita",
                "text": (
                    "Ponderea terenului depinde de cât teren se presupune sub o casă. Aici se "
                    "folosește un lot de 3–6 ori suprafața construită desfășurată, cu 4 la "
                    "mijloc. Este o presupunere, nu o măsurătoare, iar ponderea se mișcă direct "
                    "cu ea."
                ),
                "severity": "material",
                "affects": ["randament-teren-construit"],
            },
            {
                "id": "acelasi-randament-cerut-pe-ambele-jumatati",
                "text": (
                    "Identitatea presupune că investitorul cere aceeași rentabilitate a "
                    "capitalului și pentru teren, și pentru clădire, diferența dintre ele fiind "
                    "doar amortizarea. Este simplificarea standard și rămâne o simplificare: "
                    "terenul și clădirea nu au același risc."
                ),
                "severity": "material",
                "affects": ["randament-teren-construit"],
            },
        ],
    }

    out = ROOT / "data" / "randament-teren-construit-2026.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'județ':>8} {'perechi':>8} {'pondere teren (central)':>24}")
    for row in counties:
        print(f"{row['county']:>8} {row['pairs']:8d} {row['landSharePercent']['central']:23.1f}%")
    print()
    print(f"{'':<26}{'low':>10}{'central':>10}{'high':>10}")
    for label, series in (
        ("randament net proprietate", net),
        ("amortizare clădire", depreciation),
        ("pondere teren (%)", {b: 100 * share[b] for b in BANDS}),
        ("=> randament teren", derived),
    ):
        print(f"{label:<26}" + "".join(f"{series[b]:10.2f}" for b in BANDS))
    print(f"{'presupus până acum':<26}{3.0:10.2f}{5.0:10.2f}{7.0:10.2f}")
    for label, sh in (("urban", urban_share), ("rural", rural_share)):
        if sh:
            got = derive(sh)
            print(
                f"  {label:<8} pondere teren {100 * sh['central']:5.1f}%  "
                f"=> randament {got['central']:.2f}%  "
                f"(bandă {got['low']:.2f}–{got['high']:.2f})"
            )
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
