"""Chapters 4 and 5: the Danish comparison, and whether the paper's own conclusion follows.

Chapter 5.1 ends on the most quotable sentence in the document: *"Romania are de trei ori mai
multe instante decat ar fi necesar pentru populatia si volumul sau de cauze."* Three times too
many. Everything the paper proposes for the judicial map rests on it, and until now nothing
here checked it.

It is checkable, because the chapter states its own premises. Denmark runs 24 district courts,
2 appellate courts and 1 supreme court; Romania runs 175 judecatorii, 15 curti de apel and the
Inalta Curte. Put the two populations beside those counts and the sentence either follows or it
does not.

**It does not, on the half of its own test that can be computed.** At Denmark's courts-per-head,
Romania would run about 76 first-instance courts. It runs 175. That is 2,3 times too many, not
three — the claim overstates itself by roughly a third.

**And the remedy overshoots the model it cites.** The paper's own map leaves 42 first-instance
courts. Denmark's density would put Romania at 76, so 42 is not convergence on Denmark; it is
roughly half the Danish provision per head, arrived at by way of an argument that Denmark is
the standard. The same happens one tier up: Denmark's two appellate courts scale to about six
for Romania, the paper keeps fifteen, and the eight-region variant already in this repository
is the only one of the three near the Danish figure.

**The chapter also miscounts its own country.** It opens 5.1 with "180+ judecatorii" against
the CSM's 175, and "42 tribunale" against 50 tribunal-level courts sitting in 42 towns. Neither
is fatal to the argument, but a comparison is only as good as the side you are supposed to know.

Two honest limits sit on all of this, and they are not small.

The first is that the Danish counts are the paper's. Every attempt to source them independently
failed inside this build — CEPEJ's portal refuses automated access, domstol.dk returns 403, the
e-Justice pages 404. So this is a test of whether the paper's conclusion follows from the
paper's premises, not of whether the premises are true. That is still the right test for a
sentence that says "therefore", but it is a narrower one than it looks.

The second is that the paper's criterion has two halves — *populatia si volumul sau de cauze* —
and only population could be computed. Danish caseload is not available from any source this
build can reach. That gap runs against the finding rather than with it: Romania's courts take
in a very large number of cases, and a caseload test could plausibly justify more courts than a
population test does. The conclusion here is therefore about the half that could be measured,
and says so.

Usage:
    uv run python scripts/build_danemarca.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POPULATION = ROOT / "sources" / "eurostat-populatie-ro-dk.json"
OUT = ROOT / "data" / "danemarca-comparatie.json"

# The paper's own figures for Denmark, from 4.2 and 5.1. Quoted, not verified: see the module
# docstring for why nothing here could corroborate them.
DENMARK = {
    "firstInstance": 24,
    "appellate": 2,
    "supreme": 1,
    "provenance": {
        "source": "reforma-sistem-judiciar-romania",
        "locator": "Capitolul 4.2 și 5.1, p. 20 și 26",
        "confidence": "verbatim",
        "note": (
            "Cifrele daneze sunt ale lucrării. Nicio sursă independentă nu a putut fi citită "
            "automat: portalul CEPEJ, domstol.dk și paginile e-Justice refuză accesul sau nu "
            "mai există la adresele încercate."
        ),
    },
}

# What the paper says Romania has, in the same paragraph it compares from.
PAPER_ROMANIA = {
    "firstInstanceText": "180+ judecatorii",
    "firstInstance": 180,
    "tribunals": 42,
    "appellate": 15,
    "provenance": {
        "source": "reforma-sistem-judiciar-romania",
        "locator": "Capitolul 5.1, p. 26",
        "confidence": "verbatim",
    },
}

PAPER_CLAIM = {
    "text": "Romania are de trei ori mai multe instante decat ar fi necesar pentru populatia si volumul sau de cauze",
    "multiple": 3,
    "provenance": {
        "source": "reforma-sistem-judiciar-romania",
        "locator": "Capitolul 5.1, concluzie, p. 26",
        "confidence": "verbatim",
    },
}


def population() -> dict[str, dict]:
    """Eurostat's population on 1 January, latest year available for both countries."""
    if not POPULATION.exists():
        raise SystemExit(f"Missing {POPULATION}")
    doc = json.loads(POPULATION.read_text(encoding="utf-8"))
    geo = doc["dimension"]["geo"]["category"]["index"]
    time = doc["dimension"]["time"]["category"]["index"]
    values = doc["value"]
    stride = len(time)

    out: dict[str, dict] = {}
    for code, gi in geo.items():
        # Latest year this country actually has a value for; the series is ragged at the end.
        for year, ti in sorted(time.items(), key=lambda kv: kv[0], reverse=True):
            value = values.get(str(gi * stride + ti))
            if value is not None:
                out[code] = {"people": int(value), "year": int(year)}
                break
    missing = {"RO", "DK"} - set(out)
    if missing:
        raise SystemExit(f"Eurostat file has no population for {sorted(missing)}")
    if out["RO"]["year"] != out["DK"]["year"]:
        raise SystemExit(
            f"populations are from different years: RO {out['RO']['year']}, DK {out['DK']['year']}"
        )
    return out


