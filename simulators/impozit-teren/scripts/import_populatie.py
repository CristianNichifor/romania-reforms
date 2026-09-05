"""Population by locality, because nothing else in this repository predicts land price.

Twenty-two counties are priced from their notaries' grids and the rest are not, and the only
way to say anything about the country as a whole is to predict the missing ones from the
measured ones. That needs a covariate — something known for all 42 counties that moves with the
price of building land.

Two candidates already in the repository were tried first and both failed, which is why this
file exists:

* **The built share of the county**, from the land register. Regressing the price of building
  land on it gives a slope of 0,37 and an **R² of 0,04** — no relationship at all. Prahova has
  the largest built share in the set, 5,5%, and among the lowest prices per hectare. The share
  measures village sprawl, not urban value.
* **The NUTS2 region.** Under leave-one-out it is *worse than the national mean* — an error
  factor of 2,6 against 2,1. Regions here hold six counties with Cluj and Sălaj in the same
  one, and averaging those two predicts neither.

Population is the covariate that ought to work, because land is dear where people are and the
notaries' grids say so directly: the county price per hectare tracks the size of the county
seat far better than anything about the land itself. INS matrix **POP107D** publishes
population by domicile per locality per year, which is the granularity this needs — a county
total would not distinguish Iași, where a third of the county lives in one city, from Botoșani,
where it does not.

**Population by domicile, not resident population.** POP107D counts where people are
registered, which overstates places people have left and is the series that exists per locality
for every year. The resident series, POP105A, is closer to the truth and stops at county level.
Since what is wanted is a predictor of where the land market is, and land is registered where
people are registered, the domicile series is the better fit as well as the only one available.

Usage:
    uv run python simulators/impozit-teren/scripts/import_populatie.py --all
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

# Same sibling-import pattern the builders use: the scripts here are run as files, not as a
# package, so the directory has to be on the path before one of them can import another.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import retea  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPO = retea.TEMPO
MATRIX = "POP107D"
YEAR = "2024"

# The same spelling table the land register uses. INS writes county names in its own way and
# the rest of the repository joins on two-letter codes.
TO_CODE = {
    "Alba": "AB", "Arad": "AR", "Arges": "AG", "Bacau": "BC", "Bihor": "BH",
    "Bistrita-Nasaud": "BN", "Botosani": "BT", "Braila": "BR", "Brasov": "BV",
    "Buzau": "BZ", "Caras-Severin": "CS", "Calarasi": "CL", "Cluj": "CJ",
    "Constanta": "CT", "Covasna": "CV", "Dambovita": "DB", "Dolj": "DJ", "Galati": "GL",
    "Giurgiu": "GR", "Gorj": "GJ", "Harghita": "HR", "Hunedoara": "HD", "Ialomita": "IL",
    "Iasi": "IS", "Ilfov": "IF", "Maramures": "MM", "Mehedinti": "MH", "Mures": "MS",
    "Neamt": "NT", "Olt": "OT", "Prahova": "PH", "Satu Mare": "SM", "Salaj": "SJ",
    "Sibiu": "SB", "Suceava": "SV", "Teleorman": "TR", "Timis": "TM", "Tulcea": "TL",
    "Vaslui": "VS", "Valcea": "VL", "Vrancea": "VN", "Municipiul Bucuresti": "B",
}


def fold(text: str) -> str:
    """Diacritics off, so that "Bistrița-Năsăud" and "Bistrita-Nasaud" are one county."""
    table = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaissttAAISSTT")
    return text.translate(table).strip()


def metadata() -> dict:
    return retea.tempo_metadata(MATRIX, timeout=180)


def query(meta: dict, county_label: str) -> str:
    """One county's localities for one year, all ages, both sexes.

    Same cell-budget trap as the land register: asking for all 3 182 localities returns HTTP
    200 with an empty body rather than an error, so the county filter is load-bearing and not
    an optimisation.
    """
    dims = meta["dimensionsMap"]

    def options(index: int, match) -> list[dict]:
        return [o for o in dims[index]["options"] if match(o["label"].strip())]

    ages = options(0, lambda label: label.startswith("Total"))
    sexes = options(1, lambda label: label == "Total")
    counties = options(2, lambda label: fold(label) == fold(county_label))
    years = options(4, lambda label: label == f"Anul {YEAR}")
    if not (ages and sexes and counties and years):
        raise SystemExit(
            f"{MATRIX}: missing a selection for {county_label} "
            f"(ages={len(ages)} sexes={len(sexes)} counties={len(counties)} years={len(years)})"
        )
    parent = counties[0]["nomItemId"]
    localities = [o for o in dims[3]["options"] if o.get("parentId") == parent]
    if not localities:
        raise SystemExit(f"{MATRIX}: no localities under {county_label}")

    arr = [ages[:1], sexes, counties, localities, years, dims[5]["options"]]
    return retea.tempo_table(MATRIX, meta, arr)


ROW = re.compile(r"<tr>\s*(<th>.*?</tr>)", re.S)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]", re.S)
LOCALITY = re.compile(r"^(\d+)\s+(.*)$")
# "MUNICIPIUL CLUJ-NAPOCA", "ORAS HUEDIN", "COMUNA AGHIRESU" — the rank is the first word and
# it is what separates a city from a village without needing a separate roster.
RANKED = re.compile(r"^(MUNICIPIUL|ORAS(?:UL)?|COMUNA)\s+(.*)$", re.I)


def parse(table: str, county: str) -> tuple[list[dict], list[str]]:
    people: dict[str, dict] = {}
    problems: list[str] = []
    for match in ROW.finditer(table):
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in CELL.findall(match.group(1))
        ]
        if len(cells) < 2:
            continue
        label, value = cells[-2], cells[-1]
        found = LOCALITY.match(label)
        if not found:
            continue
        siruta, name = found.group(1), found.group(2).strip()
        try:
            count = int(value.replace(" ", "").replace(".", ""))
        except ValueError:
            continue
        rank = RANKED.match(name)
        people[siruta] = {
            "siruta": siruta,
            "name": (rank.group(2) if rank else name).title(),
            "county": county,
            # Normalised, because INS writes both "ORAS" and "ORASUL" in the same column.
            "rank": (
                {"municipiul": "municipii", "oras": "orase", "orasul": "orase"}.get(
                    rank.group(1).lower(), "comune"
                )
                if rank
                else "comune"
            ),
            "people": count,
        }
    if not people:
        problems.append(f"{county}: the table came back with no rows")
    return sorted(people.values(), key=lambda r: -r["people"]), problems


def build(county: str, label: str, meta: dict) -> int:
    rows, problems = parse(query(meta, label), county)
    if not rows:
        print(f"FATAL: {county} returned nothing", file=sys.stderr)
        return 1
    towns = [r for r in rows if r["rank"] != "comune"]
    total = sum(r["people"] for r in rows)
    largest = rows[0]
    document = {
        "$schema": "../schema/populatie.schema.json",
        "id": f"populatie-{county.lower()}-{YEAR}",
        "title": f"Populația după domiciliu pe localități, județul {county}, {YEAR}",
        "publisher": "Institutul Național de Statistică",
        "counties": [county],
        "period": YEAR,
        "unit": "persoane",
        "provenance": {
            "source": f"ins-tempo-{MATRIX.lower()}",
            "locator": f"{TEMPO}/matrix/{MATRIX}, anul {YEAR}, toate vârstele, ambele sexe",
            "confidence": "verbatim",
            "note": (
                "Populație după domiciliu, nu populație rezidentă: numără unde sunt "
                "înregistrate persoanele, nu unde locuiesc. Supraestimează localitățile de "
                "unde s-a plecat. Este singura serie publicată pe localități pentru fiecare an."
            ),
        },
        "summary": {
            "localities": len(rows),
            "people": total,
            "towns": len(towns),
            "urbanPeople": sum(r["people"] for r in towns),
            "urbanSharePercent": round(100 * sum(r["people"] for r in towns) / total, 3),
            "largestName": largest["name"],
            "largestPeople": largest["people"],
            "largestSharePercent": round(100 * largest["people"] / total, 3),
        },
        "localities": rows,
        "limitations": [
            {
                "id": "domiciliu-nu-resedinta",
                "text": (
                    "Populația după domiciliu diferă substanțial de cea rezidentă: cine a "
                    "plecat din țară sau din sat rămâne în evidență acolo unde e înregistrat. "
                    "Pe județe diferența ajunge la câteva procente, pe comunele din care s-a "
                    "emigrat mult este mult mai mare. Folosită aici ca predictor al pieței "
                    "funciare, nu ca măsură a populației."
                ),
                "severity": "material",
                "affects": ["populatie", "valoare-nationala"],
            }
        ]
        + [{"id": "randuri-neinterpretate", "text": p, "severity": "note", "affects": ["populatie"]}
           for p in problems],
    }
    out = ROOT / "data" / f"populatie-{county.lower()}-{YEAR}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{county}: {len(rows)} localități, {total:,} persoane, "
        f"cel mai mare {largest['name']} {largest['people']:,} "
        f"({document['summary']['largestSharePercent']:.1f}%)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", default=None)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    meta = metadata()
    labels = {code: label for label, code in TO_CODE.items()}
    if args.all:
        failed = []
        unreachable = 0
        for code in sorted(labels):
            # Retried, for the same reason the land register is: forty-two requests to TEMPO
            # in a row is more than it reliably answers, and which one it drops is arbitrary.
            # A county that fails all three attempts still fails the build — the predictor has
            # to exist for every county or the national estimate silently omits one.
            status = "ok"
            for retry in range(3):
                try:
                    if build(code, labels[code], meta) == 0:
                        break
                except retea.TempoUnavailable as error:
                    # Not retried. `retea.read` has already spent three attempts and
                    # twenty-five seconds on this county establishing that the host is
                    # refusing connections, and it will refuse them again in two more. Forty-two
                    # counties retried three times each is what turned an outage into a
                    # sixty-three-minute CI step.
                    print(f"{code}: {error}", file=sys.stderr)
                    status = "unreachable"
                    break
                except Exception as error:  # noqa: BLE001
                    print(f"{code}, încercarea {retry + 1}: {error}", file=sys.stderr)
                time.sleep(2 * (retry + 1))
            else:
                status = "failed"
            if status != "ok":
                failed.append(code)
                unreachable += status == "unreachable"
        if failed:
            # Same claim, and the same narrowness, as `import_fond_funciar.outcome`: every
            # county failed, and every one of them failed because the host was not there.
            # Anything less than all of them is still a failure, because a national estimate
            # fitted on forty-one counties is not the one this repository publishes.
            if len(failed) == len(labels) and unreachable == len(failed):
                print(
                    f"\nTEMPO nu a răspuns pentru niciunul dintre cele {len(labels)} de "
                    "județe. Nimic nu a fost importat și nimic nu a fost scris.",
                    file=sys.stderr,
                )
                return retea.UNREACHABLE
            print(f"\nFATAL: {len(failed)} counties failed: {failed}", file=sys.stderr)
            return 1
        print(f"\n{len(labels)} counties written")
        return 0
    code = (args.county or "CJ").upper()
    if code not in labels:
        raise SystemExit(f"unknown county {code}")
    return build(code, labels[code], meta)


if __name__ == "__main__":
    sys.exit(retea.guarded(main))
