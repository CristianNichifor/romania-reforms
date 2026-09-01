"""Which measured farmland yield a county gets, in one place because three callers need it.

`build_renta.py` applies it, `build_impozit.py` carries it into the file the app reads, and the
app has to agree with both or the parity test fails. That is one decision — *what is the
measured return on farmland where this county is* — and three copies of it would be three
chances to answer it differently.

The band is the region's own year-to-year movement: minimum, median and maximum of its annual
yields, not a spread invented around a point estimate. Years before 2019 are left out because
the price series has a break either side of 2017–2018, where arable more than doubles, and a
band drawn across that would be measuring the discontinuity.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The eight development regions the survey reports, and the counties in each.
COUNTY_REGION = {
    "BH": "RO11", "BN": "RO11", "CJ": "RO11", "MM": "RO11", "SM": "RO11", "SJ": "RO11",
    "AB": "RO12", "BV": "RO12", "CV": "RO12", "HR": "RO12", "MS": "RO12", "SB": "RO12",
    "BC": "RO21", "BT": "RO21", "IS": "RO21", "NT": "RO21", "SV": "RO21", "VS": "RO21",
    "BR": "RO22", "BZ": "RO22", "CT": "RO22", "GL": "RO22", "TL": "RO22", "VN": "RO22",
    "AG": "RO31", "CL": "RO31", "DB": "RO31", "GR": "RO31", "IL": "RO31",
    "PH": "RO31", "TR": "RO31",
    "B": "RO32", "IF": "RO32",
    "DJ": "RO41", "GJ": "RO41", "MH": "RO41", "OT": "RO41", "VL": "RO41",
    "AR": "RO42", "CS": "RO42", "HD": "RO42", "TM": "RO42",
}
FROM_YEAR = "2019"
# Which Eurostat product answers for which cadastral code. Arable and permanent grassland are
# surveyed separately and yield differently — 1,42% against 1,61% — so pasture and hayfield
# take their own measurement instead of borrowing arable's. Vineyards, orchards and the rest
# are not surveyed apart, so they fall back to arable, which is stated rather than hidden.
PRODUCT_FOR_CODE = {"P+F": "J0000"}
DEFAULT_PRODUCT = "ARA"


def product_of(code: str) -> str:
    return PRODUCT_FOR_CODE.get(code, DEFAULT_PRODUCT)


def forest(county: str) -> tuple[dict[str, float] | None, str | None]:
    """The county's forest yield, derived from its timber harvest and the stumpage price.

    Kept beside the agricultural bands because callers want one answer to "what does this
    code earn here", not two lookups with different shapes. It is a derivation rather than a
    measurement — there is no forest rent to survey — and the dataset it reads says so.
    """
    found = sorted((ROOT / "data").glob("randament-padure-*.json"))
    if not found:
        return None, None
    document = json.loads(found[-1].read_text(encoding="utf-8"))
    row = next(
        (r for r in document["counties_measured"] if r["county"] == county.upper()), None
    )
    if row is None:
        return None, None
    return row["yieldPercent"], (
        f"Recolta de {row['m3PerHaPerYear']:.2f} m³/ha/an (INS AGR306A, {document['period']}) × "
        "prețul masei lemnoase pe picior (Romsilva), minus costurile proprietarului, împărțit "
        f"la {row['forestValueRonPerHa']:,.0f} lei/ha valoarea pădurii din grilă."
    )


def measured(
    county: str, product: str = DEFAULT_PRODUCT
) -> tuple[dict[str, float] | None, str | None]:
    """The county's region's band, or (None, None) if the survey is not imported.

    Returning nothing rather than a default is the point: a missing dataset must leave the
    caller applying its own assumed band and saying so, not quietly substituting a number
    that happens to be lying around.
    """
    found = sorted((ROOT / "data").glob("teren-agricol-ins-*.json"))
    if not found:
        return None, None
    survey = json.loads(found[-1].read_text(encoding="utf-8"))
    region = COUNTY_REGION.get(county.upper())
    match = next((r for r in survey["regions"] if r["region"] == region), None)
    if match is None:
        return None, None
    values = sorted(
        row["yieldPercent"]
        for row in match["series"]
        if row.get("product", DEFAULT_PRODUCT) == product
        and row["yieldPercent"] is not None
        and row["year"] >= FROM_YEAR
    )
    if len(values) < 3:
        return None, None
    band = {"low": values[0], "central": values[len(values) // 2], "high": values[-1]}
    last = match["series"][-1]["year"]
    label = "pășuni și fânețe" if product == "J0000" else "teren arabil"
    return band, (
        f"Arendă ÷ preț pentru {label}, regiunea {match['name']} ({region}), "
        f"anchete INS {FROM_YEAR}–{last} raportate la Eurostat (apri_lprc / apri_lrnt); "
        "banda este minimul, mediana și maximul anilor măsurați."
    )