def load(name: str) -> dict:
    path = ROOT / "data" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run the importer that builds it first")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    pop = population()
    located = load("instante-localizate-2025")
    arondare = load("arondare-noua")
    sporuri = load("sporuri-2025")
    curti = load("curti-apel-regiuni")

    tiers: dict[str, int] = {}
    for court in located["courts"]:
        tiers[court["tier"]] = tiers.get(court["tier"], 0) + 1
    tribunal_sites = len(
        {
            tuple(round(v, 4) for v in c["point"])
            for c in located["courts"]
            if c["tier"] == "tribunal" and c.get("point")
        }
    )
    romania = {
        "firstInstance": tiers.get("judecatorie", 0),
        "tribunals": tiers.get("tribunal", 0),
        "tribunalSites": tribunal_sites,
        "appellate": tiers.get("curte-de-apel", 0),
        "supreme": tiers.get("iccj", 0),
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Anexa 1, prin instante-localizate-2025",
            "confidence": "derived",
        },
    }

    def density(people: int, courts: int) -> float:
        return people / courts

    dk_first = density(pop["DK"]["people"], DENMARK["firstInstance"])
    ro_first = density(pop["RO"]["people"], romania["firstInstance"])
    implied_first = pop["RO"]["people"] / dk_first
    dk_appellate = density(pop["DK"]["people"], DENMARK["appellate"])
    implied_appellate = pop["RO"]["people"] / dk_appellate

    # Both of these are read rather than assumed, and a rename upstream should stop this build
    # rather than quietly turn a ratio into a comparison against zero.
    proposed_first = arondare.get("courtSeats")
    if not isinstance(proposed_first, int) or proposed_first <= 0:
        raise SystemExit("arondare-noua no longer carries courtSeats as a count")
    variant_appellate = curti.get("summary", {}).get("variant")
    if not isinstance(variant_appellate, int) or variant_appellate <= 0:
        raise SystemExit("curti-apel-regiuni no longer carries summary.variant as a count")

    first_instance = {
        "denmarkCourts": DENMARK["firstInstance"],
        "denmarkPeoplePerCourt": round(dk_first),
        "romaniaCourts": romania["firstInstance"],
        "romaniaPeoplePerCourt": round(ro_first),
        "impliedAtDanishDensity": round(implied_first, 1),
        # The number the paper's "de trei ori" has to be compared against.
        "actualOverImplied": round(romania["firstInstance"] / implied_first, 2),
        "paperSaysMultiple": PAPER_CLAIM["multiple"],
        "proposedCourts": proposed_first,
        # Below 1 means the proposal is sparser than Denmark, not converging on it.
        "proposedOverImplied": round(proposed_first / implied_first, 2),
        "proposedPeoplePerCourt": round(pop["RO"]["people"] / proposed_first),
    }

    appellate = {
        "denmarkCourts": DENMARK["appellate"],
        "denmarkPeoplePerCourt": round(dk_appellate),
        "romaniaCourts": romania["appellate"],
        "romaniaPeoplePerCourt": round(density(pop["RO"]["people"], romania["appellate"])),
        "impliedAtDanishDensity": round(implied_appellate, 1),
        "actualOverImplied": round(romania["appellate"] / implied_appellate, 2),
        "regionVariantCourts": variant_appellate,
        "regionVariantOverImplied": round(variant_appellate / implied_appellate, 2),
    }

    # Chapter 5.3: Denmark pays a fixed salary and no sporuri; this is how far that is.
    pay = {
        "denmarkHasSporuri": False,
        "romaniaNarrowShare": sporuri["sporuri"]["narrow"],
        "romaniaWideShare": sporuri["sporuri"]["wide"],
        "provenance": {
            "source": "transparenta-eu-executie",
            "locator": "prin sporuri-2025, execuția bugetară a instanțelor",
            "confidence": "derived",
        },
    }

    # What the paper says Romania has, against what the CSM report says it has.
    self_count = {
        "paperFirstInstance": PAPER_ROMANIA["firstInstance"],
        "paperFirstInstanceText": PAPER_ROMANIA["firstInstanceText"],
        "actualFirstInstance": romania["firstInstance"],
        "paperTribunals": PAPER_ROMANIA["tribunals"],
        "actualTribunals": romania["tribunals"],
        "actualTribunalSites": tribunal_sites,
        "paperAppellate": PAPER_ROMANIA["appellate"],
        "actualAppellate": romania["appellate"],
        "appellateAgrees": PAPER_ROMANIA["appellate"] == romania["appellate"],
    }

    print(f"populație (Eurostat, 1 ianuarie {pop['RO']['year']}): "
          f"RO {pop['RO']['people']:,}   DK {pop['DK']['people']:,}\n")
    print("NIVELUL 1")
    print(f"  Danemarca {DENMARK['firstInstance']} instanțe -> 1 la {dk_first:,.0f} de locuitori")
    print(f"  România   {romania['firstInstance']} instanțe -> 1 la {ro_first:,.0f} de locuitori")
    print(f"  la densitatea daneză România ar avea {implied_first:.1f} instanțe; are "
          f"{romania['firstInstance']} = {first_instance['actualOverImplied']}x "
          f"(lucrarea spune {PAPER_CLAIM['multiple']}x)")
    print(f"  propunerea lasă {proposed_first} = {first_instance['proposedOverImplied']}x densitatea daneză "
          f"(1 la {first_instance['proposedPeoplePerCourt']:,} de locuitori)\n")
    print("CURȚI DE APEL")
    print(f"  Danemarca {DENMARK['appellate']} -> 1 la {dk_appellate:,.0f}")
    print(f"  la densitatea daneză România ar avea {implied_appellate:.1f}; are "
          f"{romania['appellate']} = {appellate['actualOverImplied']}x; "
          f"varianta pe regiuni {variant_appellate} = {appellate['regionVariantOverImplied']}x\n")
    print("CE SPUNE LUCRAREA DESPRE ROMÂNIA")
    print(f"  „{PAPER_ROMANIA['firstInstanceText']}” vs {romania['firstInstance']} din raportul CSM")
    print(f"  „{PAPER_ROMANIA['tribunals']} tribunale” vs {romania['tribunals']} instanțe de nivel "
          f"tribunal în {tribunal_sites} orașe")
    print(f"  „{PAPER_ROMANIA['appellate']} curți de apel” vs {romania['appellate']} "
          f"({'se potrivește' if self_count['appellateAgrees'] else 'nu se potrivește'})")

    document = {
        "$schema": "../schema/danemarca.schema.json",
        "id": "danemarca-comparatie",
        "title": "Comparația cu Danemarca: dacă „de trei ori mai multe instanțe” se susține",
        "publisher": "Cristian Nichifor",
        "period": str(pop["RO"]["year"]),
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": "Capitolele 4.2 și 5.1, p. 20 și 26",
            "confidence": "derived",
            "note": (
                "Structura daneză și concluzia sunt citate din lucrare; populațiile sunt de la "
                "Eurostat; numărul instanțelor din România vine din raportul CSM. Densitățile "
                "și rapoartele sunt calculate aici."
            ),
        },
        "population": {
            "romania": pop["RO"]["people"],
            "denmark": pop["DK"]["people"],
            "year": pop["RO"]["year"],
            "provenance": {
                "source": "eurostat-tps00001",
                "locator": "Population on 1 January, tps00001, geo=RO,DK",
                "confidence": "verbatim",
            },
        },
        "denmark": DENMARK,
        "romania": romania,
        "paperRomania": PAPER_ROMANIA,
        "paperClaim": PAPER_CLAIM,
        "firstInstance": first_instance,
        "appellate": appellate,
        "pay": pay,
        "selfCount": self_count,
        "limitations": [
            {
                "id": "volumul-de-cauze-nu-s-a-putut-masura",
                "text": (
                    "Criteriul lucrării are două jumătăți — „populația și volumul său de cauze” "
                    "— și doar prima s-a putut calcula. Volumul de dosare al instanțelor daneze "
                    "nu e accesibil din nicio sursă pe care această construcție o poate citi: "
                    "CEPEJ refuză accesul automat, domstol.dk răspunde 403, paginile e-Justice "
                    "nu mai există la adresele încercate. Lipsa nu e neutră: România are un "
                    "volum de dosare foarte mare, iar un test pe dosare ar putea justifica mai "
                    "multe instanțe decât unul pe populație. Concluzia de aici e despre "
                    "jumătatea care s-a putut măsura."
                ),
                "severity": "blocking",
                "affects": ["firstInstance", "appellate"],
            },
            {
                "id": "cifrele-daneze-sunt-ale-lucrarii",
                "text": (
                    "Cele 24 de instanțe districtuale, 2 curți de apel și 1 curte supremă sunt "
                    "luate din lucrare, nu verificate independent — din același motiv ca mai "
                    "sus. Deci ce se testează aici e dacă concluzia lucrării decurge din "
                    "premisele ei, nu dacă premisele sunt adevărate. Pentru o propoziție care "
                    "spune „prin urmare”, e testul potrivit, dar e mai îngust decât pare."
                ),
                "severity": "blocking",
                "affects": ["firstInstance", "appellate"],
            },
            {
                "id": "densitatea-nu-e-acces",
                "text": (
                    "Instanțe la mia de locuitori nu spune nimic despre cât are de mers un om "
                    "până la ele. Danemarca are 43.000 km² și România 238.000; aceeași densitate "
                    "pe hârtie înseamnă distanțe complet diferite. Distanțele reale sunt "
                    "calculate în altă parte a acestei pagini, pe drumuri, și nu intră aici."
                ),
                "severity": "material",
                "affects": ["firstInstance"],
            },
            {
                "id": "competentele-nu-sunt-aceleasi",
                "text": (
                    "O byret daneză și o judecătorie română nu judecă aceleași lucruri. "
                    "Danemarca și-a comasat instanțele în 2007 dându-le competențe largi; "
                    "România împarte materia între judecătorie, tribunal specializat și "
                    "tribunal. A număra „instanțe de nivel 1” de fiecare parte e cea mai bună "
                    "aproximație disponibilă, nu o echivalență."
                ),
                "severity": "material",
                "affects": ["firstInstance", "appellate"],
            },
            {
                "id": "lucrarea-isi-numara-gresit-tara",
                "text": (
                    "5.1 pornește de la „180+ judecatorii” și „42 tribunale”, când raportul CSM "
                    "dă 175 de judecătorii și 50 de instanțe de nivel tribunal, aflate în 42 de "
                    "orașe. Cifra de 42 pare să numere orașele, nu instanțele. Diferențele nu "
                    "răstoarnă comparația, dar o comparație e la fel de bună ca partea pe care "
                    "se presupune că o știi."
                ),
                "severity": "material",
                "affects": ["selfCount"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
