"""The service pension, as it is and as the November 2025 bill would rewrite it.

Chapter 11 of the reform paper argues the pensions of magistrates are the least defensible
part of the system. While it was being written the Government put its own bill into public
debate — signed by the Ministry of Justice on 19 November 2025 — and that bill is a different
document with different numbers. Both are modelled here, separately, because a simulator that
merged them would let one borrow the other's authority.

The bill changes four things at once, which is why the headline understates it in one
direction and overstates it in another:

    vechime          25 ani  ->  35 ani
    procent             80%  ->     55%
    baza de calcul   indemnizatia bruta din ultima luna
                     ->  media indemnizatiilor brute *si a sporurilor* pe 60 de luni
    plafon net    100% din net-ul ultimei luni  ->  70%

**80% to 55% is not a 31% cut.** The base widens at the same time: the old rule counts the
last month's indemnity alone, the new one averages five years and includes the sporuri that
carried social contributions. How much that offsets depends on how large sporuri are, which is
the number nobody publishes — so the arithmetic here is done on indemnity alone and is
therefore an upper bound on the cut, not an estimate of it.

Usage:
    uv run --with pypdf python scripts/import_pensii.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "lege-pensii-magistrati-2025"
SOURCE_FILE = ROOT / f"sources/{SOURCE}.pdf"
URL = (
    "https://mmuncii.gov.ro/wp-content/uploads/2025/11/"
    "Lege-pensii-magistrati-semnat-de-MJ-19-11-ora-17-13-1.pdf"
)
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
OUT = ROOT / "data" / "pensii-2025.json"
GRADES = ROOT / "data" / "indemnizatii-2022.json"

# The rules in force, from Legea 303/2022 as it stands before the bill.
CURRENT = {
    "seniorityYears": 25,
    "percent": 80,
    "baseDescription": "indemnizația de încadrare brută din ultima lună de activitate",
    "netCapPercent": 100,
    "provenance": {
        "source": "legea-303-2022",
        "locator": "art. 211 alin. (1), înainte de modificare",
        "confidence": "derived",
        "note": (
            "Regula în vigoare, descrisă prin ceea ce proiectul din 2025 înlocuiește. "
            "Textul consolidat al Legii 303/2022 nu se află în depozit."
        ),
    },
}


def download() -> Path:
    if SOURCE_FILE.exists():
        return SOURCE_FILE
    import urllib.request

    print(f"downloading {URL} ...")
    request = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        data = response.read()
    SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_bytes(data)
    return SOURCE_FILE


def main() -> int:
    reader = PdfReader(str(download()))
    text = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in reader.pages))

    # Read the four numbers out of the bill rather than transcribing them, so a different
    # draft cannot be described by this file's prose while carrying other figures.
    percent = re.search(r"pensie de serviciu în cuantum de (\d{2})\s*%", text)
    months = re.search(r"ultimele (\d{2}) de luni de activitate", text)
    cap = re.search(r"nu poate fi mai mare de (\d{2,3})\s*% din venitul net", text)
    seniority = re.search(r"vechime totală în muncă de cel puţin (\d{2}) de ani", text)
    if not all((percent, months, cap, seniority)):
        print(
            "the bill's wording changed; refusing to guess: "
            f"percent={bool(percent)} months={bool(months)} cap={bool(cap)} "
            f"seniority={bool(seniority)}",
            file=sys.stderr,
        )
        return 1

    proposed = {
        "seniorityYears": int(seniority.group(1)),
        "percent": int(percent.group(1)),
        "baseMonths": int(months.group(1)),
        "baseIncludesSporuri": True,
        "baseDescription": (
            "media indemnizațiilor de încadrare brute lunare și a sporurilor pentru care "
            f"s-au reținut contribuții, pe ultimele {months.group(1)} de luni"
        ),
        "netCapPercent": int(cap.group(1)),
        "provenance": {
            "source": SOURCE,
            "locator": "Art. I pct. 1, modificând art. 211 alin. (1) din Legea nr. 303/2022",
            "confidence": "verbatim",
        },
    }

    grades = json.loads(GRADES.read_text(encoding="utf-8"))["grades"]
    comparison = []
    for grade in grades:
        monthly = grade["monthlyLei"]
        now = monthly * CURRENT["percent"] / 100
        # Indemnity only: the bill's base also counts sporuri, which are not published, so
        # this is the floor of the new pension and the ceiling of the reduction.
        then = monthly * proposed["percent"] / 100
        comparison.append(
            {
                "grade": grade["name"],
                "monthlyLei": monthly,
                "currentLei": round(now),
                "proposedFloorLei": round(then),
                "reductionPercent": round(100 * (now - then) / now, 1),
            }
        )

    print(f"vechime {CURRENT['seniorityYears']} -> {proposed['seniorityYears']} ani")
    print(f"procent {CURRENT['percent']}% -> {proposed['percent']}%")
    print(f"baza    ultima lună -> media pe {proposed['baseMonths']} de luni, cu sporuri")
    print(f"plafon  {CURRENT['netCapPercent']}% -> {proposed['netCapPercent']}% din net\n")
    print(f"{'grad':<44}{'azi':>10}{'prag nou':>11}{'scădere':>10}")
    for row in comparison:
        print(f"{row['grade'][:42]:<44}{row['currentLei']:>10,}"
              f"{row['proposedFloorLei']:>11,}{row['reductionPercent']:>9.1f}%")

    document = {
        "$schema": "../schema/pensii.schema.json",
        "id": "pensii-2025",
        "title": "Pensia de serviciu a magistraților: regula de azi și proiectul din 2025",
        "publisher": "Guvernul României",
        "period": "2025",
        "provenance": {
            "source": SOURCE,
            "locator": "Lege pentru modificarea unor acte normative din domeniul pensiilor de serviciu, semnată de MJ la 19 noiembrie 2025",
            "confidence": "verbatim",
        },
        "current": CURRENT,
        "proposed": proposed,
        "byGrade": comparison,
        "limitations": [
            {
                "id": "sporurile-nu-sunt-publice",
                "text": (
                    "Proiectul lărgește baza de calcul: pe lângă indemnizație intră și "
                    "sporurile pentru care s-au reținut contribuții, pe cinci ani. Scăderea "
                    "calculată aici — doar pe indemnizație — este deci maximul posibil, nu o "
                    "estimare. Cu sporurile instanțelor la 24,9% din salariile de bază, "
                    "trecerea de la 80% la 55% taie în jur de 14%, nu 31% (vezi sporuri-2025)."
                ),
                "severity": "material",
                "affects": ["pensii"],
            },
            {
                "id": "regula-actuala-e-dedusa",
                "text": (
                    "Textul consolidat al Legii 303/2022 nu se află în depozit; regula de azi "
                    "este descrisă prin ceea ce proiectul înlocuiește. Cifrele ei sunt marcate "
                    "ca derivate, nu citate."
                ),
                "severity": "material",
                "affects": ["pensii"],
            },
            {
                "id": "proiect-nu-lege",
                "text": (
                    "Este un proiect pus în dezbatere publică în noiembrie 2025, nu o lege în "
                    "vigoare. Ce va fi adoptat poate diferi."
                ),
                "severity": "material",
                "affects": ["pensii"],
            },
            {
                "id": "nu-stim-cati-pensionari",
                "text": (
                    "Numărul magistraților pensionați și vârstele lor nu se află în datele "
                    "publice de aici, deci costul total al pensiilor de serviciu — și "
                    "economia pe care ar aduce-o proiectul — nu se pot calcula. Aici se "
                    "compară doar regulile, la nivel de o singură pensie."
                ),
                "severity": "blocking",
                "affects": ["pensii", "cost"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
