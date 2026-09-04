"""What property actually sold for, commune by commune, read off the tax it paid.

Everything else in this directory values land from the notaries' grid, and the standing
objection to all of it is that the grid is a floor rather than a price. `build_multiplu_piata.py`
answers that objection for farmland and says so honestly: it cannot answer it for
curți-construcții, which is two thirds of the value on under three per cent of the surface.
There is no published price series for building land in Romania.

There is, however, a tax on every transfer, and a tax leaves a number behind.

**Art. 111 (1) Cod fiscal** charges the transfer of any building or land at a flat rate on the
transaction value, with no allowance deducted: **3%** when the seller held it three years or
less, **1%** above that. **Art. 111 (7)** splits the proceeds — half to the state budget, half
to *"bugetul unităților administrativ-teritoriale pe teritoriul cărora se află bunurile imobile
ce au făcut obiectul înstrăinării"*. That second half lands in the commune's own budget
execution under revenue code `03.18.00`, which transparenta.eu serves per UAT, and which the
budget importer next door was already walking past.

So each commune's filing is half a tax, at a rate between 1% and 3%, on the declared value of
everything that changed hands inside its boundary in one year:

    valoarea declarată = 03.18.00 × 2 ÷ cotă

**The rate mix is unknown and is not guessed here.** A resale after four years pays 1% and a
flat bought from a developer pays 3%, and nobody publishes the split. So this file stores the
one thing it measured — the receipt — and puts the two rates in `assumptions` for whoever
divides. A single "effective rate" invented here would read as a measurement and would be the
only fabricated number in the directory.

**What this can and cannot settle, stated before anyone divides by it.**

*It measures turnover, not price.* No counts and no surfaces come with the money, so this says
how much value moved through a commune, not what a square metre went for. ANCPI publishes
transaction counts per county; with those the quotient becomes an average price per transfer.

*It measures property, not land.* A transfer is a house and the ground under it in one figure,
which is exactly the inseparability that makes land value easy to understate in the first
place. Splitting it needs the structure's replacement cost.

*It is bounded on one side only, and that is the point.* The declared value cannot legally fall
below the grid, so `declarat ÷ grilă` is a **lower** bound on `piață ÷ grilă`. Come back well
above 1 and the suppression is measured. Come back at about 1 and the test has failed to
separate "the grid is right" from "everybody declares the minimum" — which is worth knowing,
and is why the asymmetry is written down here rather than discovered later.

Usage:
    uv run python simulators/impozit-teren/scripts/import_transfer_imobiliar.py
    uv run python simulators/impozit-teren/scripts/import_transfer_imobiliar.py --year 2024
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The roster and the batching are borrowed rather than copied. Both carry a lesson that cost a
# silent half-import to learn — the endpoint caps a page at 100 and lies about it with
# `hasNextPage`, so the roster advances by what came back and never by what was asked for — and
# a second copy of that loop is a second place for it to be got wrong.
import import_buget_uat as buget  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2025

# Art. 111 (7): half the tax is the commune's, half is the state's. The exception in (7^1) —
# transfers of dismemberments under a suspensive condition, which go wholly to the state — is
# not separable here, so doubling the local half understates the total slightly rather than
# overstating it.
LOCAL_SHARE = 0.5

# Art. 111 (1) a) and b). Stored, not averaged.
RATE_MIN_PERCENT = 1.0
RATE_MAX_PERCENT = 3.0

# The revenue line. Verified against a 40-UAT sample before this was written: it is the only
# `03.*` code any of them files, and all forty file it.
CODE = "03.18.00"

# How far above the country's median receipt per inhabitant a filing may sit before it is
# treated as a filing rather than a property market.
#
# Fifty, and the number was measured rather than picked. The distribution is naturally skewed —
# a suburb where farmland is being cut into house plots really does bank thirty times what a
# median commune does, and the top twenty are Moșnița Nouă, Giroc, Dumbrăvița and Șag around
# Timișoara, Chinteni, Ciurila and Feleacu around Cluj, Cârcea and Malu Mare around Craiova.
# Those are the signal. Above them the data goes quiet: the highest of them is 37× the median,
# and then nothing at all until 297×. Fifty sits in that empty band, clear of every commune
# whose figure is a market and far below the one whose figure is not.
SUSPECT_MULTIPLE = 50


def receipts(uats: list[dict], year: int) -> dict[str, float]:
    """The `03.18.00` line for every UAT, in lei, keyed by SIRUTA."""
    out: dict[str, float] = {}
    for start in range(0, len(uats), buget.BATCH):
        chunk = uats[start : start + buget.BATCH]
        data = buget.post(buget.batch_query([u["uatId"] for u in chunk], "vn", year))
        for uat in chunk:
            found = data.get(f"u{uat['uatId']}")
            if not found:
                continue
            nodes = found["nodes"]
            # A commune files two dozen revenue lines; a Bucharest sector files four hundred
            # and more. Only the ones that overflow pay for a second round trip.
            if found["pageInfo"]["hasNextPage"]:
                nodes = buget.all_rows(uat["uatId"], "vn", year)
            out[uat["siruta"]] = sum(
                (row["amount"] or 0.0) for row in nodes if (row["functional_code"] or "") == CODE
            )
        print(f"  {min(start + buget.BATCH, len(uats))} of {len(uats)}", file=sys.stderr)
    return out


def quarantine(rows: list[dict], population: dict[str, int]) -> list[dict]:
    """Set aside filings that cannot be a property market, measured against the data's own middle.

    Mirrors `import_buget_uat.quarantine` deliberately, including the choice to test a ratio
    rather than to name a culprit — naming Sector 5 would quietly pass the next one.

    What it catches here is the same authority the budget importer already excludes, and the
    evidence is not only its size. Bucharest's transfer tax belongs to the municipality: five of
    the six sectors file nothing at all under this code and the municipality files 45,8 mil lei,
    while Sector 5 — one of the poorer ones — files 777,6 mil, seventeen times the whole city
    and twenty-six times Cluj-Napoca, the hottest market in the country. Left in, it is 59% of
    Romania's property transfer tax and every national figure derived from this file is wrong by
    a factor of two and a half.

    Population comes from the roster rather than from `buget-uat`, because the authorities most
    likely to trip this are the ones that file excluded there and so have no population left.
    """
    per_capita = [
        (row["localTaxRon"] / population[row["siruta"]], row)
        for row in rows
        if population.get(row["siruta"]) and row["localTaxRon"] > 0
    ]
    if not per_capita:
        return []
    ordered = sorted(value for value, _ in per_capita)
    median = ordered[len(ordered) // 2]
    suspects = []
    for value, row in per_capita:
        if value <= SUSPECT_MULTIPLE * median:
            continue
        row["suspect"] = True
        suspects.append(
            {
                "siruta": row["siruta"],
                "name": row["name"],
                "reportedLocalTaxRon": row["localTaxRon"],
                "perInhabitantRon": round(value, 2),
                "timesMedian": round(value / median, 1),
            }
        )
    return sorted(suspects, key=lambda s: -s["timesMedian"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=YEAR)
    args = parser.parse_args()

    uats = buget.roster()
    if len(uats) < 3000:
        raise SystemExit(f"only {len(uats)} UATs came back; refusing to write a partial roster")

    banked = receipts(uats, args.year)

    rows = []
    for uat in sorted(uats, key=lambda u: u["siruta"]):
        amount = banked.get(uat["siruta"], 0.0)
        if amount <= 0:
            continue
        rows.append(
            {
                "siruta": uat["siruta"],
                # County councils file under a letter code rather than a SIRUTA number. The
                # transfer tax is assigned to the UAT the property stands in, so a county
                # council should not have one at all — kept and labelled if it does, because a
                # figure that should not exist is worth seeing rather than dropping.
                "level": "county" if not uat["siruta"].isdigit() else "uat",
                "name": uat["name"],
                "county": uat["county"],
                "localTaxRon": round(amount, 2),
            }
        )

    # Population is used and not stored: it joins from `buget-uat-<year>.json` on the same
    # SIRUTA for anyone who wants it, and 3 182 more integers is 80 KB against a repository
    # that has about a megabyte of room left.
    suspects = quarantine(rows, {u["siruta"]: u["population"] or 0 for u in uats})
    rows = [r for r in rows if not r.pop("suspect", False)]

    local_tax = sum(r["localTaxRon"] for r in rows)
    tax = local_tax / LOCAL_SHARE
    # Both ends, never a point. At 3% the same receipt implies the least value, at 1% the most.
    low = tax / (RATE_MAX_PERCENT / 100)
    high = tax / (RATE_MIN_PERCENT / 100)

    # What share the single largest filer is of the country. Not a quarantine — unlike the
    # spending figures next door, a big number here is what an expensive city looks like — but
    # a filing that was 80% of the national total would be a filing, not a property market, and
    # this is how that would be noticed rather than averaged away.
    largest = max(rows, key=lambda r: r["localTaxRon"]) if rows else None

    document = {
        "$schema": "../schema/transfer-imobiliar.schema.json",
        "id": f"transfer-imobiliar-{args.year}",
        "title": (
            f"Impozitul pe transferul proprietăților imobiliare, pe UAT, execuție {args.year}"
        ),
        "publisher": "transparenta.eu",
        "period": str(args.year),
        "currency": "RON",
        "provenance": {
            "source": "transparenta-eu-graphql",
            "locator": (
                f"{buget.API}, aggregatedLineItems, account_category vn, "
                f"report_type PRINCIPAL_AGGREGATED, cod funcțional {CODE}, anul {args.year}, "
                "pe uat_ids"
            ),
            "confidence": "verbatim",
            "note": (
                "Suma este cea raportată în execuția bugetară a fiecărei primării, preluată ca "
                "atare. Este jumătatea care revine UAT-ului din impozitul art. 111 alin. (7) "
                "Cod fiscal; cotele și partajul sunt în „assumptions”, iar valoarea tranzacțiilor "
                "nu este calculată aici, pentru că amestecul dintre cota de 1% și cea de 3% nu "
                "se publică."
            ),
        },
        "assumptions": {
            "functionalCode": CODE,
            "localShare": LOCAL_SHARE,
            "rateMinPercent": RATE_MIN_PERCENT,
            "rateMaxPercent": RATE_MAX_PERCENT,
            "formula": "valoare declarată = localTaxRon ÷ localShare ÷ (cotă ÷ 100)",
            "legalBasis": (
                "art. 111 alin. (1) lit. a) și b) și alin. (7) din Legea nr. 227/2015 privind "
                "Codul fiscal, în forma consolidată din sources/cod-fiscal-consolidat.html.gz"
            ),
            "suspectMultipleOfMedian": SUSPECT_MULTIPLE,
        },
        # Named rather than dropped silently, for the same reason as in buget-uat: an exclusion
        # nobody can see is a number nobody can check.
        "excluded": suspects,
        "summary": {
            "uatsReporting": len(rows),
            "localTaxRon": round(local_tax, 2),
            "taxRon": round(tax, 2),
            "declaredValueRon": {"low": round(low, 2), "high": round(high, 2)},
            "largestFiler": (
                {
                    "siruta": largest["siruta"],
                    "name": largest["name"],
                    "localTaxRon": largest["localTaxRon"],
                    "shareOfCountry": round(largest["localTaxRon"] / local_tax, 4),
                }
                if largest and local_tax
                else None
            ),
        },
        "uats": rows,
        "limitations": [
            {
                "id": "cota-efectiva-nu-se-publica",
                "severity": "blocking",
                "text": (
                    "Cota este 3% pentru imobilele deținute cel mult trei ani și 1% peste, iar "
                    "amestecul dintre ele nu se publică nicăieri. Aceeași încasare înseamnă deci "
                    "o valoare tranzacționată de trei ori mai mare sau mai mică, după cum "
                    "predomină revânzările sau vânzările de la dezvoltator. Fișierul nu alege "
                    "între ele: publică încasarea și cele două cote, iar cine împarte trebuie să "
                    "arate ambele capete."
                ),
                "affects": ["transfer-imobiliar", "impozit-teren"],
            },
            {
                "id": "raportare-imposibila-scoasa",
                "severity": "blocking",
                "text": (
                    "Sectorul 5 al Bucureștiului raportează 777,6 milioane de lei sub acest cod, "
                    "de 297 de ori mediana pe locuitor a țării, când primăria capitalei — căreia "
                    "îi revine de fapt impozitul — raportează 45,8 milioane, iar celelalte cinci "
                    "sectoare, zero. Ar fi 59% din impozitul pe transferuri al României. Este "
                    "aceeași primărie pe care execuția bugetară o dă cu sume imposibile și la "
                    "cheltuieli, deci problema e în raportare, nu în întrebare. Este scoasă din "
                    "total și numită în „excluded”."
                ),
                "affects": ["transfer-imobiliar"],
            },
            {
                "id": "e-rulaj-nu-pret",
                "severity": "blocking",
                "text": (
                    "Este bani mișcați, nu preț. Nu vin cu numărul tranzacțiilor și nici cu "
                    "suprafețele, deci spun cât s-a vândut într-o comună, nu cât a costat un "
                    "metru pătrat. Numărul tranzacțiilor se publică de ANCPI, pe județe; fără el "
                    "împărțirea la grilă compară un flux anual cu un stoc."
                ),
                "affects": ["transfer-imobiliar"],
            },
            {
                "id": "imobil-nu-teren",
                "severity": "material",
                "text": (
                    "Impozitul se aplică deopotrivă construcției și terenului de sub ea, într-o "
                    "singură sumă. Exact separarea care lipsește peste tot lipsește și aici, deci "
                    "cifra nu poate fi pusă direct lângă valoarea terenului fără costul de "
                    "reconstrucție al clădirii."
                ),
                "affects": ["transfer-imobiliar", "valoare-nationala"],
            },
            {
                "id": "declaratul-nu-poate-cobori-sub-grila",
                "severity": "material",
                "text": (
                    "Valoarea declarată nu poate fi sub grila notarială, care e prag legal. "
                    "Raportul „declarat ÷ grilă” este deci o limită de jos pentru „piață ÷ "
                    "grilă”: mult peste 1 măsoară subevaluarea, aproape de 1 nu deosebește o "
                    "grilă corectă de o declarare la minim."
                ),
                "affects": ["transfer-imobiliar", "multiplu-piata"],
            },
            {
                "id": "jumatatea-de-stat-lipseste",
                "severity": "note",
                "text": (
                    "Se vede doar jumătatea care revine primăriei. Dublarea ei reface impozitul "
                    "total, cu excepția cazurilor de la art. 111 alin. (7^1), care merg integral "
                    "la bugetul de stat și nu se pot separa — deci totalul de aici este un minim."
                ),
                "affects": ["transfer-imobiliar"],
            },
            {
                "id": "scutirile-nu-apar",
                "severity": "note",
                "text": (
                    "Moștenirile, donațiile între rude până la gradul al III-lea și "
                    "reconstituirile de proprietate nu se impozitează (art. 111 alin. (2)), deci "
                    "nu lasă urmă. Transferurile acoperite aici sunt cele cu titlu oneros între "
                    "vii, nu tot ce își schimbă proprietarul."
                ),
                "affects": ["transfer-imobiliar"],
            },
        ],
    }

    out = ROOT / "data" / f"transfer-imobiliar-{args.year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{len(rows)} UAT-uri, {local_tax / 1e9:.2f} mld lei la primării, "
        f"{tax / 1e9:.2f} mld lei impozit total"
    )
    print(f"valoare declarată: între {low / 1e9:,.0f} și {high / 1e9:,.0f} mld lei")
    if largest:
        print(
            f"cel mai mare filer: {largest['name']} — "
            f"{largest['localTaxRon'] / 1e6:,.1f} mil lei, "
            f"{100 * largest['localTaxRon'] / local_tax:.1f}% din țară"
        )
    print(f"Wrote {out.relative_to(ROOT.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
