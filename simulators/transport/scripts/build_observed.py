"""Turn published county transport programmes into `data/observed-journeys.json`.

Run with `--refetch` to pull the PDFs again; without it, the committed JSON is regenerated
from a local cache if one exists and the script otherwise refuses to run rather than quietly
producing an empty file.

The six counties are not a designed sample. They are the county programmes that publish a
machine-readable table with distance and times in the same row — most publish a scan, which
cannot be read without OCR that would introduce errors nobody could audit. Two of the six
(Bacău, Sălaj) put the distance on a separate line from the times for most of their routes,
so they contribute few rows; that is a parsing limit, not a judgement about those counties,
and the per-county counts are published so a reader can see how lopsided the sample is.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path
from typing import Final

from scripts.observed_journeys import Journey, parse_programme_line, summarise

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "observed-journeys.json"
CACHE = ROOT / "data" / "reports" / "programme-cache"

# County, source URL, and what the document is. Each is an official county council
# publication of the regulated route network — the legal instrument, not a timetable site.
SOURCES: Final[tuple[dict[str, str], ...]] = (
    {
        "county": "Sibiu",
        "url": "https://www.cjsibiu.ro/wp-content/uploads/2020/09/ANEXA-1-14092020.pdf",
        "title": "Programul de transport rutier județean de persoane prin curse regulate, "
        "județul Sibiu (Anexa 1 la HCJ, 14.09.2020)",
    },
    {
        "county": "Brăila",
        "url": "https://www.cjbraila.ro/dm_cj/portal.nsf/131A843C6093D69DC2258B700046ECD9/"
        "$FILE/Programul%20de%20transport%20public%20judetean%20de%20persoane-"
        "%20de%20la%2030.07.2024.pdf",
        "title": "Programul de transport public județean de persoane, județul Brăila, "
        "de la 30.07.2024",
    },
    {
        "county": "Dolj",
        "url": "https://www.cjdolj.ro/portal/siteweb/documente%202021/"
        "PROGRAM%20TRANSPORT%202022-2032.pdf",
        "title": "Programul de transport public rutier de persoane prin curse regulate, "
        "județul Dolj, 2022-2032",
    },
    {
        "county": "Bacău",
        "url": "https://www.csjbacau.ro/dm_cj/portalweb.nsf/"
        "5DCD1CF489BC8373C225881E00362E1E/$FILE/"
        "Final%20Anexa%201%20HCJ%20-%20program%20transport%202023-2032%20corectat%20"
        "%20transparenta.pdf",
        "title": "Programul de transport județean, județul Bacău, 2023-2032 (Anexa 1 la HCJ)",
    },
    {
        "county": "Caraș-Severin",
        "url": "https://cjcs.ro/data_files/content/program-transport-040918.pdf",
        "title": "Programul de transport pentru traseele din județul Caraș-Severin, "
        "01.01.2014-30.06.2019",
    },
    {
        "county": "Sălaj",
        "url": "https://www.cjsj.ro/date/pdfuri/Transport%20public/"
        "program%20transport%20actualizat%20iunie%202024.pdf",
        "title": "Programul de transport public județean, județul Sălaj, actualizat iunie 2024",
    },
)

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def cache_path(source: dict[str, str]) -> Path:
    """Cache filename for a county.

    Diacritics are transliterated rather than stripped: dropping them turns "Brăila" into
    "br-ila", which is a filename nobody can recognise on disk.
    """
    folded = unicodedata.normalize("NFKD", source["county"].lower())
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c))
    # NFKD leaves ș/ț as-is on some builds because they decompose to comma-below, which is not
    # a combining mark in every normalisation path. Map them explicitly.
    ascii_only = ascii_only.translate(str.maketrans({"ș": "s", "ş": "s", "ț": "t", "ţ": "t"}))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return CACHE / f"{slug}.pdf"


def fetch(source: dict[str, str]) -> bytes:
    request = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return response.read()


def journeys_from(pdf: bytes, county: str) -> list[Journey]:
    from io import BytesIO

    from pypdf import PdfReader

    found: list[Journey] = []
    for page in PdfReader(BytesIO(pdf)).pages:
        for raw in (page.extract_text() or "").split("\n"):
            line = re.sub(r"[ \t]+", " ", raw).strip()
            found.extend(parse_programme_line(line, county))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refetch", action="store_true", help="download the programmes again")
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    journeys: list[Journey] = []
    per_source = []

    for source in SOURCES:
        path = cache_path(source)
        if args.refetch or not path.exists():
            if not args.refetch and not path.exists():
                print(f"  {source['county']}: not cached; run with --refetch", file=sys.stderr)
                return 1
            print(f"  fetching {source['county']}...")
            path.write_bytes(fetch(source))
        found = journeys_from(path.read_bytes(), source["county"])
        print(f"  {source['county']:15} {len(found):4} journeys")
        journeys.extend(found)
        per_source.append({**source, "journeys": len(found)})

    if not journeys:
        print("no journeys extracted; refusing to write an empty file", file=sys.stderr)
        return 1

    summary = summarise(journeys)
    document = {
        "$schema": "../schema/observed-journeys.schema.json",
        "what": (
            "Timpi de parcurs observați, citiți din programele de transport județean publicate "
            "de consiliile județene. Fiecare rând al programului dă distanța pe sens și orele "
            "de plecare și sosire, iar raportul lor este viteza comercială reală a unei curse "
            "rurale, cu opriri incluse."
        ),
        "provenance": {
            "source": "programe-transport-judetean",
            "locator": (
                "Programele de transport public județean adoptate prin hotărâre de consiliu "
                "județean, coloanele „Km pe sens” și „Plecare/Sosire”; documentele și "
                "adresele lor sunt listate în câmpul sources al acestui fișier"
            ),
            "confidence": "verbatim",
            "note": (
                "Distanța și orele sunt copiate din tabel fără ajustare. Viteza este raportul "
                "lor, deci derivată aritmetic din două cifre verbatim."
            ),
        },
        "note": (
            "Cifrele sunt citite direct din documentele oficiale, fără ajustare. Ce nu sunt: "
            "un eșantion aleatoriu. Sunt traseele care există, iar un traseu comercial există "
            "unde este cerere, deci pe drumurile mai bune. Rețeaua construită aici trebuie să "
            "deservească și comune pe care niciun operator nu le-a ales. Dacă eșantionul este "
            "deplasat, este deplasat spre rapid."
        ),
        "sources": per_source,
        "summary": summary,
        "journeys": [
            {"county": journey.county, "km": journey.km, "minutes": journey.minutes}
            for journey in journeys
        ],
        "limitations": [
            {
                "id": "esantionul-e-al-traseelor-existente",
                "text": (
                    "Observațiile vin de pe traseele care se operează astăzi, nu de pe rețeaua "
                    "propusă. Un traseu comercial urmează cererea, iar cererea urmează drumul "
                    "bun; comunele fără serviciu sunt, în medie, pe drumuri mai proaste. "
                    "Eșantionul este deci mai degrabă optimist decât pesimist, iar un model "
                    "care îl nimerește este cel mult la fel de rapid ca realitatea."
                ),
                "severity": "material",
                "affects": ["observed-journeys"],
            },
            {
                "id": "sase-judete-dintre-care-patru-cantaresc",
                "text": (
                    "Șase județe, dintre care patru dau aproape toate rândurile: Bacăul și "
                    "Sălajul își scriu distanța pe alt rând decât orele, iar rândul de "
                    "continuare nu poate fi legat de distanța de deasupra fără a ghici. "
                    "Restul județelor publică programul scanat. Eșantionul acoperă câmpie "
                    "(Brăila, Dolj), deal (Sibiu, Sălaj) și munte (Caraș-Severin), dar nu este "
                    "ponderat pe țară."
                ),
                "severity": "material",
                "affects": ["observed-journeys"],
            },
            {
                "id": "orarul-nu-e-parcursul-real",
                "text": (
                    "Ora de sosire din program este ora planificată, nu cea realizată. Un "
                    "operator își pune marjă în orar ca traseul să poată fi respectat, deci "
                    "timpul publicat conține deja acea marjă — ceea ce este exact mărimea de "
                    "care are nevoie un model de cost, pentru că vehiculul și șoferul sunt "
                    "ocupați pe durata din orar, nu pe cea realizată."
                ),
                "severity": "note",
                "affects": ["observed-journeys"],
            },
        ],
    }

    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{summary['count']} journeys, {summary['totalKm']} km, {summary['totalHours']} h")
    print(
        f"  weighted {summary['kmhWeighted']} km/h   median {summary['kmhMedian']}   "
        f"IQR {summary['kmhP25']}-{summary['kmhP75']}"
    )
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
