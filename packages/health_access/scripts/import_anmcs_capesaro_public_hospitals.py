"""Extract ANMCS CAPeSaRo public hospital dashboard records.

The source endpoint returns the full dashboard JSON. This importer keeps only
the stable fields needed for provider-point source acquisition and leaves the
raw response out of git.

Usage:
    uv run python packages/health_access/scripts/import_anmcs_capesaro_public_hospitals.py \
      --source /tmp/capesaro-health.json --retrieved-date 2026-09-09
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID: Final[str] = "anmcs-capesaro-public-hospitals-2026"
OUT = PACKAGE_ROOT / f"sources/{SOURCE_ID}.json"
TRANSFORM_VERSION: Final[int] = 1
CAPESARO_PAGE_URL: Final[str] = "https://capesaro.gov.ro/hospitals_public.php"
CAPESARO_FEED_URL: Final[str] = "https://capesaro.gov.ro/hospitals_public.php?ajax=1"
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"

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


def clean_text(value: object) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def read_source_json(location: str | Path) -> str:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read().decode("utf-8")
    return Path(text).read_text(encoding="utf-8")


def county_code(value: object) -> str | None:
    return COUNTY_CODE_BY_NAME.get(normalise_text(value).replace("-", " "))


def parse_float(value: object) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    return float(text)


def has_street_address(address: str | None, name: str) -> bool:
    if not address:
        return False
    normalised_address = normalise_text(address)
    if not normalised_address or normalised_address == normalise_text(name):
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
        "SPLAI",
        "SPLAIUL",
        "SOSEA",
        "SOSEAUA",
        "SOS",
        "STR",
        "STRADA",
    }
    tokens = set(normalised_address.split()) | set(compact_address.split())
    return bool(tokens & street_markers) or bool(
        re.search(r"\b(BD|BDUL|BULEVARD|NR|NUMAR)\b", compact_address)
    )


def source_record_id(source_native_id: str, source_code: str | None) -> str:
    if source_code:
        return f"capesaro-2026-{source_code}"
    return f"capesaro-2026-id-{source_native_id}"


def parse_source_records(source_json: str) -> list[dict[str, Any]]:
    payload = json.loads(source_json)
    if not isinstance(payload, list):
        raise ValueError("CAPeSaRo source must be a JSON array")

    records = []
    for ordinal, item in enumerate(payload, start=1):
        general = item.get("general") if isinstance(item, dict) else None
        if not isinstance(general, dict):
            raise ValueError(f"CAPeSaRo row has no general object: {ordinal}")

        source_native_id = clean_text(general.get("id"))
        if not source_native_id:
            raise ValueError(f"CAPeSaRo row has no id: {ordinal}")
        source_code = clean_text(general.get("cod_anmcs"))
        name = clean_text(general.get("name"))
        if not name:
            raise ValueError(f"CAPeSaRo row has no name: {ordinal}")
        latitude = parse_float(general.get("lat"))
        longitude = parse_float(general.get("lng"))
        address = clean_text(general.get("address_sediu_social"))

        records.append(
            {
                "sourceRecordId": source_record_id(source_native_id, source_code),
                "sourceOrdinal": ordinal,
                "sourceNativeId": source_native_id,
                "sourceCode": source_code,
                "name": name,
                "countyCode": county_code(general.get("judet")),
                "sourceCountyName": clean_text(general.get("judet")),
                "sourceCity": clean_text(general.get("city")),
                "address": address,
                "hasStreetAddress": has_street_address(address, name),
                "latitude": latitude,
                "longitude": longitude,
                "hasPublishedCoordinate": latitude is not None and longitude is not None,
                "website": clean_text(general.get("website")),
                "active": clean_text(general.get("active")) == "1",
            }
        )
    return records


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_document(source_json: str, retrieved_date: str) -> dict[str, Any]:
    records = parse_source_records(source_json)
    code_counts = Counter(record["sourceCode"] for record in records if record["sourceCode"])
    name_counts = Counter(normalise_text(record["name"]) for record in records)

    return {
        "$schema": "../schema/anmcs-capesaro-public-hospitals.schema.json",
        "id": SOURCE_ID,
        "title": "ANMCS CAPeSaRo public hospital dashboard extract",
        "publisher": "Autoritatea Nationala de Management al Calitatii in Sanatate",
        "sourcePageUrl": CAPESARO_PAGE_URL,
        "sourceUrl": CAPESARO_FEED_URL,
        "retrievedDate": retrieved_date,
        "license": "not-specified-public-government-dashboard",
        "usageLimitation": (
            "Public CAPeSaRo government dashboard feed; no explicit reuse license "
            "was found on the fetched source or listing page, so records retain "
            "URL, retrieval date and source identifiers."
        ),
        "transform": {
            "script": "packages/health_access/scripts/import_anmcs_capesaro_public_hospitals.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": {
            "sourceRecords": len(records),
            "activeSourceRecords": sum(1 for record in records if record["active"]),
            "sourceRecordsWithCounty": sum(1 for record in records if record["countyCode"]),
            "sourceRecordsWithStreetAddress": sum(
                1 for record in records if record["hasStreetAddress"]
            ),
            "sourceRecordsWithCoordinates": sum(
                1 for record in records if record["hasPublishedCoordinate"]
            ),
            "duplicateSourceCodes": sum(1 for count in code_counts.values() if count > 1),
            "duplicateSourceNames": sum(1 for count in name_counts.values() if count > 1),
        },
        "records": records,
        "limitations": [
            limitation(
                "raw-dashboard-response-not-committed",
                "note",
                ["records"],
                (
                    "The official dashboard JSON is fetched or supplied to this importer, "
                    "then reduced to stable fields needed by provider-point candidate reports."
                ),
            ),
            limitation(
                "source-license-not-specified",
                "material",
                ["license", "usageLimitation"],
                (
                    "CAPeSaRo is a public government dashboard, but no explicit reusable "
                    "open-data license is recorded in this source file."
                ),
            ),
            limitation(
                "source-candidates-not-point-evidence",
                "material",
                ["records"],
                (
                    "This extract is source material for candidate review. Downstream "
                    "provider-point builders may accept only explicit audited "
                    "provider/sourceCode evidence rows."
                ),
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=CAPESARO_FEED_URL)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    source_json = read_source_json(args.source)
    document = build_document(source_json, args.retrieved_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['sourceRecords']} source rows "
        f"({document['summary']['activeSourceRecords']} active; "
        f"source sha256 {sha256_text(source_json)[:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
