"""Import the wage benchmarks a position is judged against.

    uv run python scripts/import_benchmarks.py

Writes data/fiscal/benchmarks.json.

An exchange rate tells you how big a number is. It does not tell you what a society
thinks a job is worth, because it carries none of the surrounding economy. A ratio does:
a post paid three times the national average is treated as important wherever it sits,
and a post paid 1,2 times the average is not — regardless of currency, price level or
which decade the grid was written in.

So each position gets measured against two anchors from its own economy:

  the average gross wage      what a normal job pays there
  the floor                   what the least-paid work pays there

Average is national-accounts D11 — wages and salaries, excluding employers' social
contributions — divided by the number of employees. D1 would have been easier but
includes employer contributions, which are small in Romania and large in Denmark, so it
would have flattered Denmark by construction.

The floor is where the two countries stop being symmetrical. Romania legislates a
minimum wage. Denmark does not have one at all: pay floors are set by collective
agreement, sector by sector. Using a union rate for the lowest-paid work is the closest
honest equivalent, and it is labelled as an approximation everywhere it appears rather
than dressed up as a statutory figure.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = "https://api.statbank.dk/v1/data"
OUT = ROOT / "data/fiscal/benchmarks.json"
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

YEAR = "2024"
# Danish standard working week is 37 hours against Romania's 40 — one more reason a
# monthly comparison is fairer than an hourly one.
DK_HOURS_PER_MONTH = 37 * 52 / 12


def fetch(dataset: str, **params) -> dict:
    pairs: list[tuple[str, str]] = [("format", "JSON")]
    for key, value in params.items():
        for item in value if isinstance(value, list) else [value]:
            pairs.append((key, str(item)))
    url = f"{API}/{dataset}?{urllib.parse.urlencode(pairs)}"
    with urllib.request.urlopen(url, timeout=90) as response:  # noqa: S310
        return json.loads(response.read())


def by_geo(payload: dict) -> dict[str, float]:
    index = payload["dimension"]["geo"]["category"]["index"]
    values = payload["value"]
    out: dict[str, float] = {}
    for geo, position in index.items():
        value = values.get(str(position))
        if value is not None:
            out[geo] = float(value)
    return out


def series(sid: str, label: str, geo: str, unit: str, period: str, value: float,
           locator: str, confidence: str = "verbatim", note: str | None = None) -> dict:
    provenance = {"source": "eurostat", "locator": locator, "confidence": confidence}
    if note:
        provenance["note"] = note
    return {
        "id": sid,
        "label": label,
        "geo": geo,
        "unit": unit,
        "dims": {"kind": "benchmark"},
        "observations": [{"period": period, "value": round(value, 2)}],
        "provenance": provenance,
    }


def dst_basic_earnings() -> dict[str, float]:
    """Danish basic earnings per standard hour, excluding pension, by sector.

    Denmark's own statistical office is the better source than a Eurostat derivation, and
    the component matters: STANDARDIZED HOURLY EARNINGS would include pension, holiday
    pay and irregular payments, which the Romanian figure does not. BASISST is the
    like-for-like concept, and picking the headline number instead would have inflated
    the Danish anchor by about a fifth and quietly flattered every Romanian ratio.
    """
    body = json.dumps({
        "table": "LONS50", "format": "CSV", "lang": "en", "delimiter": "Semicolon",
        "variables": [
            {"code": "ALDER1", "values": ["TOT"]},
            {"code": "SEKTOR", "values": ["1000", "1032"]},
            {"code": "AFLOEN", "values": ["TIFA"]},
            {"code": "LONGRP", "values": ["LTOT"]},
            {"code": "LØNMÅL", "values": ["BASISST"]},
            {"code": "KØN", "values": ["MOK"]},
            {"code": "Tid", "values": [YEAR]},
        ],
    }).encode()
    request = urllib.request.Request(DST, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
        text = response.read().decode("utf-8-sig")
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        key = "all" if row["SEKTOR"].startswith("All") else "gov"
        out[key] = float(row["INDHOLD"]) * DK_HOURS_PER_MONTH
    return out


def main() -> None:
    print("fetching wages and salaries (D11) and employee counts ...")
    wages = by_geo(fetch("nama_10_a10", geo=["RO", "DK"], na_item="D11",
                         nace_r2="TOTAL", unit="CP_MNAC", time=YEAR))
    employees = by_geo(fetch("nama_10_a10_e", geo=["RO", "DK"], na_item="SAL_DC",
                             nace_r2="TOTAL", unit="THS_PER", time=YEAR))

    entries = []
    ro_monthly = wages["RO"] * 1e6 / (employees["RO"] * 1e3) / 12
    entries.append(series(
        "avg-gross-monthly-ro", "Salariul mediu brut lunar, toată economia (RO)",
        "RO", "CP_MNAC", YEAR, ro_monthly,
        f"Eurostat nama_10_a10 D11 ÷ nama_10_a10_e SAL_DC ÷ 12, geo=RO, {YEAR}", "derived",
        "D11 sunt salariile brute, fără contribuțiile angajatorului — același concept ca "
        "'basic earnings' din statistica daneză.",
    ))
    print(f"  RO all sectors: {ro_monthly:,.0f} RON".replace(",", " "))

    print("fetching Danish basic earnings from Danmarks Statistik (LONS50) ...")
    dk = dst_basic_earnings()
    entries.append(series(
        "avg-gross-monthly-dk", "Salariul mediu brut lunar, toată economia (DK)",
        "DK", "CP_MNAC", YEAR, dk["all"],
        f"Danmarks Statistik LONS50, BASISST × {DK_HOURS_PER_MONTH:.2f} ore/lună, toate sectoarele, {YEAR}",
        "derived",
        "Câștig de bază pe oră standard, fără pensie. Măsura de titlu a DST "
        "(STANDARDIZED HOURLY EARNINGS) include pensia, concediul și plățile neregulate, "
        "deci ar fi umflat reperul danez cu circa o cincime.",
    ))
    entries.append(series(
        "avg-gross-monthly-gov-dk", "Salariul mediu brut lunar, sectorul public (DK)",
        "DK", "CP_MNAC", YEAR, dk["gov"],
        f"Danmarks Statistik LONS50, BASISST, General government, {YEAR}", "derived",
    ))
    print(f"  DK all sectors: {dk['all']:,.0f} DKK".replace(",", " "))
    print(f"  DK general government: {dk['gov']:,.0f} DKK".replace(",", " "))

    print("fetching Romanian general-government compensation ...")
    gov = by_geo(fetch("gov_10a_exp", geo="RO", na_item="D1", sector="S13",
                       unit="MIO_NAC", cofog99="TOTAL", time=YEAR))
    posts = json.loads((ROOT / "data/headcount/posturi-ocupate-2026-06.json").read_text(encoding="utf-8"))
    ro_gov = gov["RO"] * 1e6 / posts["totalPosts"] / 12 / 1.0225
    entries.append(series(
        "avg-gross-monthly-gov-ro", "Salariul mediu brut lunar, sectorul public (RO)",
        "RO", "CP_MNAC", YEAR, ro_gov,
        f"Eurostat gov_10a_exp D1 ÷ posturi ocupate (MF) ÷ 12 ÷ 1,0225, {YEAR}", "derived",
        "D1 include contribuția asiguratorie pentru muncă de 2,25%, scoasă aici ca să rămână "
        "salariul brut. Numărul de posturi e din raportarea MF pentru iunie 2026, nu din 2024, "
        "deci raportul e aproximativ.",
    ))
    print(f"  RO general government: {ro_gov:,.0f} RON".replace(",", " "))

    print("fetching the Romanian statutory minimum wage ...")
    minimum = fetch("earn_mw_cur", geo=["RO", "DK"], currency="NAC", lastTimePeriod=1)
    period = next(iter(minimum["dimension"]["time"]["category"]["index"]))
    ro_min = by_geo(minimum).get("RO")
    if ro_min is None:
        raise SystemExit("no Romanian minimum wage returned")
    entries.append(series(
        "floor-monthly-ro", "Salariul minim brut pe țară (RO)", "RO", "CP_MNAC",
        period, ro_min, f"Eurostat earn_mw_cur, geo=RO, {period}",
    ))
    print(f"  RO minimum: {ro_min:,.0f}".replace(",", " "))
    print(f"  DK minimum: not published — Denmark has no statutory minimum wage")

    # Denmark's floor is a collective-agreement rate, not a law. Stated as an
    # approximation, with the rate and the hours both visible so a reader can redo it.
    dk_hourly = 140.0
    dk_floor = dk_hourly * DK_HOURS_PER_MONTH
    entries.append({
        "id": "floor-monthly-dk",
        "label": "Prag de jos din contractele colective (DK) — aproximare",
        "geo": "DK",
        "unit": "CP_MNAC",
        "dims": {"kind": "benchmark", "statutory": "no"},
        "observations": [{"period": "2026", "value": round(dk_floor, 2)}],
        "provenance": {
            "source": "presa-si-sinteze-sectoriale",
            "locator": "Rate orare de 135–145 DKK pentru munca necalificată în servicii, 2026",
            "confidence": "assumed",
            "note": f"Danemarca nu are salariu minim legal. S-a folosit {dk_hourly:.0f} DKK/oră × "
                    f"{DK_HOURS_PER_MONTH:.2f} ore/lună (37 de ore pe săptămână). Cifra provine din "
                    "sinteze secundare, nu din textul unui contract colectiv, și trebuie înlocuită cu "
                    "tariful din overenskomst-ul 3F sau HK atunci când e disponibil.",
        },
    })
    print(f"  DK collective floor (assumed): {dk_floor:,.0f}".replace(",", " "))

    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "benchmarks",
        "title": "Repere salariale naționale: media și pragul de jos",
        "publisher": "Eurostat; pentru pragul danez, surse secundare",
        "methodology": "ESA 2010 pentru medii; salariul minim legal pentru România",
        "retrieved": YEAR,
        "query": {"endpoint": API, "datasets": ["nama_10_a10", "nama_10_a10_e", "earn_mw_cur"]},
        "provenance": {
            "source": "eurostat",
            "locator": "nama_10_a10, nama_10_a10_e, earn_mw_cur",
            "confidence": "derived",
        },
        "series": entries,
        "limitations": [
            {
                "id": "media-nu-e-mediana",
                "text": "Media este trasă în sus de vârfuri. Mediana ar descrie mai bine „un salariu obișnuit”, dar nu e publicată anual pentru ambele țări prin aceeași metodă. Un raport față de medie subestimează cât de sus stă de fapt un post față de omul obișnuit — în ambele țări, dar mai tare în cea cu inegalitate mai mare.",
                "affects": ["structure", "gross"],
                "severity": "material",
            },
            {
                "id": "pragul-danez-nu-e-lege",
                "text": "Danemarca nu are salariu minim legal, iar pragul folosit aici este o rată din contracte colective, preluată din surse secundare și marcată ca atare. Nu are aceeași autoritate ca salariul minim românesc, care este stabilit prin hotărâre de guvern, și cele două nu trebuie citite ca fiind același tip de cifră.",
                "affects": ["structure", "gross"],
                "severity": "material",
            },
            {
                "id": "ore-diferite",
                "text": "Săptămâna standard daneză are 37 de ore, cea românească 40. La salariu lunar egal, ora daneză e plătită cu circa 8% mai bine decât arată comparația lunară.",
                "affects": ["gross"],
                "severity": "note",
            },
            {
                "id": "media-e-din-2024",
                "text": "Mediile sunt pe 2024, ultimul an complet din conturile naționale, în timp ce grilele comparate sunt din 2026. Salariile au crescut între timp în ambele țări, deci rapoartele sunt ușor supraestimate în ambele coloane.",
                "affects": ["structure"],
                "severity": "note",
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
