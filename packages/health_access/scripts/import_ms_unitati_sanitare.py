"""Extract Ministry of Health provider address evidence from the public map page.

The source page embeds marker popups with provider names, addresses, detail
links and marker coordinates. This importer keeps a compact, auditable extract
and leaves the raw HTML page out of git.

Usage:
    uv run python packages/health_access/scripts/import_ms_unitati_sanitare.py
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID: Final[str] = "ministerul-sanatatii-unitati-sanitare-2026"
OUT = PACKAGE_ROOT / "sources/ms-unitati-sanitare-2026.json"
TRANSFORM_VERSION: Final[int] = 2
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
MS_UNITATI_SANITARE_URL: Final[str] = "https://ms.ro/ro/unitati-sanitare/"

COUNTY_CODE_BY_NAME: Final[dict[str, str]] = {
    "ALBA": "AB",
    "ARAD": "AR",
    "ARGES": "AG",
    "BACAU": "BC",
    "BIHOR": "BH",
    "BISTRITA NASAUD": "BN",
    "BOTOSANI": "BT",
    "BRAILA": "BR",
    "BRASOV": "BV",
    "BUCURESTI": "B",
    "BUZAU": "BZ",
    "CALARASI": "CL",
    "CARAS SEVERIN": "CS",
    "CLUJ": "CJ",
    "CONSTANTA": "CT",
    "COVASNA": "CV",
    "DAMBOVITA": "DB",
    "DOLJ": "DJ",
    "GALATI": "GL",
    "GIURGIU": "GR",
    "GORJ": "GJ",
    "HARGHITA": "HR",
    "HUNEDOARA": "HD",
    "IALOMITA": "IL",
    "IASI": "IS",
    "ILFOV": "IF",
    "MARAMURES": "MM",
    "MEHEDINTI": "MH",
    "MURES": "MS",
    "NEAMT": "NT",
    "OLT": "OT",
    "PRAHOVA": "PH",
    "SALAJ": "SJ",
    "SATU MARE": "SM",
    "SIBIU": "SB",
    "SUCEAVA": "SV",
    "TELEORMAN": "TR",
    "TIMIS": "TM",
    "TULCEA": "TL",
    "VALCEA": "VL",
    "VASLUI": "VS",
    "VRANCEA": "VN",
}


def normalise_text(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" -\t\r\n")


def read_source_text(location: str | Path) -> str:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read().decode("utf-8")
    return Path(text).read_text(encoding="utf-8")


def county_code(value: object) -> str | None:
    return COUNTY_CODE_BY_NAME.get(normalise_text(value).replace("-", " "))


def county_code_from_address(address: str) -> str | None:
    text = f" {normalise_text(address).replace('-', ' ')} "
    for name, code in sorted(
        COUNTY_CODE_BY_NAME.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if re.search(rf"\b{name}\b", text):
            return code
    return None


def has_street_address(address: str, name: str) -> bool:
    normalised_address = normalise_text(address)
    if not normalised_address or normalised_address == normalise_text(name):
        return False
    if re.match(r"^https?://", address.strip(), re.IGNORECASE):
        return False
    if re.fullmatch(r"-?[0-9.]+,\s*-?[0-9.]+", address.strip()):
        return False

    compact_address = normalise_text(address.replace("-", ""))
    street_markers = {
        "ALEEA",
        "BULEVARD",
        "BULEVARDUL",
        "CALEA",
        "DRUM",
        "DRUMUL",
        "FUNDATURA",
        "INTRAREA",
        "PIATA",
        "PRELUNGIREA",
        "SOSEA",
        "SOSEAUA",
        "SOS",
        "SPLAI",
        "SPLAIUL",
        "STR",
        "STRADA",
    }
    tokens = set(normalised_address.split()) | set(compact_address.split())
    return bool(tokens & street_markers) or bool(
        re.search(r"\b(BD|BDUL|BULEVARD|NR|NUMAR)\b", compact_address)
    )


def table_county_index(source_text: str) -> dict[str, str]:
    index: dict[str, str] = {}
    pattern = re.compile(
        r'<td class="(?P<class>[^"]+) hide"><a href="(?P<url>[^"]+)">(?P<name>.*?)</a>',
        re.S,
    )
    for match in pattern.finditer(source_text):
        code = county_code(clean_text(match.group("class")))
        if code:
            index[clean_text(match.group("url"))] = code
    return index


def parse_source_records(source_text: str) -> list[dict[str, Any]]:
    counties_by_url = table_county_index(source_text)
    pattern = re.compile(
        r"var lat_lng = \{lat: (?P<lat>[-0-9.]+), lng: (?P<lng>[-0-9.]+) \};"
        r".*?message = message \+ \"<h5>(?P<name>.*?)</h5>"
        r"<address>(?P<address>.*?)</address><a href='(?P<url>.*?)'>",
        re.S,
    )

    records = []
    for ordinal, match in enumerate(pattern.finditer(source_text), start=1):
        name = clean_text(match.group("name"))
        address = clean_text(match.group("address"))
        relative_url = clean_text(match.group("url"))
        detail_url = urllib.parse.urljoin(MS_UNITATI_SANITARE_URL, relative_url)
        latitude = float(match.group("lat"))
        longitude = float(match.group("lng"))
        records.append(
            {
                "sourceRecordId": f"ms-unitati-sanitare-{ordinal:03d}",
                "sourceOrdinal": ordinal,
                "name": name,
                "countyCode": (
                    counties_by_url.get(relative_url) or county_code_from_address(address)
                ),
                "address": address,
                "hasStreetAddress": has_street_address(address, name),
                "latitude": latitude,
                "longitude": longitude,
                "hasPublishedCoordinate": True,
                "detailUrl": detail_url,
            }
        )
    return records


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_document(source_text: str, retrieved_date: str) -> dict[str, Any]:
    records = parse_source_records(source_text)
    name_counts = Counter(normalise_text(record["name"]) for record in records)
    url_counts = Counter(record["detailUrl"] for record in records)

    return {
        "$schema": "../schema/health-address-source.schema.json",
        "id": SOURCE_ID,
        "title": "Ministerul Sanatatii unitati sanitare address extract",
        "publisher": "Ministerul Sanatatii",
        "sourceUrl": MS_UNITATI_SANITARE_URL,
        "retrievedDate": retrieved_date,
        "transform": {
            "script": "packages/health_access/scripts/import_ms_unitati_sanitare.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": {
            "sourceRecords": len(records),
            "sourceRecordsWithCounty": sum(1 for record in records if record["countyCode"]),
            "sourceRecordsWithStreetAddress": sum(
                1 for record in records if record["hasStreetAddress"]
            ),
            "sourceRecordsWithCoordinates": sum(
                1 for record in records if record["hasPublishedCoordinate"]
            ),
            "duplicateSourceNames": sum(1 for count in name_counts.values() if count > 1),
            "duplicateDetailUrls": sum(1 for count in url_counts.values() if count > 1),
        },
        "records": records,
        "limitations": [
            limitation(
                "raw-html-not-committed",
                "note",
                ["records"],
                (
                    "The official Ministry page HTML is fetched or supplied to this "
                    "importer, then reduced to the address fields required by the "
                    "provider-point builder."
                ),
            ),
            limitation(
                "map-coordinates-source-evidence",
                "material",
                ["latitude", "longitude", "hasPublishedCoordinate"],
                (
                    "The source page embeds marker coordinates. This extract retains "
                    "them as source evidence; the provider-point builder decides "
                    "which coordinates can become point evidence."
                ),
            ),
            limitation(
                "street-address-heuristic",
                "material",
                ["hasStreetAddress"],
                (
                    "Some official address strings are locality-only, URL-only or "
                    "coordinate-only values. They are retained but marked as not "
                    "street-address evidence."
                ),
            ),
            limitation(
                "source-license-not-published",
                "note",
                ["sourceUrl"],
                (
                    "The Ministry page is an official public webpage, but it does not "
                    "publish a reusable open-data license on the extracted page."
                ),
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=MS_UNITATI_SANITARE_URL)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    source_text = read_source_text(args.source)
    document = build_document(source_text, args.retrieved_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['sourceRecords']} source rows "
        f"({document['summary']['sourceRecordsWithStreetAddress']} street addresses; "
        f"{document['summary']['sourceRecordsWithCoordinates']} coordinates; "
        f"source sha256 {sha256_text(source_text)[:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
