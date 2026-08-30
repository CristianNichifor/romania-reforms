"""Chapter 16, "Resurse necesare": six numbers, checked against the rest of the repository.

The coverage ledger called this "aritmetică pe care nimeni nu a făcut-o aici — cel mai
substanțial capitol nemodelat", and that was fair but not quite right about why. Chapter 16 is
not missing arithmetic. It is six figures asserted in a bullet list, none of them reconciled
against each other or against the system they are meant to re-equip:

    Financiare   digitalizare 200-300 mil euro
                 reabilitare sedii 500-700 mil euro (10 ani)
                 cresterea personalului auxiliar 150 mil euro anual
    Umane        recrutare 4.000-6.000 personal auxiliar
                 recrutare 1.000 magistrati in 10 ani

Every one of those has something in this repository it has to agree with, and three of them
do not.

**The money line and the headcount line are the same policy, costed twice.** 150 mil euro a
year is meant to pay for 4.000-6.000 auxiliary staff. At the state's own pay grid — the
auxiliary band out of Legea 153/2017, uplifted by the sporuri share the budget execution
actually shows — those people cost well under half of it. The chapter does not say what the
remainder buys, and the two bullets cannot both be the size of the same thing.

**A thousand magistrates in ten years does not fill the holes that exist today.** The CSM
report counts 751 vacant judge posts and 765 vacant prosecution posts on 31 December 2025.
Read as judges alone the recruitment covers the gap with room to spare; read as magistrates in
the ordinary sense — judges and prosecutors — a decade of hiring finishes short of where the
system already is, before a single retirement. The paper does not say which it means, so both
are computed and neither is called the answer.

**The building estimate does not say which estate it is for.** 500-700 mil euro to
rehabilitate court buildings, while chapter 7 of the same document closes most of them: 176
distinct court sites operate today and the proposed map leaves 42, because every appellate
seat is already a tribunal seat and the judecatorii move to the tribunal's building. Spread
over what exists, the estimate is about 3 mil euro a site. Spread over what would remain, four
times that. The chapter is silent on which it costed, and the two readings are not close.

What this file does not do is decide whether the total is affordable. It states the total,
against the one denominator this repository can compute honestly — the base wage bill of the
courts — and marks clearly that a wage bill is not a budget.

Euros are converted at the ECB reference rate for 31 December 2025, the date every staffing
figure here is taken on. The paper never dates its euros; the year's average rate differs from
the year-end one by about 1%, which is reported so a reader can see the choice does not carry
the argument.

Usage:
    uv run --with pypdf python scripts/import_resurse.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "sources" / "reforma-sistem-judiciar-romania.pdf"
FX = ROOT / "sources" / "ecb-eurofx-ron-2025.csv"
OUT = ROOT / "data" / "resurse-necesare.json"

MONTHS = 12
# Chapter 15 runs the reform over ten years, and chapter 16 dates its building programme the
# same way. The one-off figures are spread over that horizon to put them beside the annual one.
HORIZON_YEARS = 10

MILLION = 1_000_000


def load_rate() -> tuple[float, float, str]:
    """The ECB reference rate for the leu, year-end and year-average.

    BNR is the domestic authority but no longer serves its yearly XML at a stable address; the
    ECB publishes the same reference rate for RON and does so through a documented API, so that
    is what is cached here.
    """
    if not FX.exists():
        raise SystemExit(f"Missing {FX}")
    rows = [
        (row["TIME_PERIOD"], float(row["OBS_VALUE"]))
        for row in csv.DictReader(FX.open(encoding="utf-8"))
        if row.get("OBS_VALUE")
    ]
    if not rows:
        raise SystemExit(f"{FX} holds no observations")
    rows.sort()
    last_date, year_end = rows[-1]
    if not last_date.startswith("2025-12"):
        raise SystemExit(f"the cached rate series ends on {last_date}, not in December 2025")
    average = sum(value for _, value in rows) / len(rows)
    return year_end, average, last_date


def read_chapter() -> dict:
    """Chapter 16's own figures, quoted rather than paraphrased.

    Each pattern is anchored inside the chapter and each failure is fatal. A bullet list is
    exactly the kind of thing that survives an edit while changing meaning, and a silent
    fallback here would turn a quotation into an invention.
    """
    from pypdf import PdfReader  # noqa: PLC0415

    if not PAPER.exists():
        raise SystemExit(f"Missing {PAPER}")
    pages = [re.sub(r"\s+", " ", p.extract_text() or "") for p in PdfReader(str(PAPER)).pages]
    found = [i for i, text in enumerate(pages) if re.search(r"(?<!\d)16\.\s*Resurse necesare", text)]
    if not found:
        raise SystemExit("chapter 16 is not in the paper")
    # Last occurrence: the table of contents carries the heading first.
    page_number = found[-1] + 1
    text = pages[found[-1]]

    def rng(pattern: str, label: str) -> tuple[float, float]:
        match = re.search(pattern, text)
        if not match:
            raise SystemExit(f"chapter 16 no longer states {label} the way this script reads it")
        low = float(match.group(1).replace(".", ""))
        high = float(match.group(2).replace(".", ""))
        if low > high:
            raise SystemExit(f"{label}: range reads {low}-{high}, which is backwards")
        return low, high

    digital = rng(r"digitalizare:\s*([\d.]+)-([\d.]+)\s*mil\s*euro", "the digitalisation range")
    buildings = rng(
        r"reabilitare\s*sedii:\s*([\d.]+)-([\d.]+)\s*mil\s*euro", "the building range"
    )
    auxiliary_people = rng(
        r"recrutare\s*([\d.]+)-([\d.]+)\s*personal\s*auxiliar", "the auxiliary recruitment range"
    )

    money = re.search(r"personalului\s*auxiliar:\s*([\d.]+)\s*mil\s*euro\s*anual", text)
    if not money:
        raise SystemExit("chapter 16 no longer states the annual auxiliary figure")
    magistrates = re.search(r"recrutare\s*([\d.]+)\s*magistrati\s*in\s*(\d+)\s*ani", text)
    if not magistrates:
        raise SystemExit("chapter 16 no longer states the magistrate recruitment")

    building_years = re.search(r"reabilitare\s*sedii:[^●]*?\((\d+)\s*ani\)", text)
    institutional = re.findall(r"●\s*(ANIR|platforma digitala|audit extern)", text)

    return {
        "page": page_number,
        "digitalisationMillionEur": list(digital),
        "buildingsMillionEur": list(buildings),
        "buildingsYears": int(building_years.group(1)) if building_years else None,
        "auxiliaryAnnualMillionEur": float(money.group(1).replace(".", "")),
        "auxiliaryRecruits": [int(auxiliary_people[0]), int(auxiliary_people[1])],
        "magistrateRecruits": int(magistrates.group(1).replace(".", "")),
        "magistrateYears": int(magistrates.group(2)),
        "institutional": institutional,
    }


def load(name: str) -> dict:
    path = ROOT / "data" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run the importer that builds it first")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    chapter = read_chapter()
    rate, rate_average, rate_date = load_rate()

    personal = load("personal-2025")
    parchete = load("parchete-2025")
    costuri = load("costuri-2025")
    sporuri = load("sporuri-2025")
    located = load("instante-localizate-2025")

    def eur_to_lei(million_eur: float) -> float:
        return million_eur * MILLION * rate

    # ---- the people the money is supposed to hire -------------------------------------------
    #
    # Base pay is the floor and nobody is paid only that, so the auxiliary band is uplifted by
    # the sporuri share the budget execution actually shows — both the narrow reading (the
    # paragraphs accounting calls sporuri) and the wide one (everything above base pay).
    aux = costuri["auxiliary"]
    narrow, wide = sporuri["sporuri"]["narrow"], sporuri["sporuri"]["wide"]
    band = {
        "baseLowMonthlyLei": aux["lowMonthlyLei"],
        "baseHighMonthlyLei": aux["highMonthlyLei"],
        "withSporuriLowMonthlyLei": round(aux["lowMonthlyLei"] * (1 + narrow), 2),
        "withSporuriHighMonthlyLei": round(aux["highMonthlyLei"] * (1 + wide), 2),
        "sporuriNarrow": narrow,
        "sporuriWide": wide,
    }

    low_recruits, high_recruits = chapter["auxiliaryRecruits"]
    money_lei = eur_to_lei(chapter["auxiliaryAnnualMillionEur"])
    # The most expensive honest reading of the headcount: the top of the band, uplifted by the
    # widest sporuri reading. If the money still exceeds this, it exceeds it on any reading.
    dearest_annual_lei = high_recruits * band["withSporuriHighMonthlyLei"] * MONTHS
    cheapest_annual_lei = low_recruits * band["withSporuriLowMonthlyLei"] * MONTHS
    auxiliary_check = {
        "annualMoneyLei": round(money_lei),
        "recruitsLow": low_recruits,
        "recruitsHigh": high_recruits,
        "band": band,
        "costOfRecruitsDearestLei": round(dearest_annual_lei),
        "costOfRecruitsCheapestLei": round(cheapest_annual_lei),
        # How many times over the money covers the people it is said to pay for.
        "moneyOverDearest": round(money_lei / dearest_annual_lei, 2),
        "moneyOverCheapest": round(money_lei / cheapest_annual_lei, 2),
        "impliedMonthlyLeiAtHigh": round(money_lei / high_recruits / MONTHS),
        "impliedMonthlyLeiAtLow": round(money_lei / low_recruits / MONTHS),
        "unexplainedAnnualLei": round(money_lei - dearest_annual_lei),
    }

    # ---- the magistrates the reform says it will recruit -------------------------------------
    judges_vacant = personal["judgesTotal"]["vacant"]
    prosecutors_vacant = parchete["totals"]["vacant"]
    magistrate_check = {
        "recruits": chapter["magistrateRecruits"],
        "years": chapter["magistrateYears"],
        "perYear": round(chapter["magistrateRecruits"] / chapter["magistrateYears"], 1),
        "judgesVacant": judges_vacant,
        "prosecutorsVacant": prosecutors_vacant,
        "bothVacant": judges_vacant + prosecutors_vacant,
        "coversJudgeVacancies": chapter["magistrateRecruits"] >= judges_vacant,
        "coversBothVacancies": chapter["magistrateRecruits"] >= judges_vacant + prosecutors_vacant,
        "shortfallIfBoth": max(0, judges_vacant + prosecutors_vacant - chapter["magistrateRecruits"]),
    }

    # ---- the buildings -----------------------------------------------------------------------
    #
    # A site, not a court: several courts share one building, and the reform's whole logistical
    # argument is that they should share more of them.
    def sites(tiers: tuple[str, ...]) -> set[tuple[float, ...]]:
        return {
            tuple(round(v, 4) for v in court["point"])
            for court in located["courts"]
            if court.get("point") and court.get("tier") in tiers
        }

    today_sites = sites(("iccj", "curte-de-apel", "tribunal", "judecatorie"))
    # Chapter 7 sends the judecatorii to the tribunal's building; the appellate seats are
    # already tribunal seats, which is why this union is the tribunal count exactly.
    proposed_sites = sites(("tribunal",)) | sites(("curte-de-apel",))
    if not proposed_sites <= today_sites:
        raise SystemExit("the proposed sites are not a subset of today's; the map data changed")
    low_build, high_build = chapter["buildingsMillionEur"]
    buildings_check = {
        "millionEurLow": low_build,
        "millionEurHigh": high_build,
        "years": chapter["buildingsYears"],
        "sitesToday": len(today_sites),
        "sitesProposed": len(proposed_sites),
        "sitesClosed": len(today_sites) - len(proposed_sites),
        "perSiteTodayLowEur": round(low_build * MILLION / len(today_sites)),
        "perSiteTodayHighEur": round(high_build * MILLION / len(today_sites)),
        "perSiteProposedLowEur": round(low_build * MILLION / len(proposed_sites)),
        "perSiteProposedHighEur": round(high_build * MILLION / len(proposed_sites)),
    }

    # ---- what it adds up to, per year, against a wage bill -----------------------------------
    years = chapter["buildingsYears"] or HORIZON_YEARS
    annual_low_eur = (
        chapter["auxiliaryAnnualMillionEur"]
        + low_build / years
        + chapter["digitalisationMillionEur"][0] / HORIZON_YEARS
    )
    annual_high_eur = (
        chapter["auxiliaryAnnualMillionEur"]
        + high_build / years
        + chapter["digitalisationMillionEur"][1] / HORIZON_YEARS
    )
    base_payroll_lei = costuri["reconciliation"]["executionBaseAnnualLei"]
    total = {
        "annualLowMillionEur": round(annual_low_eur, 1),
        "annualHighMillionEur": round(annual_high_eur, 1),
        "annualLowLei": round(eur_to_lei(annual_low_eur)),
        "annualHighLei": round(eur_to_lei(annual_high_eur)),
        "oneOffLowMillionEur": chapter["digitalisationMillionEur"][0] + low_build,
        "oneOffHighMillionEur": chapter["digitalisationMillionEur"][1] + high_build,
        "basePayrollLei": base_payroll_lei,
        "shareOfBasePayrollLow": round(eur_to_lei(annual_low_eur) / base_payroll_lei, 3),
        "shareOfBasePayrollHigh": round(eur_to_lei(annual_high_eur) / base_payroll_lei, 3),
        "horizonYears": years,
    }

    # ---- what it looks like on a terminal ----------------------------------------------------
    print(f"capitolul 16, p. {chapter['page']}   curs BCE {rate_date}: {rate:.4f} lei/euro "
          f"(media anului {rate_average:.4f}, diferență {(rate / rate_average - 1) * 100:+.1f}%)\n")

    print("PERSONAL AUXILIAR — banii față de oameni")
    print(f"  {chapter['auxiliaryAnnualMillionEur']:.0f} mil euro/an = "
          f"{auxiliary_check['annualMoneyLei'] / 1e6:,.0f} mil lei/an")
    print(f"  {low_recruits:,}-{high_recruits:,} de posturi, la {band['withSporuriLowMonthlyLei']:,.0f}"
          f"-{band['withSporuriHighMonthlyLei']:,.0f} lei/lună cu sporuri")
    print(f"  costă {cheapest_annual_lei / 1e6:,.0f}-{dearest_annual_lei / 1e6:,.0f} mil lei/an")
    print(f"  banii acoperă de {auxiliary_check['moneyOverDearest']:.2f}x-"
          f"{auxiliary_check['moneyOverCheapest']:.2f}x ce spune că plătesc; "
          f"{auxiliary_check['unexplainedAnnualLei'] / 1e6:,.0f} mil lei/an nu sunt explicați\n")

    print("MAGISTRAȚI — recrutarea față de posturile goale")
    print(f"  {magistrate_check['recruits']:,} în {magistrate_check['years']} ani "
          f"({magistrate_check['perYear']}/an)")
    print(f"  vacante azi: {judges_vacant} judecători + {prosecutors_vacant} procurori "
          f"= {magistrate_check['bothVacant']}")
    print(f"  acoperă judecătorii: {'da' if magistrate_check['coversJudgeVacancies'] else 'nu'};  "
          f"acoperă ambele: {'da' if magistrate_check['coversBothVacancies'] else 'nu'} "
          f"(lipsă {magistrate_check['shortfallIfBoth']})\n")

    print("SEDII — pe ce parc imobiliar?")
    print(f"  {low_build:.0f}-{high_build:.0f} mil euro / {buildings_check['years']} ani")
    print(f"  azi {buildings_check['sitesToday']} locații -> "
          f"{buildings_check['perSiteTodayLowEur'] / 1e6:.1f}-"
          f"{buildings_check['perSiteTodayHighEur'] / 1e6:.1f} mil euro/locație")
    print(f"  propus {buildings_check['sitesProposed']} locații -> "
          f"{buildings_check['perSiteProposedLowEur'] / 1e6:.1f}-"
          f"{buildings_check['perSiteProposedHighEur'] / 1e6:.1f} mil euro/locație "
          f"({buildings_check['sitesClosed']} închise)\n")

    print("TOTAL")
    print(f"  {total['annualLowMillionEur']:.0f}-{total['annualHighMillionEur']:.0f} mil euro/an "
          f"pe {years} ani = {total['annualLowLei'] / 1e6:,.0f}-{total['annualHighLei'] / 1e6:,.0f} mil lei/an")
    print(f"  salariile de bază ale instanțelor: {base_payroll_lei / 1e6:,.0f} mil lei/an")
    print(f"  cererea = +{total['shareOfBasePayrollLow'] * 100:.0f}% ... "
          f"+{total['shareOfBasePayrollHigh'] * 100:.0f}% peste ele")

    document = {
        "$schema": "../schema/resurse.schema.json",
        "id": "resurse-necesare",
        "title": "Resursele cerute de capitolul 16, față de sistemul pe care îl reechipează",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": f"Capitolul 16, p. {chapter['page']}",
            "confidence": "verbatim",
            "note": (
                "Cifrele capitolului sunt citate. Conversia în lei, împărțirea pe locații și pe "
                "ani, și comparațiile cu posturile vacante și cu grila de salarizare sunt "
                "calculate aici."
            ),
        },
        "exchangeRate": {
            "leiPerEur": rate,
            "date": rate_date,
            "yearAverage": round(rate_average, 4),
            "provenance": {
                "source": "ecb-eurofx-ron-2025",
                "locator": "ECB Data Portal, seria EXR.D.RON.EUR.SP00.A",
                "confidence": "verbatim",
            },
        },
        "chapter": chapter,
        "auxiliaryCheck": auxiliary_check,
        "magistrateCheck": magistrate_check,
        "buildingsCheck": buildings_check,
        "total": total,
        "limitations": [
            {
                "id": "salariile-nu-sunt-buget",
                "text": (
                    "Numitorul este masa salarială de bază a instanțelor — 2,46 miliarde lei — "
                    "nu bugetul justiției, care cuprinde și parchetele, penitenciarele, "
                    "cheltuielile materiale și investițiile. „+50% peste salariile de bază” nu "
                    "înseamnă „+50% la bugetul justiției”, iar procentul din buget ar fi mai "
                    "mic. Comparația e făcută cu singurul numitor pe care depozitul îl poate "
                    "calcula din surse citabile."
                ),
                "severity": "blocking",
                "affects": ["total"],
            },
            {
                "id": "euro-nedatati",
                "text": (
                    "Lucrarea nu spune în ce euro sunt cifrele. Sunt convertiți la cursul de "
                    "referință BCE din 31 decembrie 2025, data la care sunt luate toate "
                    "posturile de aici. Media anului diferă cu circa 1%, deci alegerea datei nu "
                    "schimbă nicio concluzie; inflația de construcții pe zece ani, în schimb, "
                    "ar schimba, și nu e modelată."
                ),
                "severity": "material",
                "affects": ["total", "buildingsCheck"],
            },
            {
                "id": "esalonarea-e-presupusa",
                "text": (
                    "Doar sediile primesc un orizont în lucrare — zece ani. Digitalizarea e o "
                    "sumă fără termen, întinsă aici tot pe zece ani pentru a putea sta lângă o "
                    "cifră anuală, iar planul din capitolul 15 se încheie tot în zece. Alt "
                    "eșalonaj dă alt cost anual, iar suma totală rămâne aceeași."
                ),
                "severity": "material",
                "affects": ["total"],
            },
            {
                "id": "recrutarea-nu-tine-cont-de-plecari",
                "text": (
                    "Comparația dintre 1.000 de magistrați și posturile vacante e statică: "
                    "ignoră pensionările, demisiile și pensia de serviciu pe care capitolul 11 "
                    "o schimbă tocmai în acest interval. Recrutarea netă necesară e mai mare "
                    "decât golul de azi, deci concluzia — că zece ani de recrutare nu ajung "
                    "pentru ambele corpuri — este dacă ceva prea blândă."
                ),
                "severity": "material",
                "affects": ["magistrateCheck"],
            },
            {
                "id": "costul-unui-post-e-doar-salariul",
                "text": (
                    "Un post auxiliar e socotit la salariul de bază din grilă plus cota de "
                    "sporuri din execuția bugetară. Nu include contribuția asiguratorie a "
                    "angajatorului, formarea, spațiul sau echipamentul. Diferența nemotivată "
                    "dintre bani și oameni e deci un maxim, nu o măsură a risipei: o parte din "
                    "ea acoperă costuri reale pe care capitolul nu le enumeră."
                ),
                "severity": "material",
                "affects": ["auxiliaryCheck"],
            },
            {
                "id": "locatiile-sunt-deduse-din-coordonate",
                "text": (
                    "„Locație” înseamnă aici o coordonată distinctă, nu o clădire: două "
                    "instanțe din același oraș pot ocupa sedii diferite, iar una poate ocupa "
                    "mai multe. Cele 176 de locații de azi și cele 42 propuse sunt un ordin de "
                    "mărime al parcului imobiliar, nu un inventar al lui — inventarul nu e "
                    "public într-o formă care să poată fi citită."
                ),
                "severity": "material",
                "affects": ["buildingsCheck"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
