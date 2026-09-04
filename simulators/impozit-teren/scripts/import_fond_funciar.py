"""How much land there is of each kind, per locality, from the INS land register.

The notaries' grids say what a square metre is worth. They do not say how many there are, and
a tax on land value needs both. INS matrix **AGR101B**, *Suprafata fondului funciar dupa modul
de folosinta, pe judete si localitati*, is the other half: hectares per locality, split by the
same cadastral categories the notaries price — arable, pasture, meadow, vineyard, orchard,
forest, water, built-up, roads, unproductive.

The two taxonomies line up because both are cadastral. Corine Land Cover would be twelve years
fresher and is deliberately not used: it classifies land *cover* from satellite imagery, not
the *category of use* recorded in the land register, and the notaries price the register's
categories. A join between the two would look tighter and mean less.

**The series stops in 2014.** INS discontinued the locality-level breakdown — AGR101B and its
regional sibling AGR101A were both last updated in July 2015, and nothing replaced them at
this granularity. So the areas are 2014 and the values are 2026. Land-use composition moves
slowly, but it does move in one direction: arable becomes built-up, never the reverse, so the
built-up area here is a floor and the land value computed from it is understated rather than
flattering. That is carried as a material limitation, with the direction of the error named,
because a caveat that does not say which way it cuts is not much of a caveat.

**Who owns it is in the same matrix, and it is what a tax base is made of.** AGR101B's second
dimension is `Forme de proprietate`, with exactly two options — `Total` and `Proprietate
privata` — so public land is the subtraction between them, per locality and per category. Both
are fetched. This matters because a land tax is not charged on the whole country: art. 456 of
the Fiscal Code exempts land in the public domain, and roads, rivers and state forest are a
fifth of Romania by area. Valuing every hectare and then taxing every hectare produces a
revenue figure that no treasury could ever collect.

The split is a **proxy for the taxable base, not the base itself**, and it is wrong in both
directions by amounts nobody publishes: the register's "private" includes the private domain
of the state and of the commune, which *is* taxable, while some public-domain land that is
leased or given in administration is taxed to the tenant under art. 463 (2). It is used
because it is measured per locality, which no legal exemption list is.

The check is the source's own arithmetic. AGR101B publishes a Total alongside the categories,
so the ten leaf categories are fetched together with it and must add up. They are independent
numbers in the register, not a derived sum, which is what makes the check worth running: if a
category silently fails to parse out of the HTML table, the total no longer balances and the
import stops rather than publishing a county with land missing. The private side publishes its
own total too and is checked the same way, which is what catches an ownership row landing on
the wrong category.

Usage:
    uv run python simulators/impozit-teren/scripts/import_fond_funciar.py --county BC
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# Same sibling-import pattern the builders use: the scripts here are run as files, not as a
# package, so the directory has to be on the path before one of them can import another.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import retea  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPO = retea.TEMPO
MATRIX = "AGR101B"
YEAR = 2014

# INS county names as the matrix spells them, against the codes the rest of the repository
# uses. All 42, because the register is also the roster every notary grid is checked against:
# a county whose areas are not imported cannot have its grid verified, so this list has to
# lead the grids rather than follow them.
COUNTIES = {
    "AB": "Alba", "AR": "Arad", "AG": "Arges", "BC": "Bacau", "BH": "Bihor",
    "BN": "Bistrita-Nasaud", "BT": "Botosani", "BV": "Brasov", "BR": "Braila",
    "BZ": "Buzau", "CS": "Caras-Severin", "CL": "Calarasi", "CJ": "Cluj",
    "CT": "Constanta", "CV": "Covasna", "DB": "Dambovita", "DJ": "Dolj",
    "GL": "Galati", "GR": "Giurgiu", "GJ": "Gorj", "HR": "Harghita",
    "HD": "Hunedoara", "IL": "Ialomita", "IS": "Iasi", "IF": "Ilfov",
    "MM": "Maramures", "MH": "Mehedinti", "MS": "Mures", "NT": "Neamt",
    "OT": "Olt", "PH": "Prahova", "SM": "Satu Mare", "SJ": "Salaj",
    "SB": "Sibiu", "SV": "Suceava", "TR": "Teleorman", "TM": "Timis",
    "TL": "Tulcea", "VS": "Vaslui", "VL": "Valcea", "VN": "Vrancea",
    "B": "Municipiul Bucuresti",
}

# The land register's categories against the notaries' codes. Two of the register's
# categories fold into one of the notaries' — pasture and meadow are priced together as P+F,
# vineyard and orchard together as V+L — which is a merge the notaries make, not one invented
# here. Forest is left out of the mapping on purpose: the studies price it per hectare in a
# separate table rather than per square metre in the grid, so it cannot be valued with the
# same multiplication and is carried as area only.
TO_NOTARY = {
    "Arabila": "A",
    "Pasuni": "P+F",
    "Finete": "P+F",
    "Vii si pepiniere viticole": "V+L",
    "Livezi si pepiniere pomicole": "V+L",
    # Kept apart rather than merged into the notaries' combined "TAPA SI NP". The extravilan
    # grid prices water (AP) and unproductive land (NP) separately, and merging them here
    # would throw away a distinction the buyer of this data can still use.
    "Ocupata cu ape, balti": "AP",
    "Terenuri degradate si neproductive": "NP",
    "Ocupata cu constructii": "CC",
    "Cai de comunicatii si cai ferate": "DR",
    "Paduri si alta vegetatie forestiera": None,
}
TOTAL_LABEL = "Total"
# The register's only ownership split. Everything not under it is the public domain, which
# art. 456 (1) a) of the Fiscal Code does not tax.
PRIVATE_LABEL = "Proprietate privata"


def metadata() -> dict:
    """The matrix definition, which is also the vocabulary a query has to be written in."""
    return retea.tempo_metadata(MATRIX)


def query(meta: dict, county_label: str) -> str:
    """One county's table, as the HTML the API answers with.

    The options are posted back verbatim rather than as their ids: the endpoint deserialises
    each entry into a typed object and rejects a bare number, which is the whole reason this
    reads the metadata first instead of hard-coding the codes.
    """
    dims = meta["dimensionsMap"]
    wanted = {TOTAL_LABEL, *TO_NOTARY}
    # The ownership dimension is two options and the import subtracts one from the other. A
    # third would make that subtraction wrong rather than incomplete, so it stops here.
    forms = {option["label"].strip() for option in dims[1]["options"]}
    if forms != {TOTAL_LABEL, PRIVATE_LABEL}:
        raise SystemExit(f"AGR101B ownership forms changed: {sorted(forms)}")

    def options(index: int, match) -> list[dict]:
        return [o for o in dims[index]["options"] if match(o["label"].strip())]

    categories = options(0, lambda label: label in wanted)
    if len(categories) != len(wanted):
        found = {o["label"].strip() for o in categories}
        raise SystemExit(f"AGR101B categories changed; missing {sorted(wanted - found)}")

    counties = options(2, lambda label: label == county_label)
    if not counties:
        raise SystemExit(f"AGR101B does not know a county called {county_label!r}")
    # Only this county's localities. Asking for all 3 183 of them returns an empty body
    # rather than an error — the endpoint has a cell budget and exceeding it fails silently,
    # which is the worst of both worlds and the reason the county filter is not optional.
    parent = counties[0]["nomItemId"]
    localities = [o for o in dims[3]["options"] if o.get("parentId") == parent]

    arr = [
        categories,
        # Both forms of ownership, not just the total. The difference is the public domain,
        # which art. 456 does not tax — see the module docstring.
        dims[1]["options"],
        counties,
        localities,
        options(4, lambda label: label == f"Anul {YEAR}"),
        dims[5]["options"],
    ]
    for index, group in enumerate(arr):
        if not group:
            raise SystemExit(f"AGR101B: nothing selected for dimension {index + 1}")

    return retea.tempo_table(MATRIX, meta, arr)


ROW = re.compile(r"<tr>\s*(<th>.*?</tr>)", re.S)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]", re.S)
# "1017 MUNICIPIUL ALBA IULIA" — the SIRUTA code leads the label, which is what makes this
# joinable to the boundaries and the budget without matching on names at all.
LOCALITY = re.compile(r"^(\d+)\s+(.*)$")


def parse(table: str, county: str) -> tuple[dict[str, dict], list[str]]:
    """Hectares per locality per category, keyed by SIRUTA."""
    localities: dict[str, dict] = {}
    problems: list[str] = []
    # The table repeats a label only when it changes and writes "-" underneath it otherwise,
    # so a row read on its own says its category is "-". Carrying the last real label forward
    # is what turns the rows back into records. Read literally, the first version credited
    # every locality's every category to the one category named on the first row.
    carried = ["", "", ""]
    for match in ROW.finditer(table):
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in CELL.findall(match.group(1))
        ]
        if len(cells) != 5:
            continue
        for index in range(3):
            if cells[index] and cells[index] != "-":
                carried[index] = cells[index]
            else:
                cells[index] = carried[index]
        category, ownership, _county, locality, value = cells
        name_match = LOCALITY.match(locality)
        if not name_match:
            problems.append(f"locality label without a SIRUTA code: {locality!r}")
            continue
        siruta, name = name_match.group(1), name_match.group(2)
        try:
            hectares = float(value.replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        record = localities.setdefault(
            siruta,
            {
                "siruta": siruta,
                "name": name,
                "county": county,
                "areaHa": {},
                "totalHa": 0.0,
                "privateAreaHa": {},
                "privateHa": 0.0,
            },
        )
        # The private rows are a subset of the same table, keyed by the same category, so the
        # ownership cell is what decides which of the two sets a row belongs to. Reading it as
        # one set — which is what pinning the dimension to Total used to guarantee — would now
        # double every category, because both forms are fetched.
        area_key, total_key = (
            ("privateAreaHa", "privateHa") if ownership == PRIVATE_LABEL else ("areaHa", "totalHa")
        )
        if category == TOTAL_LABEL:
            record[total_key] = hectares
        else:
            record[area_key][category] = record[area_key].get(category, 0.0) + hectares
    return localities, problems


def outcome(results: list[tuple[str, int, str]]) -> int:
    """What a whole-country run means: 0 ok, `retea.UNREACHABLE` outage, 1 anything else.

    Separated from the run so it can be tested without a network, because this is the piece
    that decides whether CI is allowed to continue and it must not quietly widen. The claim it
    makes is deliberately narrow: **nothing** was imported, and **every** county failed for the
    same reason, and that reason was that TEMPO did not answer.

    A partial import is a failure. Some counties answering and others not is a flaky network
    mid-run at best, and at worst a change that breaks a subset — and either way the roster on
    disk is now half old and half new, which is the state most worth stopping on.
    """
    ok = [code for code, status, _ in results if status == 0]
    if len(ok) == len(results):
        return 0
    failures = [status for _, status, _ in results if status != 0]
    if not ok and all(status == retea.UNREACHABLE for status in failures):
        print(
            "\nEvery county failed the same way: TEMPO did not answer. Nothing was imported "
            "and nothing was written, so this is the source being down rather than the parse "
            "being wrong.",
            file=sys.stderr,
        )
        return retea.UNREACHABLE
    return 1


def run_all(workers: int) -> int:
    """Every county at once. The register is the roster every grid is checked against, so it
    has to exist before any chamber can be parsed, and forty-two serial requests to TEMPO is
    ten minutes of waiting for work that is entirely independent.

    **Retried, because the failure is in the service and not in the county.** Forty-two
    concurrent requests from one runner is more than TEMPO reliably answers: a CI run dropped
    Arad and Bucharest, both of which import on their own without complaint. Which two fail is
    arbitrary, so a single miss must not fail a build that would pass on a second attempt —
    but a county that fails every attempt still has to fail the build, because the register is
    what every grid is checked against and a missing one silently narrows the roster.
    """
    import concurrent.futures  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import time  # noqa: PLC0415

    here = Path(__file__)

    def attempt(code: str) -> tuple[int, str]:
        """The child's exit code and one line about it.

        The code, not a substring of the code's message. An earlier version of `outcome` read
        the last line of stderr looking for "TempoUnavailable", which worked exactly until
        `retea.guarded` started catching that exception and printing a sentence instead — so
        the detector was keyed to the shape of a traceback that no longer happened, and a whole
        country of outages counted as ordinary failures. Exit codes are the interface between
        a process and its caller; the text is for the human reading the log.
        """
        done = subprocess.run(  # noqa: S603
            ["uv", "run", "python", str(here), "--county", code],
            capture_output=True, text=True, cwd=here.parents[3],
        )
        if done.returncode == 0:
            line = next(
                (x for x in done.stdout.splitlines() if "localități" in x), "imported"
            )
            return 0, line
        # The *last* line of stderr, which is the exception or the explanation. Reporting the
        # first eighty characters instead — which is what this did — turns every failure into
        # "Traceback (most recent call last): File /home/runner/work/rom" and tells nobody
        # anything; the CI run that prompted this retry could not be diagnosed from its log.
        tail = [x for x in done.stderr.strip().splitlines() if x.strip()]
        return done.returncode, (tail[-1] if tail else "no output")[:160]

    def one(code: str) -> tuple[str, int, str]:
        for retry in range(3):
            status, line = attempt(code)
            if status == 0:
                return code, 0, line if retry == 0 else f"{line}  (reîncercat de {retry}x)"
            # A host that is refusing connections will refuse them again in two seconds. The
            # retry is for a service that is slow, and `retea.read` has already spent three
            # attempts and twenty-five seconds establishing that this one is not.
            if status == retea.UNREACHABLE:
                return code, status, line
            time.sleep(2 * (retry + 1))
        return code, status, line

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = sorted(pool.map(one, sorted(COUNTIES)))
    ok = [c for c, status, _ in results if status == 0]
    for code, status, line in results:
        print(f"  {'ok  ' if status == 0 else 'FAIL'} {code}: {line}")
    print(f"\n{len(ok)} of {len(results)} counties imported")
    return outcome(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", default="BC", choices=sorted(COUNTIES))
    parser.add_argument(
        "--all",
        action="store_true",
        help="every county, concurrently — the register is the roster each grid needs",
    )
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.all:
        return run_all(args.workers)
    county = args.county

    meta = metadata()
    localities, problems = parse(query(meta, COUNTIES[county]), county)
    if not localities:
        print(f"FATAL: AGR101B returned no rows for {COUNTIES[county]}", file=sys.stderr)
        return 1

    # The source's own arithmetic, used as the check. The leaves and the total are separate
    # numbers in the register, so agreement is evidence the parse kept everything. Run on both
    # forms of ownership: the private side has its own published total, and checking it is
    # what would catch a private row credited to the wrong category — which the combined
    # figures would hide, since they would still add up.
    unbalanced = []
    for record in localities.values():
        for area_key, total_key, label in (
            ("areaHa", "totalHa", "total"),
            ("privateAreaHa", "privateHa", "privat"),
        ):
            leaves = sum(record[area_key].values())
            if record[total_key] and abs(leaves - record[total_key]) > 1:
                unbalanced.append(
                    f"{record['name']} ({record['siruta']}), {label}: categories {leaves:.0f} ha, "
                    f"total {record[total_key]:.0f} ha"
                )
        # Private land is a subset, so more of it than there is land is a parse error rather
        # than a fact about the commune.
        if record["privateHa"] > record["totalHa"] + 1:
            unbalanced.append(
                f"{record['name']} ({record['siruta']}): privat {record['privateHa']:.0f} ha "
                f"depășește totalul {record['totalHa']:.0f} ha"
            )

    rows = sorted(localities.values(), key=lambda r: r["siruta"])
    for record in rows:
        # Fold the register's categories onto the notaries', which is the join everything
        # downstream actually uses. Forest keeps its own line: it is priced per hectare in a
        # separate table, not per square metre in the grid.
        def folded(areas: dict[str, float]) -> dict[str, float]:
            out: dict[str, float] = {}
            for label, hectares in areas.items():
                code = TO_NOTARY.get(label)
                if code:
                    out[code] = round(out.get(code, 0.0) + hectares, 2)
            return out

        record["byCategory"] = folded(record["areaHa"])
        record["byCategoryPrivate"] = folded(record["privateAreaHa"])
        forest = record["areaHa"].get("Paduri si alta vegetatie forestiera", 0.0)
        record["forestHa"] = round(forest, 2)
        record["forestPrivateHa"] = round(
            record["privateAreaHa"].get("Paduri si alta vegetatie forestiera", 0.0), 2
        )
        record["areaHa"] = {k: round(v, 2) for k, v in record["areaHa"].items()}
        record["privateAreaHa"] = {k: round(v, 2) for k, v in record["privateAreaHa"].items()}
        record["privateHa"] = round(record["privateHa"], 2)

    total = sum(r["totalHa"] for r in rows)
    private = sum(r["privateHa"] for r in rows)
    built = sum(r["byCategory"].get("CC", 0.0) for r in rows)
    built_private = sum(r["byCategoryPrivate"].get("CC", 0.0) for r in rows)
    print(f"{COUNTIES[county]} ({county}), anul {YEAR}: {len(rows)} localități")
    print(f"suprafață totală: {total:,.0f} ha   din care curți-construcții: {built:,.0f} ha "
          f"({100 * built / total:.1f}%)")
    print(f"proprietate privată: {private:,.0f} ha ({100 * private / total:.1f}%)   "
          f"din care curți-construcții: {built_private:,.0f} ha "
          f"({100 * built_private / built if built else 0:.1f}% din ele)")
    if unbalanced:
        print(f"\ncategorii care nu însumează totalul ({len(unbalanced)}):")
        for line in unbalanced[:10]:
            print(f"  {line}")
    for problem in problems:
        print(f"  {problem}")

    document = {
        "$schema": "../schema/fond-funciar.schema.json",
        "id": f"fond-funciar-{county.lower()}-{YEAR}",
        "title": f"Fondul funciar după modul de folosință, județul {COUNTIES[county]}, {YEAR}",
        "publisher": "Institutul Național de Statistică",
        "counties": [county],
        "period": str(YEAR),
        "unit": "ha",
        "provenance": {
            "source": f"ins-tempo-{MATRIX.lower()}",
            "locator": (
                f"{TEMPO}/matrix/{MATRIX}, anul {YEAR}, forme de proprietate: "
                f"{TOTAL_LABEL} și {PRIVATE_LABEL}"
            ),
            "confidence": "verbatim",
            "note": (
                "Suprafețele sunt preluate ca atare din matricea INS. Gruparea pe categoriile "
                "notariale (pășuni+fânețe → P+F, vii+livezi → V+L) este făcută aici și "
                "urmează gruparea din grilele notariale. Proprietatea publică nu este "
                "publicată separat: este diferența dintre total și proprietatea privată, "
                "calculată aici prin scădere."
            ),
        },
        "summary": {
            "localities": len(rows),
            "totalHa": round(total, 2),
            "builtHa": round(built, 2),
            "privateHa": round(private, 2),
            "privateBuiltHa": round(built_private, 2),
            "privateSharePercent": round(100 * private / total, 2) if total else 0,
            "unbalanced": unbalanced,
            "problems": problems,
        },
        "categoryMapping": {k: v for k, v in TO_NOTARY.items() if v},
        "localities": rows,
        "limitations": [
            {
                "id": "privat-nu-inseamna-impozabil",
                "text": (
                    "Împărțirea pe forme de proprietate este măsurată, dar „privat” nu este "
                    "același lucru cu „impozabil”. Registrul numără drept privată și "
                    "proprietatea privată a statului și a comunei, care se impozitează; în "
                    "sens invers, terenul din domeniul public dat în concesiune, închiriere "
                    "sau administrare se impozitează chiriașului, potrivit art. 463 alin. (2). "
                    "Niciuna dintre cele două abateri nu este publicată pe localități, așa că "
                    "împărțirea este cea mai bună aproximare măsurată a bazei impozabile, nu "
                    "baza însăși."
                ),
                "severity": "material",
                "affects": ["valoare-teren", "impozit"],
            },
            {
                "id": "suprafetele-sunt-din-2014",
                "text": (
                    "INS a oprit seria pe localități: AGR101B nu are date după 2014 și nimic "
                    "nu a înlocuit-o la această granularitate. Suprafețele sunt deci din 2014, "
                    "iar valorile din 2026. Compoziția fondului funciar se schimbă lent, dar "
                    "într-o singură direcție — arabilul devine curți-construcții, nu invers — "
                    "așa că suprafața construită de aici este un minim, iar valoarea calculată "
                    "din ea este subestimată, nu umflată."
                ),
                "severity": "material",
                "affects": ["valoare-teren", "impozit"],
            },
            {
                "id": "nu-exista-impartire-intravilan-extravilan",
                "text": (
                    "Fondul funciar nu spune ce este intravilan și ce este extravilan, iar "
                    "grilele notariale dau prețuri foarte diferite pentru cele două — la Bacău "
                    "curțile-construcții intravilane din zona A sunt de peste 250 de ori mai "
                    "scumpe pe metru pătrat decât cele extravilane. Împărțirea trebuie deci "
                    "presupusă, nu citită, iar presupunerea este cel mai important parametru "
                    "al oricărei sume calculate din aceste date."
                ),
                "severity": "blocking",
                "affects": ["valoare-teren", "impozit"],
            },
            {
                "id": "padurea-nu-e-in-grila-pe-metru-patrat",
                "text": (
                    "Pădurea este evaluată în studii pe hectar, într-un tabel separat, nu pe "
                    "metru pătrat în grilă. Suprafața ei este păstrată aici, dar nu este "
                    "convertită în valoare cu aceeași înmulțire."
                ),
                "severity": "note",
                "affects": ["valoare-teren"],
            },
        ],
    }

    out = ROOT / "data" / f"fond-funciar-{county.lower()}-{YEAR}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 1 if unbalanced or problems else 0


if __name__ == "__main__":
    sys.exit(retea.guarded(main))
