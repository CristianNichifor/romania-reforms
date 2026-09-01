"""The yield on the land under buildings, read from its derivation rather than assumed.

This module exists because of a contradiction the repository carried for a long time. The rent
builder capitalised building land at an assumed **3–7%**, anchored on the observed gross
residential yield. Meanwhile `build_randament_construit.py` derived, from an identity whose
every other term is published, that the same yield is about **2,5%** — and the rent builder's
own limitation said so out loud:

    "plafonul deducerii este aproximativ podeaua benzii folosite aici, deci renta terenului
     construit este probabil supraestimată"

Four separate routes now put land yields in the same place, and none of them is near 5%:

    arabil        1,43%   measured   arendă ÷ preț, INS via Eurostat
    pășuni/fânețe 1,61%   measured   the same survey
    pădure        2,27%   derived    harvest × standing price − owner's costs
    curți-constr. 2,53%   derived    property yield − depreciation × building share

Keeping 5% for the largest category while three neighbouring categories were measured or
derived below 2,3% was not a conservative choice. It was an inconsistency that made the rent
roughly twice as large as this repository's own evidence supports, and therefore made the
Fiscal Code's capture of that rent roughly half what it should read.

**One band, not an urban and a rural one.** The derivation does split them — 2,73% urban
against 2,52% rural — and the split is real: the land share of a property is a third in the
centre of Iași and a sixteenth in a Harghita village. It is not used here because the gap
between the two, 0,2 points, is small against the width of either band, 1,7–3,2. Splitting
would publish a distinction finer than the thing being distinguished. Both figures are carried
in the output so anyone who disagrees can see what they would be splitting on.

**The band stays wide and stays a band.** The point is not that 2,53 is right. It is that the
whole of the assumed 3–7% sits above the derived band's central estimate, and the derived
band's ceiling — 3,18% — is barely above the assumption's floor.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANDS = ("low", "central", "high")

# What the repository used to assume, kept so that every builder can report the move rather
# than silently publishing a different number than it did last month.
ASSUMED = {"low": 3.0, "central": 5.0, "high": 7.0}
ASSUMED_SOURCE = (
    "Randamentul brut rezidențial observat în România, cca. 6,3% în T3 2025 (Global Property "
    "Guide), 5–6% net de cheltuieli; terenul se capitalizează sub acest nivel pentru că nu se "
    "amortizează."
)


def built() -> tuple[dict[str, float], str, dict]:
    """The derived band, its provenance sentence, and the whole derivation for reference.

    Falls back to the old assumption — loudly, in the returned source string — when the
    derivation has not been built, so that a fresh checkout still produces numbers and says
    which ones they are.
    """
    path = ROOT / "data" / "randament-teren-construit-2026.json"
    if not path.exists():
        return dict(ASSUMED), "PRESUPUS (deducerea nu e construită): " + ASSUMED_SOURCE, {}
    document = json.loads(path.read_text(encoding="utf-8"))
    summary = document["summary"]
    band = {b: round(summary["derivedYieldPercent"][b], 4) for b in BANDS}
    urban = summary.get("urbanDerivedYieldPercent")
    rural = summary.get("ruralDerivedYieldPercent")
    where = ", ".join(document["counties"])
    source = (
        f"Dedus, nu măsurat: randament net al proprietății − amortizarea clădirii × ponderea "
        f"clădirii, r = y_net − δ·(1 − λ). Ponderea terenului λ = "
        f"{summary['landSharePercent']['central']:.1f}% este calculată din "
        f"{summary['pairs']} perechi preț-teren/preț-construcție publicate pe aceeași pagină în "
        f"grilele notariale ({where}); randamentul brut este cel al Global Property Guide, "
        f"amortizarea este cea din HG 2139/2004. "
        f"Înlocuiește banda presupusă anterior "
        f"{ASSUMED['low']:.0f}–{ASSUMED['high']:.0f}%."
    )
    if urban and rural:
        source += (
            f" Deducerea separă urbanul ({urban['central']:.2f}%) de rural "
            f"({rural['central']:.2f}%); diferența de "
            f"{abs(urban['central'] - rural['central']):.2f} puncte este mai mică decât "
            f"lățimea benzii, deci se folosește una singură."
        )
    return band, source, summary


def limitation(band: dict[str, float]) -> dict:
    """The blocking limitation that has to travel with the number, wherever it is used."""
    return {
        "id": "randamentul-construit-e-dedus-nu-masurat",
        "text": (
            "Randamentul terenului de sub clădiri nu este măsurat nicăieri în România: grilele "
            "notariale publică prețuri, nu chirii, iar redevențele de concesiune se negociază "
            "contract cu contract. Banda folosită aici, "
            f"{band['low']:.2f}–{band['high']:.2f}% cu {band['central']:.2f}% la mijloc, este "
            "dedusă din identitatea r = randament_net − amortizare × (1 − pondere_teren), ale "
            "cărei trei intrări sunt parametri declarați (randament brut, cotă de cheltuieli, "
            "raport lot/suprafață construită). Ea înlocuiește banda presupusă 3–7% folosită "
            "până acum, care era ancorată într-un randament rezidențial brut și pe care "
            "deducerea o contrazicea: renta scade cu circa jumătate și captura impozitului "
            "actual se dublează. Cum curțile-construcții sunt circa 64% din valoare, cea mai "
            "mare parte a rentei raportate depinde de această deducere. Eșantionul ei — trei "
            "județe fără grilă pentru București, Cluj sau Timiș — o înclină în jos."
        ),
        "severity": "blocking",
        "affects": ["renta", "captura"],
    }
