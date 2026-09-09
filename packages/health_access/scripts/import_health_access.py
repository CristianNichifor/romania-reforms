"""Build a shared national health-access mart from Ministry of Health and ANMCS workbooks.

The mart uses ANMCS as the provider/accreditation roster, attaches provider-level
clinical bed counts when Ministry source rows can be matched confidently, and
names the rows that are excluded from provider-level access calculations.

Usage:
    uv run python packages/health_access/scripts/import_health_access.py \
        --hospital-beds-source /tmp/paturi-in-spitale-2024.xls \
        --clinical-beds-source /tmp/paturi-clinice-specialitati-2024.xls \
        --anmcs-source /tmp/anmcs-acreditare-unitati-sanitare-dec2025.xlsx
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import unicodedata
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Final

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
UAT_REGISTRY = REPO_ROOT / "packages/uat_registry/data/uat-registry-2026.json"
NATIONAL_MART_ID: Final[str] = "health-access-mart-2024-2025"
SAMPLE_MART_ID: Final[str] = "health-access-mart-sample-2024-2025"
OUT = PACKAGE_ROOT / f"data/{NATIONAL_MART_ID}.json"
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
TRANSFORM_VERSION: Final[int] = 2

HOSPITAL_BEDS_URL: Final[str] = (
    "https://data.gov.ro/dataset/37aa4af3-4b99-4277-8193-236b8ccbaea1/"
    "resource/b4930a0f-b8e8-447f-ab02-778951b4a7ca/download/"
    "paturi-in-spitale-ministerul-sanatatii-academia-romana-elias-si-"
    "administratia-locala-la-31.xii.2.xls"
)
CLINICAL_BEDS_URL: Final[str] = (
    "https://data.gov.ro/dataset/c5619084-3ff8-4b9c-aa90-36e12a0fcf70/"
    "resource/6f28d169-e692-4079-8edd-caf46643673f/download/"
    "paturi-clinice-in-spitale-pe-specialitati-la-31.xii.2024.xls"
)
ANMCS_URL: Final[str] = (
    "https://data.gov.ro/dataset/9d218668-6a1d-4f3b-b889-cfb73d062f90/"
    "resource/5debc642-bdae-413e-93ff-9baf2d1e0c1d/download/"
    "anmcs-acreditare-unitati-sanitare-dec2025.xlsx"
)

COUNTY_CODE_BY_NAME: Final[dict[str, str]] = {
    "ALBA": "AB",
    "ARAD": "AR",
    "ARGES": "AG",
    "BACAU": "BC",
    "BIHOR": "BH",
    "BISTRITA N": "BN",
    "BISTRITA NASAUD": "BN",
    "BOTOSANI": "BT",
    "BRAILA": "BR",
    "BRASOV": "BV",
    "BUZAU": "BZ",
    "BUCURESTI": "B",
    "M BUCURESTI": "B",
    "CALARASI": "CL",
    "CARAS S": "CS",
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
COUNTY_NAME_BY_CODE: Final[dict[str, str]] = {
    "AB": "Alba",
    "AG": "Arges",
    "AR": "Arad",
    "B": "Bucuresti",
    "BC": "Bacau",
    "BH": "Bihor",
    "BN": "Bistrita-Nasaud",
    "BR": "Braila",
    "BT": "Botosani",
    "BV": "Brasov",
    "BZ": "Buzau",
    "CJ": "Cluj",
    "CL": "Calarasi",
    "CS": "Caras-Severin",
    "CT": "Constanta",
    "CV": "Covasna",
    "DB": "Dambovita",
    "DJ": "Dolj",
    "GJ": "Gorj",
    "GL": "Galati",
    "GR": "Giurgiu",
    "HD": "Hunedoara",
    "HR": "Harghita",
    "IF": "Ilfov",
    "IL": "Ialomita",
    "IS": "Iasi",
    "MH": "Mehedinti",
    "MM": "Maramures",
    "MS": "Mures",
    "NT": "Neamt",
    "OT": "Olt",
    "PH": "Prahova",
    "SB": "Sibiu",
    "SJ": "Salaj",
    "SM": "Satu Mare",
    "SV": "Suceava",
    "TL": "Tulcea",
    "TM": "Timis",
    "TR": "Teleorman",
    "VL": "Valcea",
    "VN": "Vrancea",
    "VS": "Vaslui",
}
BEDS_COLUMN: Final[int] = 2
SPECIALTY_COLUMNS: Final[dict[int, str]] = {
    3: "internalMedicine",
    4: "endocrinology",
    5: "occupationalDiseases",
    6: "cardiology",
    7: "rheumatology",
    8: "diabetesNutritionMetabolic",
    9: "gastroenterology",
    10: "geriatricsGerontology",
    11: "hematology",
    12: "neurology",
    13: "psychiatryTotal",
    14: "psychiatry",
    15: "acutePsychiatry",
    16: "chronicPsychiatry",
    17: "neurosurgery",
    18: "neuropsychomotorRecovery",
    19: "ent",
    22: "ophthalmology",
    23: "infectiousDiseases",
    24: "generalSurgery",
    25: "maxillofacialSurgery",
    26: "pediatricSurgery",
    27: "plasticSurgery",
    28: "cardiovascularSurgery",
    29: "thoracicSurgery",
    30: "medicalOncology",
    31: "urology",
    32: "orthopedicsTraumatology",
    33: "pediatrics",
    34: "pediatricRecovery",
    35: "chronicPediatrics",
    36: "dermatologyVenereology",
    37: "obstetricsGynecology",
    38: "neonatology",
    39: "prematureNeonatology",
    40: "tuberculosis",
    41: "pneumology",
    42: "pneumologyTbc",
    43: "thoracicSurgeryTbc",
    44: "extrapulmonaryTbc",
    45: "rehabilitationPhysicalMedicineBalneology",
    46: "generalMedicine",
    47: "chronicCare",
    48: "intensiveCare",
    49: "otherDepartments",
    50: "covidBeds",
}
TOKEN_REPLACEMENTS: Final[dict[str, str]] = {
    "SPIT.": "SPITAL ",
    "SPIT ": "SPITAL ",
    "INST.": "INSTITUT ",
    "INST ": "INSTITUT ",
    "INSTITUTL": "INSTITUTUL",
    "CLINC": "CLINIC",
    "CLIN.": "CLINIC",
    "SF.": "SFANTUL ",
    "SF ": "SFANTUL ",
    "DR.": "DOCTOR ",
    "DR ": "DOCTOR ",
    "PROF.": "PROFESOR ",
    "PROF ": "PROFESOR ",
    "NAT.": "NATIONAL ",
    "NAT ": "NATIONAL ",
    "PTR": "PENTRU",
    "REG.": "REGIONAL ",
    "NR.": "NUMAR ",
}
MATCH_STOP_WORDS: Final[set[str]] = {
    "A",
    "AL",
    "ALE",
    "BUCURESTI",
    "CENTRUL",
    "CENTRU",
    "CLINIC",
    "CLINICA",
    "DE",
    "DIN",
    "DOCTOR",
    "DR",
    "IN",
    "INSTITUT",
    "INSTITUTUL",
    "JUDETEAN",
    "JUDETEANA",
    "MUNICIPAL",
    "MUNICIPIUL",
    "NATIONAL",
    "PENTRU",
    "PROF",
    "PROFESOR",
    "REGIONAL",
    "SFANTUL",
    "SI",
    "SPITAL",
    "SPITALUL",
    "UNIVERSITAR",
    "URGENTA",
    "URGENTE",
}
WEAK_SINGLE_TOKEN_MATCHES: Final[set[str]] = {
    "BOLI",
    "CHIRURGIE",
    "COPII",
    "IOAN",
    "MEDICAL",
    "RECUPERARE",
}
CLINICAL_LOCATION_HINTS: Final[dict[str, str]] = {
    "ARAD": "AR",
    "BAILE FELIX": "BH",
    "BRAILA": "BR",
    "BRASOV": "BV",
    "BUCURESTI": "B",
    "BUZIAS": "TM",
    "CLUJ": "CJ",
    "CONSTANTA": "CT",
    "CRAIOVA": "DJ",
    "EFORIE NORD": "CT",
    "EFORIE": "CT",
    "GALATI": "GL",
    "IASI": "IS",
    "LEAMNA": "DJ",
    "MOINESTI": "BC",
    "MURES": "MS",
    "ORADEA": "BH",
    "SIBIU": "SB",
    "SUCEAVA": "SV",
    "TARGU MURES": "MS",
    "TG MURES": "MS",
    "TIMISOARA": "TM",
}
LOCATION_ONLY_MATCH_TOKENS: Final[set[str]] = {
    token for hint in CLINICAL_LOCATION_HINTS for token in hint.split()
}
LOCALITY_ALIASES: Final[dict[tuple[str, str], str]] = {
    ("CJ", "CLUJ"): "CLUJ-NAPOCA",
    ("MS", "TG MURES"): "TARGU MURES",
    ("MS", "TIRGU MURES"): "TARGU MURES",
}
PRIVATE_MARKERS: Final[tuple[str, ...]] = (
    " S R L",
    " SRL",
    " S A",
    " SA",
    "SOCIETATEA",
    "ASOCIATIA",
    "ASOCIATIE",
    "FUNDATIA",
    "CLINICA",
    "MED LIFE",
    "MEDICOVER",
    "REGINA MARIA",
    "SANADOR",
)
PUBLIC_MARKERS: Final[tuple[str, ...]] = (
    "SPITALUL",
    "SPITAL ",
    "INSTITUTUL",
    "INSTITUT ",
    "PENITENCIAR",
    "CENTRUL NATIONAL",
    "CENTRUL CLINIC",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_source_bytes(location: str | Path) -> bytes:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    return Path(text).read_bytes()


def normalise_text(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def county_code(value: object) -> str | None:
    return COUNTY_CODE_BY_NAME.get(normalise_text(value).replace("-", " "))


def parse_number(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, int | float):
        return round(float(value), 2)
    text = str(value).strip()
    if not text or text == "-":
        return 0.0
    text = text.replace(" ", "").replace(",", ".")
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def parse_percent(value: object) -> float | None:
    number = parse_number(str(value).replace("%", "") if isinstance(value, str) else value)
    if number is None:
        return None
    if 0 <= number <= 1:
        number *= 100
    return round(number, 2)


def excel_frame(data: bytes, sheet_name: int | str = 0) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, header=None, dtype=object)


def clinical_tokens(name: str) -> list[str]:
    text = normalise_text(name)
    for before, after in TOKEN_REPLACEMENTS.items():
        text = text.replace(before, after)
    text = normalise_text(text)
    return [token for token in text.split() if len(token) > 1 and token not in MATCH_STOP_WORDS]


def match_score(left: str, right: str) -> float:
    left_tokens = set(clinical_tokens(left))
    right_tokens = set(clinical_tokens(right))
    common = left_tokens & right_tokens
    token_score = 0.0
    if len(common) >= 2:
        token_score = len(common) / max(1, min(len(left_tokens), len(right_tokens)))
    elif (
        len(common) == 1
        and min(len(left_tokens), len(right_tokens)) == 1
        and next(iter(common)) not in WEAK_SINGLE_TOKEN_MATCHES | LOCATION_ONLY_MATCH_TOKENS
    ):
        token_score = 1.0
    return token_score


def owner_type(name: str) -> str:
    normalised = f" {normalise_text(name)} "
    if any(marker in normalised for marker in PRIVATE_MARKERS):
        return "private"
    if any(marker in normalised for marker in PUBLIC_MARKERS):
        return "public"
    return "unknown"


def is_numeric_index(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and not math.isnan(value)


def parse_county_beds(data: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    frame = excel_frame(data)
    for index, row in frame.iterrows():
        code = county_code(row.iloc[1] if len(row) > 1 else None)
        beds = parse_number(row.iloc[BEDS_COLUMN] if len(row) > BEDS_COLUMN else None)
        if code and beds is not None:
            rows.append(
                {
                    "countyCode": code,
                    "countyName": COUNTY_NAME_BY_CODE.get(code, clean_text(row.iloc[1]) or code),
                    "totalBeds": beds,
                    "sourceRow": int(index) + 1,
                }
            )
    return rows


def parse_clinical_beds(data: bytes) -> list[dict[str, Any]]:
    frame = excel_frame(data)
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for index, row in frame.iterrows():
        first = row.iloc[0] if len(row) else None
        name = clean_text(row.iloc[1] if len(row) > 1 else None)
        beds = parse_number(row.iloc[BEDS_COLUMN] if len(row) > BEDS_COLUMN else None)
        if is_numeric_index(first) and name and name not in {"A", "UNITATE"}:
            values = [row.iloc[col] if col < len(row) else None for col in range(0, 51)]
            current = {
                "clinicalRow": int(first),
                "sheetRow": int(index) + 1,
                "name": name,
                "bedCount": beds,
                "values": values,
            }
            rows.append(current)
            continue

        if (
            current is not None
            and name
            and name != "A"
            and "continuare" not in normalise_text(name).lower()
            and beds is not None
            and not is_numeric_index(first)
        ):
            current["name"] = f"{current['name']} {name}"
            for col in range(2, min(len(row), 51)):
                value = row.iloc[col]
                if not (value is None or (isinstance(value, float) and math.isnan(value))):
                    current["values"][col] = value
            current["bedCount"] = parse_number(current["values"][BEDS_COLUMN])

    parsed: list[dict[str, Any]] = []
    for row in rows:
        if row["bedCount"] is None:
            continue
        specialty_beds = {
            key: number
            for col, key in SPECIALTY_COLUMNS.items()
            if (number := parse_number(row["values"][col])) is not None and number > 0
        }
        parsed.append(
            {
                "clinicalRow": row["clinicalRow"],
                "sheetRow": row["sheetRow"],
                "name": row["name"],
                "bedCount": row["bedCount"],
                "specialtyBeds": specialty_beds,
                "specialties": sorted(specialty_beds),
            }
        )
    return parsed


def parse_anmcs(data: bytes, selected_counties: set[str] | None) -> list[dict[str, Any]]:
    frame = excel_frame(data, "Toate")
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        if not is_numeric_index(row.iloc[0] if len(row) else None):
            continue
        name = clean_text(row.iloc[1] if len(row) > 1 else None)
        code = county_code(row.iloc[2] if len(row) > 2 else None)
        if (
            not name
            or code is None
            or (selected_counties is not None and code not in selected_counties)
        ):
            continue
        ordinal = int(row.iloc[0])
        rows.append(
            {
                "providerId": f"anmcs-2025-{ordinal:03d}",
                "anmcsOrdinal": ordinal,
                "anmcsSheetRow": int(index) + 1,
                "name": name,
                "countyCode": code,
                "countyName": COUNTY_NAME_BY_CODE.get(code, clean_text(row.iloc[2]) or code),
                "accreditationDecision": clean_text(row.iloc[3] if len(row) > 3 else None),
                "accreditationOrder": clean_text(row.iloc[4] if len(row) > 4 else None),
                "accreditationCategory": clean_text(row.iloc[5] if len(row) > 5 else None),
                "accreditationScore": parse_percent(row.iloc[6] if len(row) > 6 else None),
                "accreditationPeriod": clean_text(row.iloc[10] if len(row) > 10 else None),
                "ownerType": owner_type(name),
            }
        )
    return rows


def clinical_county_hint(name: str) -> str | None:
    normalised = normalise_text(name)
    for token, code in sorted(
        CLINICAL_LOCATION_HINTS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.search(rf"(^| ){re.escape(token)}( |$)", normalised):
            return code
    return None


def match_clinical_rows(
    providers: list[dict[str, Any]],
    clinical_rows: list[dict[str, Any]],
    threshold: float = 0.72,
) -> dict[str, dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    used: set[int] = set()

    for provider in providers:
        best_index = None
        best_score = 0.0
        for index, clinical in enumerate(clinical_rows):
            if index in used:
                continue
            county_hint = clinical_county_hint(clinical["name"])
            if county_hint is not None and county_hint != provider["countyCode"]:
                continue
            score = match_score(provider["name"], clinical["name"])
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is not None and best_score >= threshold:
            used.add(best_index)
            match = dict(clinical_rows[best_index])
            match["matchScore"] = round(best_score, 4)
            matches[provider["providerId"]] = match

    return matches


def registry_index(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_county: dict[str, list[dict[str, Any]]] = {}
    for unit in registry["units"]:
        by_county.setdefault(unit["countyCode"], []).append(unit)
    for units in by_county.values():
        units.sort(key=lambda unit: len(normalise_text(unit["shortName"])), reverse=True)
    return by_county


def locate_provider(
    provider: dict[str, Any],
    units_by_county: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    county_code_value = provider["countyCode"]
    if county_code_value == "B":
        units = units_by_county.get("B", [])
        municipality = next((unit for unit in units if unit["level"] == "municipality"), None)
        return {
            "siruta": municipality["siruta"] if municipality else None,
            "localityName": municipality["name"] if municipality else None,
            "locationConfidence": "municipality-from-county",
        }

    name = normalise_text(provider["name"])
    for unit in units_by_county.get(county_code_value, []):
        if unit["level"] == "county":
            continue
        short = normalise_text(unit["shortName"])
        if short and re.search(rf"(^| ){re.escape(short)}( |$)", name):
            return {
                "siruta": unit["siruta"],
                "localityName": unit["name"],
                "locationConfidence": "name-derived-locality",
            }

    for (county_code, alias), canonical in LOCALITY_ALIASES.items():
        if county_code_value != county_code or not re.search(
            rf"(^| ){re.escape(alias)}( |$)", name
        ):
            continue
        unit = next(
            (
                unit
                for unit in units_by_county.get(county_code, [])
                if normalise_text(unit["shortName"]) == canonical
            ),
            None,
        )
        if unit:
            return {
                "siruta": unit["siruta"],
                "localityName": unit["name"],
                "locationConfidence": "name-derived-locality",
            }

    return {"siruta": None, "localityName": None, "locationConfidence": "county-only"}


def selected_clinical_row(clinical: dict[str, Any], selected_counties: set[str]) -> bool:
    hint = clinical_county_hint(clinical["name"])
    if hint is not None:
        return hint in selected_counties
    return selected_counties == set(COUNTY_NAME_BY_CODE)


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def build_document(
    providers: list[dict[str, Any]],
    clinical_rows: list[dict[str, Any]],
    county_beds: list[dict[str, Any]],
    registry: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
    locators: dict[str, str],
    selected_counties: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if selected_counties is None:
        selected_counties = tuple(row["countyCode"] for row in county_beds)
        scope = "national"
    else:
        scope = "sample"

    selected = set(selected_counties)
    providers = [provider for provider in providers if provider["countyCode"] in selected]
    county_totals = [row for row in county_beds if row["countyCode"] in selected]
    matches = match_clinical_rows(providers, clinical_rows)
    units_by_county = registry_index(registry)
    matched_clinical_rows = {match["clinicalRow"] for match in matches.values()}

    records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for provider in providers:
        match = matches.get(provider["providerId"])
        location = locate_provider(provider, units_by_county)
        records.append(
            {
                "providerId": provider["providerId"],
                "name": provider["name"],
                "countyCode": provider["countyCode"],
                "countyName": provider["countyName"],
                "siruta": location["siruta"],
                "localityName": location["localityName"],
                "locationConfidence": location["locationConfidence"],
                "ownerType": provider["ownerType"],
                "bedCount": match["bedCount"] if match else None,
                "specialties": match["specialties"] if match else [],
                "specialtyBeds": match["specialtyBeds"] if match else {},
                "accreditationCategory": provider["accreditationCategory"],
                "accreditationScore": provider["accreditationScore"],
                "accreditationDecision": provider["accreditationDecision"],
                "accreditationOrder": provider["accreditationOrder"],
                "accreditationPeriod": provider["accreditationPeriod"],
                "sourceRows": {
                    "anmcsOrdinal": provider["anmcsOrdinal"],
                    "anmcsSheetRow": provider["anmcsSheetRow"],
                    "clinicalBedsRow": match["clinicalRow"] if match else None,
                    "clinicalBedsSheetRow": match["sheetRow"] if match else None,
                },
            }
        )
        if match is None:
            exclusions.append(
                {
                    "kind": "anmcs-provider-without-clinical-bed-row",
                    "source": "anmcs",
                    "name": provider["name"],
                    "countyCode": provider["countyCode"],
                    "reason": (
                        "No confident provider-level match in the 2024 clinical-beds workbook."
                    ),
                }
            )
        if location["siruta"] is None:
            exclusions.append(
                {
                    "kind": "provider-without-uat-location",
                    "source": "anmcs",
                    "name": provider["name"],
                    "countyCode": provider["countyCode"],
                    "reason": "The source rows carry county names but no address or coordinates.",
                }
            )

    for clinical in clinical_rows:
        if clinical["clinicalRow"] in matched_clinical_rows or not selected_clinical_row(
            clinical, selected
        ):
            continue
        hint = clinical_county_hint(clinical["name"])
        exclusions.append(
            {
                "kind": "clinical-bed-row-without-selected-anmcs-match",
                "source": "clinical-beds",
                "name": clinical["name"],
                "countyCode": hint,
                "reason": "Provider name was not matched to an ANMCS row in the selected scope.",
            }
        )

    by_county = []
    for code in selected_counties:
        county_records = [record for record in records if record["countyCode"] == code]
        county_name = next(
            (row["countyName"] for row in county_totals if row["countyCode"] == code),
            COUNTY_NAME_BY_CODE.get(code, code),
        )
        by_county.append(
            {
                "countyCode": code,
                "countyName": county_name,
                "anmcsProviders": len(county_records),
                "providersWithClinicalBeds": sum(
                    1 for record in county_records if record["bedCount"] is not None
                ),
                "providersWithSiruta": sum(1 for record in county_records if record["siruta"]),
                "countyTotalBeds": next(
                    (row["totalBeds"] for row in county_totals if row["countyCode"] == code),
                    None,
                ),
                "matchedClinicalBeds": round(
                    sum(record["bedCount"] or 0 for record in county_records), 2
                ),
            }
        )

    location_counts = Counter(record["locationConfidence"] for record in records)
    summary = {
        "scopeCounties": list(selected_counties),
        "records": len(records),
        "anmcsProviders": len(providers),
        "clinicalBedRows": len(clinical_rows),
        "matchedClinicalBedRows": len(matched_clinical_rows),
        "providersWithClinicalBeds": sum(1 for record in records if record["bedCount"] is not None),
        "providersWithoutClinicalBeds": sum(1 for record in records if record["bedCount"] is None),
        "providersWithSiruta": sum(1 for record in records if record["siruta"] is not None),
        "providerLevelClinicalBeds": round(sum(record["bedCount"] or 0 for record in records), 2),
        "countyTotalBeds": round(sum(row["totalBeds"] for row in county_totals), 2),
        "namedExclusions": len(exclusions),
        "locationConfidence": dict(sorted(location_counts.items())),
        "byCounty": by_county,
    }
    is_national = scope == "national"

    return {
        "$schema": "../schema/health-access-mart.schema.json",
        "id": NATIONAL_MART_ID if is_national else SAMPLE_MART_ID,
        "title": (
            "Health provider access mart, national"
            if is_national
            else "Health provider access mart sample"
        ),
        "publisher": "Ministerul Sanatatii / ANMCS",
        "scope": scope,
        "periodStart": "2024",
        "periodEnd": "2025",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": "data-gov-ro-health-workbooks",
            "locator": (
                f"hospital beds: {locators['hospitalBeds']}; "
                f"clinical beds: {locators['clinicalBeds']}; "
                f"ANMCS: {locators['anmcs']}"
            ),
            "confidence": "derived",
            "note": (
                "ANMCS supplies the provider roster and accreditation. The Ministry "
                "clinical-beds workbook supplies provider-level bed counts only where names "
                "match confidently; the broader hospital-beds workbook supplies county totals."
            ),
        },
        "registry": {"id": registry["id"], "period": registry["period"]},
        "sourceHashes": source_hashes,
        "transform": {
            "script": "packages/health_access/scripts/import_health_access.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "countyTotals": county_totals,
        "records": records,
        "exclusions": exclusions,
        "limitations": [
            limitation(
                "clinical-beds-provider-scope-is-partial",
                "material",
                ["bedCount", "specialties"],
                (
                    "Provider-level beds come from the clinical-beds workbook, which is not the "
                    "complete ANMCS provider roster. Providers without a confident match keep "
                    "bedCount null and are named in exclusions."
                ),
            ),
            limitation(
                "location-derived-from-provider-name",
                "material",
                ["siruta", "localityName", "locationConfidence"],
                (
                    "The source workbooks do not publish address or coordinates. UAT placement "
                    "is derived from locality text in provider names; unmatched rows remain "
                    "county-only."
                ),
            ),
            limitation(
                "bucharest-sector-not-identifiable",
                "material",
                ["siruta", "locationConfidence"],
                (
                    "Bucharest providers are assigned to the municipality-level SIRUTA because "
                    "the workbooks do not identify sectors."
                ),
            ),
            limitation(
                "owner-type-name-derived",
                "note",
                ["ownerType"],
                "Owner type is derived from legal-form words in the provider name.",
            ),
        ],
    }


def build_from_sources(
    hospital_beds_source: str,
    clinical_beds_source: str,
    anmcs_source: str,
    registry_path: Path,
    retrieved_date: str,
    selected_counties: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    hospital_beds = read_source_bytes(hospital_beds_source)
    clinical_beds = read_source_bytes(clinical_beds_source)
    anmcs = read_source_bytes(anmcs_source)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    providers = parse_anmcs(anmcs, set(selected_counties) if selected_counties else None)
    clinical_rows = parse_clinical_beds(clinical_beds)
    county_beds = parse_county_beds(hospital_beds)
    return build_document(
        providers,
        clinical_rows,
        county_beds,
        registry,
        source_hashes={
            "hospitalBedsWorkbookSha256": sha256_bytes(hospital_beds),
            "clinicalBedsWorkbookSha256": sha256_bytes(clinical_beds),
            "anmcsWorkbookSha256": sha256_bytes(anmcs),
            "uatRegistrySha256": sha256_file(registry_path),
        },
        retrieved_date=retrieved_date,
        locators={
            "hospitalBeds": hospital_beds_source,
            "clinicalBeds": clinical_beds_source,
            "anmcs": anmcs_source,
        },
        selected_counties=selected_counties,
    )


def parse_scope_counties(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    counties = tuple(
        dict.fromkeys(part.strip().upper() for part in value.split(",") if part.strip())
    )
    unknown = sorted(set(counties) - set(COUNTY_NAME_BY_CODE))
    if unknown:
        raise ValueError(f"Unknown county code(s): {', '.join(unknown)}")
    return counties


def write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hospital-beds-source", default=HOSPITAL_BEDS_URL)
    parser.add_argument("--clinical-beds-source", default=CLINICAL_BEDS_URL)
    parser.add_argument("--anmcs-source", default=ANMCS_URL)
    parser.add_argument("--registry", type=Path, default=UAT_REGISTRY)
    parser.add_argument("--scope-counties", help="Comma-separated county codes; omit for national.")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)
    selected_counties = parse_scope_counties(args.scope_counties)

    document = build_from_sources(
        args.hospital_beds_source,
        args.clinical_beds_source,
        args.anmcs_source,
        args.registry,
        args.retrieved_date,
        selected_counties=selected_counties,
    )
    out = args.out or (PACKAGE_ROOT / f"data/{SAMPLE_MART_ID}.json" if selected_counties else OUT)
    write_json(out, document)
    print(
        f"{document['summary']['records']} providers -> "
        f"{display_path(out)} "
        f"({document['summary']['providersWithClinicalBeds']} with clinical beds)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
