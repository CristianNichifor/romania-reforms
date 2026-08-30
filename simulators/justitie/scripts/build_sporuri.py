"""What the judiciary pays above base salary — and what that does to the pension arithmetic.

Three documents in this simulator carried the same blocking caveat: sporuri cannot be found
in the public data, so every figure is base indemnity and every conclusion is an upper or a
lower bound. That caveat was true when it was written and is not true now.

The pay simulator imports transparenta.eu's `entityAnalytics` at `PRINCIPAL_AGGREGATED`,
which rolls every subordinate institution into its ordonator principal de credite. The courts
report under the Înalta Curte de Casație și Justiție, and they are all in there: the line
carries 14.650 filled posts and 2,46 miliarde lei of base salary, which is about 13.976 lei a
month per post — a judges-and-grefieri mix, not a supreme court of roughly a hundred people.

That gives the number nobody had:

    sporuri (10.01.05 + 10.01.06) / salarii de bază (10.01.01) = 24,9%

**This changes the headline of the pension bill.** The bill cuts the rate from 80% to 55% and
widens the base at the same time, from last month's indemnity alone to a five-year average
that includes the sporuri carrying contributions. With sporuri unknown, the only defensible
statement was that the cut is *at most* 31%. That bound still holds — it is what the cut would
be if judges drew no sporuri at all — but it was being read as the figure. With sporuri at a
quarter of base pay, 55% of a base a quarter larger is about 69% of the indemnity, so an even
spread gives a cut nearer 14%. The bound was never wrong; presenting it as the answer was.

**The split between judges and grefieri cannot be closed, and it was worth checking why.** The
July 2026 draft's own justice annex was the obvious place to look: it names no supplement at
all, only coefficients for management posts. Neither does Anexa V of the law in force, which
mentions sporuri once, to say that seniority is already inside the indemnity. The draft's
general list does carry Art. 20 supplements for working conditions, but the frame records that
their size is set by later Government decision, so there is nothing to compute against. Every
route this repository holds ends in the same place.

What can be computed is the weight of each group in the base. Judges are 27,9% of the courts'
base wage bill and 2.961 of 14.650 posts, so the ratio is dominated by auxiliary staff. That
bounds the answer without settling it: if sporuri fall evenly the cut is 14,1%, and if judges
draw none of them it is the 31,2% published before. Where between those the truth sits, the
data cannot say.

Two things this still cannot do, both of which keep a caveat on the result:

  * The ratio is for all 14.650 people the courts employ, and most of them are grefieri, not
    judges. If sporuri fall differently across the two, the judges' own share is not this one.
  * 10.01.05 + 10.01.06 is what the accounting calls supplements. The pension bill's base is
    "sporurile pentru care s-au reținut contribuții", and the draft salary law's 20% ceiling
    has its own named exclusions. Three sets that overlap heavily and match exactly nowhere.

Usage:
    uv run python scripts/build_sporuri.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAY = ROOT.parent / "salarizare" / "data"
PLAFON = PAY / "fiscal" / "plafon-sporuri.json"
HEADCOUNT = PAY / "headcount" / "posturi-ocupate-2026-06.json"
FRAME = PAY / "frames" / "ro-draft-2026-07-16.frame.json"
OUT = ROOT / "data" / "sporuri-2025.json"

# The courts' ordonator principal de credite. Keyed on the fiscal code rather than the name:
# the same institution is spelled four ways across these files, and a name match that silently
# misses would report the judiciary as having no supplements at all.
COURTS_CUI = "4340587"
COURTS_HEADCOUNT_KEY = "inalta-curte-de-casatie-si-justitie"
PROSECUTION_CUI = "4364748"


def entity(series: list[dict], cui: str) -> dict[str, float]:
    """The narrow ratio, the wide ratio and the base wage bill for one principal."""
    found: dict[str, float] = {}
    for s in series:
        dims = s["dims"]
        if dims.get("cui") != cui:
            continue
        if dims["kind"] == "entity":
            found[dims["measure"]] = s["observations"][0]["value"]
        elif dims["kind"] == "entityBase":
            found["base"] = s["observations"][0]["value"]
    return found


def main() -> int:
    for path in (PLAFON, HEADCOUNT, FRAME):
        if not path.exists():
            raise SystemExit(f"Missing {path}; build the pay simulator's data first")

    plafon = json.loads(PLAFON.read_text(encoding="utf-8"))
    courts = entity(plafon["series"], COURTS_CUI)
    prosecution = entity(plafon["series"], PROSECUTION_CUI)
    if not {"narrow", "wide", "base"} <= courts.keys():
        print(
            f"the courts' principal ({COURTS_CUI}) is not in the execution data; "
            "refusing to report a share the source does not carry",
            file=sys.stderr,
        )
        return 1

    posts = next(
        (
            r["filledPosts"]
            for r in json.loads(HEADCOUNT.read_text(encoding="utf-8"))["rows"]
            if r["key"] == COURTS_HEADCOUNT_KEY
        ),
        None,
    )
    if posts is None:
        print("no headcount for the courts; the scope of the ratio cannot be stated", file=sys.stderr)
        return 1

    # The draft salary law's ceiling, read from the frame rather than typed here, so a redraft
    # that moves it off 20% moves this document with it.
    frame = json.loads(FRAME.read_text(encoding="utf-8"))
    cap = next((c for c in frame["caps"] if c["id"] == "cap-sporuri-20"), None)
    if cap is None:
        print("the draft's supplement ceiling is not in the frame", file=sys.stderr)
        return 1
    cap_pct = cap["pct"]

    # Judges' weight inside that payroll, so the reader can see the ratio is mostly grefieri.
    # The judge wage bill is priced on the 2022 scale against 2025 execution, and pay rose in
    # between, so this share is a floor on the judges' true weight, not an estimate of it.
    costuri = json.loads((ROOT / "data" / "costuri-2025.json").read_text(encoding="utf-8"))
    judges_bill = costuri["today"]["annualLei"]
    judges_count = sum(r["judges"] for r in costuri["today"]["byTier"])
    judges_share = judges_bill / courts["base"]

    bill = json.loads((ROOT / "data" / "pensii-2025.json").read_text(encoding="utf-8"))
    now_pct = bill["current"]["percent"] / 100
    then_pct = bill["proposed"]["percent"] / 100

    # The bill's two changes pull against each other. Rate falls; base widens by the sporuri
    # share. Computed at both measures because choosing one would be choosing an argument.
    readings = []
    for measure in ("narrow", "wide"):
        share = courts[measure]
        effective = then_pct * (1 + share)
        readings.append(
            {
                "measure": measure,
                "sporuriShare": round(share, 4),
                "effectivePercentOfIndemnity": round(100 * effective, 1),
                "reductionPercent": round(100 * (now_pct - effective) / now_pct, 1),
            }
        )
    # What the simulator has been publishing: no sporuri in the base at all.
    without = round(100 * (now_pct - then_pct) / now_pct, 1)

    over_cap = courts["narrow"] > cap_pct
    print(f"instanțe (ÎCCJ, ordonator principal): {posts:,} posturi, "
          f"{courts['base'] / 1e9:.2f} mld lei salarii de bază")
    print(f"  sporuri strict (10.01.05+06): {courts['narrow'] * 100:.1f}%")
    print(f"  tot ce e peste bază:          {courts['wide'] * 100:.1f}%")
    print(f"  plafonul proiectului:         {cap_pct * 100:.0f}%  -> "
          f"{'PESTE plafon' if over_cap else 'sub plafon'}")
    if prosecution:
        print(f"  (parchete, pentru context:    {prosecution.get('narrow', 0) * 100:.1f}%)")
    print(f"\npensia, {bill['current']['percent']}% -> {bill['proposed']['percent']}%:")
    print(f"  fără sporuri în bază: scădere de {without:.1f}%   <- ce publicam până acum")
    for r in readings:
        print(f"  cu sporuri ({r['measure']:<6}): {r['effectivePercentOfIndemnity']:.1f}% "
              f"din indemnizație, scădere de {r['reductionPercent']:.1f}%")

    document = {
        "$schema": "../schema/sporuri.schema.json",
        "id": "sporuri-2025",
        "title": "Cât plătesc instanțele peste salariul de bază",
        "publisher": "Ministerul Finanțelor (execuție bugetară), agregat de transparenta.eu",
        "period": "2025",
        "provenance": {
            "source": "transparenta-eu-executie",
            "locator": (
                "entityAnalytics, PRINCIPAL_AGGREGATED, CUI 4340587 (Înalta Curte de Casație "
                "și Justiție ca ordonator principal de credite), 2025"
            ),
            "confidence": "derived",
        },
        "scope": {
            "entity": "Înalta Curte de Casație și Justiție, ordonator principal",
            "filledPosts": posts,
            "baseAnnualLei": round(courts["base"]),
            "baseMonthlyLeiPerPost": round(courts["base"] / posts / 12),
        },
        "sporuri": {
            "narrow": round(courts["narrow"], 4),
            "wide": round(courts["wide"], 4),
            "narrowDescription": "10.01.05 + 10.01.06, paragrafele pe care contabilitatea le numește sporuri",
            "wideDescription": "tot titlul 10.01 în afară de salariul de bază și de decontări",
        },
        "judges": {
            "annualLei": round(judges_bill),
            "count": round(judges_count, 1),
            "shareOfCourtsBase": round(judges_share, 4),
            "shareIsFloor": True,
        },
        "prosecutionNarrow": round(prosecution["narrow"], 4) if prosecution else None,
        "draftCap": {
            "percent": round(cap_pct * 100),
            "overCap": over_cap,
            "gapPercentagePoints": round(100 * (courts["narrow"] - cap_pct), 1),
            "provenance": cap["provenance"],
        },
        "pension": {
            "currentPercent": bill["current"]["percent"],
            "proposedPercent": bill["proposed"]["percent"],
            "reductionWithoutSporuriPercent": without,
            "readings": readings,
            # The two ends of the unknown. Judges drawing no sporuri at all leaves the base
            # unwidened and the published 31,2% standing; an even spread gives 14,1%. The
            # answer is somewhere inside, and nothing here narrows it further.
            "ifJudgesDrawNoSporuriPercent": without,
            "ifSporuriSpreadEvenlyPercent": readings[0]["reductionPercent"],
        },
        "limitations": [
            {
                "id": "raportul-e-pe-tot-personalul",
                "text": (
                    "Procentul este pe toți cei "
                    + f"{posts:,}".replace(",", ".")
                    + " de angajați ai instanțelor. Judecătorii sunt "
                    + f"{judges_count:,.0f}".replace(",", ".")
                    + " dintre ei și "
                    + f"{judges_share * 100:.1f}".replace(".", ",")
                    + "% din masa salarială de bază, deci raportul este dat mai ales de "
                    "grefieri. Dacă sporurile se împart uniform, scăderea pensiei este de "
                    + f"{readings[0]['reductionPercent']:.1f}".replace(".", ",")
                    + "%; dacă judecătorii nu iau deloc sporuri, rămâne "
                    + f"{without:.1f}".replace(".", ",")
                    + "%. Adevărul e între ele și nu se poate localiza din datele de aici."
                ),
                "severity": "material",
                "affects": ["cost", "pensii"],
            },
            {
                "id": "trei-definitii-ale-sporurilor",
                "text": (
                    "10.01.05 și 10.01.06 sunt ce numește contabilitatea sporuri. Baza de "
                    "calcul din proiectul de pensii este „sporurile pentru care s-au reținut "
                    "contribuții”. Plafonul de 20% din proiectul de salarizare își are propriile "
                    "excepții, scrise pe nume. Sunt trei mulțimi care se suprapun mult și nu "
                    "coincid exact cu niciuna."
                ),
                "severity": "material",
                "affects": ["cost", "pensii"],
            },
            {
                "id": "media-pe-60-de-luni-nu-e-modelata",
                "text": (
                    "Proiectul calculează pensia pe media ultimelor 60 de luni, nu pe ultima "
                    "lună. Indemnizațiile au crescut în acest interval, așa că media este sub "
                    "nivelul ultimei luni și scăderea reală este ceva mai mare decât cea de "
                    "aici. Cu cât, nu se poate spune fără seria lunară a indemnizațiilor."
                ),
                "severity": "material",
                "affects": ["pensii"],
            },
            {
                "id": "plafonul-net-nu-e-modelat",
                "text": (
                    "Proiectul scade și plafonul net de la 100% la 70% din venitul net al "
                    "persoanei. Acesta lucrează separat de procent și poate deveni el "
                    "constrângerea efectivă. Nu este inclus în cifrele de aici."
                ),
                "severity": "material",
                "affects": ["pensii"],
            },
            {
                "id": "impartirea-pe-categorii-nu-exista-in-surse",
                "text": (
                    "Anexa de justiție a proiectului de salarizare din iulie 2026 nu prevede "
                    "niciun spor — doar coeficienți pentru funcțiile de conducere. Nici Anexa V "
                    "a legii în vigoare nu prevede: acolo sporul apare o singură dată, ca să "
                    "spună că vechimea este deja inclusă în indemnizație. Sporurile pentru "
                    "condiții de muncă din proiect (Art. 20) își primesc cuantumul prin hotărâre "
                    "de Guvern, care încă nu există. Nu există deci sursă în acest depozit care "
                    "să împartă procentul între judecători și grefieri."
                ),
                "severity": "material",
                "affects": ["cost", "pensii"],
            },
            {
                "id": "ministerul-justitiei-nu-e-comparabil",
                "text": (
                    "Ministerul Justiției apare separat în execuție, dar ca ordonator principal "
                    "el cuprinde și penitenciarele, cu alt regim de sporuri, iar numărul de "
                    "posturi raportat pentru minister nu acoperă același perimetru ca suma "
                    "cheltuită. Linia lui nu este folosită aici."
                ),
                "severity": "note",
                "affects": ["cost"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
