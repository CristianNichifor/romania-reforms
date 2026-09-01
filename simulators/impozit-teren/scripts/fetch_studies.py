"""Find and download every county's land study, in parallel, from the notaries' own index.

Until now each study was a hand-written entry: a path copied out of the page, a county code,
a title. That does not scale to 41 counties and it hides the thing that matters — which
counties have a study at all, and which of the hundred-odd files on that page is it.

The union publishes everything for a year in one flat list: studies, errata, the covering
letters chambers send each other, and the decisions approving them. Only the first kind
prices land. The rest are filtered by name, and what is filtered is reported rather than
dropped quietly, because "this county has no study" and "its study is called something I did
not expect" look identical in a count.

Downloads run concurrently because they are the slow part and they are independent: the
whole country is about 300 MB and the union's server is content to serve it in parallel.

Usage:
    uv run python simulators/impozit-teren/scripts/fetch_studies.py --year 2026
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.unnpr.ro/"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
SOURCES = ROOT / "sources"

# County code against the spellings that appear in these filenames. The union's file names
# are written by 14 different chambers and are not consistent even within one; matching folds
# to bare letters and accepts any of the aliases.
COUNTY_ALIASES: dict[str, list[str]] = {
    "AB": ["alba"], "AR": ["arad"], "AG": ["arges"], "BC": ["bacau"], "BH": ["bihor"],
    "BN": ["bistrita", "bistritanasaud", "bn"], "BT": ["botosani", "bt"], "BV": ["brasov"],
    "BR": ["braila"], "BZ": ["buzau"], "CS": ["carasseverin", "caras"], "CL": ["calarasi"],
    "CJ": ["cluj", "cj"], "CT": ["constanta"], "CV": ["covasna"], "DB": ["dambovita"],
    "DJ": ["dolj"], "GL": ["galati"], "GR": ["giurgiu"], "GJ": ["gorj"],
    "HR": ["harghita"], "HD": ["hunedoara"], "IL": ["ialomita"], "IS": ["iasi"],
    "IF": ["ilfov"], "MM": ["maramures", "mm"], "MH": ["mehedinti"], "MS": ["mures"],
    "NT": ["neamt"], "OT": ["olt"], "PH": ["prahova"], "SM": ["satumare"],
    "SJ": ["salaj", "sj"], "SB": ["sibiu"], "SV": ["suceava", "sv"], "TR": ["teleorman"],
    "TM": ["timis"], "TL": ["tulcea"], "VS": ["vaslui"], "VL": ["valcea"],
    "VN": ["vrancea"], "B": ["bucuresti"],
}
# Mureș is a substring of nothing, but Timiș is a substring of Timișoara, the chamber's own
# name, which appears in every path from that chamber. Longer aliases are tried first and the
# directory segment is excluded from matching for exactly this reason.
NOT_A_STUDY = re.compile(
    r"adresa|erata|errata|hotarare|hotarire|decizi|semnatur|pag_|update|"
    r"viza_anaf|studiu_unnpr|grila_notari",
    re.I,
)
# Deliberately no "looks like a study" pattern. Half of them are called one — Studiu_de_
# piata_Timis_2026 — and half are called nothing but their county, ALBA_2026.pdf. Requiring
# the word lost fourteen counties including three that were already parsing. Naming a county
# and not being an erratum is the whole test.

# Which counties a chamber speaks for, used only when the filename names none of them: the
# Pitești chamber calls its study after itself, not after Argeș.
CHAMBER_COUNTIES: dict[str, list[str]] = {
    "CNPAlbaIulia": ["AB", "SB", "HD"], "CNPBacau": ["BC", "NT"], "CNPBrasov": ["BV", "CV"],
    "CNPBucuresti": ["B", "CL", "GR", "IL", "IF", "TR"], "CNPCluj": ["CJ", "BN", "MM", "SJ"],
    "CNPConstanta": ["CT", "TL"], "CNPCraiova": ["DJ", "GJ", "MH", "OT"],
    "CNPGalati": ["GL", "BR", "VN"], "CNPIasi": ["IS", "VS"], "CNPOradea": ["BH", "SM"],
    "CNPPitesti": ["AG", "VL"], "CNPPloiesti": ["PH", "BZ", "DB"],
    "CNPSuceava": ["SV", "BT"], "CNPTarguMures": ["MS", "HR"],
    "CNPTimisoara": ["TM", "AR", "CS"],
}


def fold(text: str) -> str:
    stripped = unicodedata.normalize("NFD", str(text).lower())
    stripped = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    stripped = stripped.translate(str.maketrans({"ş": "s", "ţ": "t", "ș": "s", "ț": "t"}))
    return re.sub(r"[^a-z0-9]+", "", stripped)


def index_page() -> str:
    cache = SOURCES / "unnpr-index.html"
    if not cache.exists():
        request = urllib.request.Request(BASE, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(response.read())
    return cache.read_text(encoding="utf-8", errors="ignore")


def counties_in(filename: str) -> list[str]:
    """Which counties a file names, matched on the filename alone.

    The directory is deliberately excluded: every path from the Timișoara chamber contains
    "CNPTimisoara", and "timis" is a substring of it, so matching the whole path would file
    Arad's study under Timiș as well.
    """
    key = fold(filename)
    found = []
    for code, aliases in COUNTY_ALIASES.items():
        if any(alias in key for alias in sorted(aliases, key=len, reverse=True)):
            found.append(code)
    return found


def discover(year: int) -> tuple[list[dict], list[str]]:
    page = index_page()
    links = sorted(
        {
            match
            for match in re.findall(rf'href="(files/expertize{year}/[^"]+\.pdf)"', page, re.I)
        }
    )
    studies: list[dict] = []
    skipped: list[str] = []
    for path in links:
        name = path.rsplit("/", 1)[-1]
        if NOT_A_STUDY.search(name):
            skipped.append(path)
            continue
        chamber = path.split("/")[2]
        codes = counties_in(name)
        source = "filename"
        if not codes:
            codes = CHAMBER_COUNTIES.get(chamber, [])
            source = "chamber"
        if not codes:
            skipped.append(path)
            continue
        studies.append(
            {
                "key": f"{fold(name)[:48]}-{year}",
                "path": path,
                "chamber": chamber,
                "counties": codes,
                "countySource": source,
                "file": name,
            }
        )
    return studies, skipped


def download(study: dict) -> tuple[str, int, str]:
    out = SOURCES / "studies" / study["file"]
    if out.exists() and out.stat().st_size > 0:
        return study["file"], out.stat().st_size, "cached"
    url = BASE + urllib.parse.quote(study["path"])
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        return study["file"], 0, f"failed: {exc}"
    return study["file"], out.stat().st_size, "downloaded"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    studies, skipped = discover(args.year)
    covered = sorted({code for study in studies for code in study["counties"]})
    missing = sorted(set(COUNTY_ALIASES) - set(covered))
    print(f"{len(studies)} candidate studies, {len(skipped)} other files skipped")
    print(f"counties named: {len(covered)} of {len(COUNTY_ALIASES)}")
    if missing:
        print(f"no {args.year} study found for: {missing}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(download, studies))
    failed = [name for name, _, status in results if status.startswith("failed")]
    total = sum(size for _, size, _ in results)
    fresh = sum(1 for _, _, status in results if status == "downloaded")
    print(f"downloaded {fresh}, cached {len(results) - fresh - len(failed)}, "
          f"failed {len(failed)}, {total / 1e6:.0f} MB")
    for name in failed:
        print(f"  failed: {name}")

    manifest = {
        "year": args.year,
        "studies": studies,
        "countiesCovered": covered,
        "countiesMissing": missing,
        "skipped": skipped,
        "failed": failed,
    }
    out = SOURCES / f"studies-{args.year}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
