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

The check is the source's own arithmetic. AGR101B publishes a Total alongside the categories,
so the ten leaf categories are fetched together with it and must add up. They are independent
numbers in the register, not a derived sum, which is what makes the check worth running: if a
category silently fails to parse out of the HTML table, the total no longer balances and the
import stops rather than publishing a county with land missing.

Usage:
    uv run python simulators/impozit-teren/scripts/import_fond_funciar.py --county BC
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPO = "http://statistici.insse.ro:8077/tempo-ins"
MATRIX = "AGR101B"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
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


def metadata() -> dict:
    """The matrix definition, which is also the vocabulary a query has to be written in."""
    cache = ROOT / "sources" / f"ins-{MATRIX.lower()}-metadata.json"
    if not cache.exists():
        print(f"downloading {TEMPO}/matrix/{MATRIX} ...")
        request = urllib.request.Request(f"{TEMPO}/matrix/{MATRIX}", headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(response.read())
    return json.loads(cache.read_text(encoding="utf-8"))


def query(meta: dict, county_label: str) -> str:
    """One county's table, as the HTML the API answers with.

    The options are posted back verbatim rather than as their ids: the endpoint deserialises
    each entry into a typed object and rejects a bare number, which is the whole reason this
    reads the metadata first instead of hard-coding the codes.
    """
    dims = meta["dimensionsMap"]
    wanted = {TOTAL_LABEL, *TO_NOTARY}

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
        options(1, lambda label: label == "Total"),
        counties,
        localities,
        options(4, lambda label: label == f"Anul {YEAR}"),
        dims[5]["options"],
    ]
    for index, group in enumerate(arr):
        if not group:
            raise SystemExit(f"AGR101B: nothing selected for dimension {index + 1}")

    body = json.dumps(
        {
            "language": "ro",
            "arr": arr,
            "matrixName": meta["matrixName"],
            "matrixDetails": meta["details"],
        }
    ).encode()
    request = urllib.request.Request(
        f"{TEMPO}/matrix/{MATRIX}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.loads(response.read())["resultTable"]


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
        category, _ownership, _county, locality, value = cells
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
            siruta, {"siruta": siruta, "name": name, "county": county, "areaHa": {}, "totalHa": 0.0}
        )
        if category == TOTAL_LABEL:
            record["totalHa"] = hectares
        else:
            record["areaHa"][category] = record["areaHa"].get(category, 0.0) + hectares
    return localities, problems


def run_all(workers: int) -> int:
    """Every county at once. The register is the roster every grid is checked against, so it
    has to exist before any chamber can be parsed, and forty-two serial requests to TEMPO is
    ten minutes of waiting for work that is entirely independent."""
    import concurrent.futures  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    here = Path(__file__)

    def one(code: str) -> tuple[str, bool, str]:
        done = subprocess.run(  # noqa: S603
            ["uv", "run", "python", str(here), "--county", code],
            capture_output=True, text=True, cwd=here.parents[3],
        )
        line = next(
            (x for x in done.stdout.splitlines() if "localități" in x), done.stderr.strip()[:80]
        )
        return code, done.returncode == 0, line

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = sorted(pool.map(one, sorted(COUNTIES)))
    ok = [c for c, good, _ in results if good]
    for code, good, line in results:
        print(f"  {'ok  ' if good else 'FAIL'} {code}: {line}")
    print(f"\n{len(ok)} of {len(results)} counties imported")
    return 0 if len(ok) == len(results) else 1


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
    # numbers in the register, so agreement is evidence the parse kept everything.
    unbalanced = []
    for record in localities.values():
        leaves = sum(record["areaHa"].values())
        if record["totalHa"] and abs(leaves - record["totalHa"]) > 1:
            unbalanced.append(
                f"{record['name']} ({record['siruta']}): categories {leaves:.0f} ha, "
                f"total {record['totalHa']:.0f} ha"
            )

    rows = sorted(localities.values(), key=lambda r: r["siruta"])
    for record in rows:
        # Fold the register's categories onto the notaries', which is the join everything
        # downstream actually uses. Forest keeps its own line: it is priced per hectare in a
        # separate table, not per square metre in the grid.
        folded: dict[str, float] = {}
        for label, hectares in record["areaHa"].items():
            code = TO_NOTARY.get(label)
            if code:
                folded[code] = round(folded.get(code, 0.0) + hectares, 2)
        record["byCategory"] = folded
        forest = record["areaHa"].get("Paduri si alta vegetatie forestiera", 0.0)
        record["forestHa"] = round(forest, 2)
        record["areaHa"] = {k: round(v, 2) for k, v in record["areaHa"].items()}

    total = sum(r["totalHa"] for r in rows)
    built = sum(r["byCategory"].get("CC", 0.0) for r in rows)
    print(f"{COUNTIES[county]} ({county}), anul {YEAR}: {len(rows)} localități")
    print(f"suprafață totală: {total:,.0f} ha   din care curți-construcții: {built:,.0f} ha "
          f"({100 * built / total:.1f}%)")
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
            "locator": f"{TEMPO}/matrix/{MATRIX}, anul {YEAR}, forme de proprietate: Total",
            "confidence": "verbatim",
            "note": (
                "Suprafețele sunt preluate ca atare din matricea INS. Gruparea pe categoriile "
                "notariale (pășuni+fânețe → P+F, vii+livezi → V+L) este făcută aici și "
                "urmează gruparea din grilele notariale."
            ),
        },
        "summary": {
            "localities": len(rows),
            "totalHa": round(total, 2),
            "builtHa": round(built, 2),
            "unbalanced": unbalanced,
            "problems": problems,
        },
        "categoryMapping": {k: v for k, v in TO_NOTARY.items() if v},
        "localities": rows,
        "limitations": [
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
    sys.exit(main())
