"""Build a CAPeSaRo candidate report for remaining health provider points.

This is not point evidence. It identifies same-county CAPeSaRo dashboard rows
that may be reviewed into supplemental evidence later.

Usage:
    uv run python packages/health_access/scripts/build_health_provider_point_capesaro_candidates.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ACQUISITION = PACKAGE_ROOT / "data/health-provider-point-source-acquisition-2024-2026.json"
CAPESARO_SOURCE = PACKAGE_ROOT / "sources/anmcs-capesaro-public-hospitals-2026.json"
CANDIDATE_REPORT_ID: Final[str] = "health-provider-point-capesaro-candidates-2024-2026"
OUT = PACKAGE_ROOT / f"data/{CANDIDATE_REPORT_ID}.json"
TRANSFORM_VERSION: Final[int] = 1
MINIMUM_CANDIDATE_SCORE: Final[int] = 50
MAX_CANDIDATES_PER_PROVIDER: Final[int] = 5

PRIORITY_RANK: Final[dict[str, int]] = {
    "p3-public-provider-no-ministry-candidate": 3,
    "p4-private-or-unknown-provider-no-ministry-candidate": 4,
}

STOP_WORDS: Final[set[str]] = {
    "A",
    "AL",
    "ALE",
    "BUCURESTI",
    "CENTRU",
    "CENTRUL",
    "CLINIC",
    "CLINICA",
    "CLINICUL",
    "CU",
    "DE",
    "DIN",
    "DOCTOR",
    "DR",
    "IN",
    "INTEGRAT",
    "INTEGRATA",
    "JUDETEAN",
    "JUDETEANA",
    "MEDICAL",
    "MEDICALA",
    "MUNICIPAL",
    "ORASENESC",
    "PATURI",
    "PENTRU",
    "PROF",
    "ROMANIA",
    "S",
    "SA",
    "SANATORIUL",
    "SANITARA",
    "SI",
    "SOCIETATEA",
    "SPITAL",
    "SPITALUL",
    "SPECIALITATE",
    "SRL",
    "UNITATE",
    "URGENTA",
}

MATCHING_POLICY: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "same-county-only",
        "text": (
            "Candidates are generated only when the acquisition row and CAPeSaRo source "
            "row have the same county code."
        ),
    },
    {
        "id": "active-address-coordinate-source-rows-only",
        "text": (
            "Candidate rows require active CAPeSaRo records with a source code, street "
            "address evidence and published coordinates."
        ),
    },
    {
        "id": "candidate-not-evidence",
        "text": (
            "Exact, contained and token-overlap matches are review candidates only; "
            "provider points may use CAPeSaRo only through explicit audited supplemental "
            "evidence rows."
        ),
    },
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def normalise_text(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_tokens(value: object) -> set[str]:
    return {
        token
        for token in normalise_text(value).split()
        if len(token) > 2 and token not in STOP_WORDS
    }


def match_score(provider_name: str, source_name: str) -> tuple[int, str | None, list[str]]:
    provider_normalised = normalise_text(provider_name)
    source_normalised = normalise_text(source_name)
    provider_tokens = match_tokens(provider_name)
    source_tokens = match_tokens(source_name)
    overlapping_tokens = sorted(provider_tokens & source_tokens)

    if provider_normalised == source_normalised:
        return 100, "exact-normalised-name-county", overlapping_tokens
    if provider_normalised in source_normalised or source_normalised in provider_normalised:
        return 92, "contained-normalised-name-county", overlapping_tokens

    overlap_ratio = len(overlapping_tokens) / max(len(provider_tokens), 1)
    if len(overlapping_tokens) >= 4 and overlap_ratio >= 0.6:
        return int(60 + overlap_ratio * 30), "token-overlap-same-county", overlapping_tokens
    if len(overlapping_tokens) >= 3 and overlap_ratio >= 0.5:
        return int(45 + overlap_ratio * 30), "weak-token-overlap-same-county", overlapping_tokens
    return int(overlap_ratio * 40), None, overlapping_tokens


def review_signal(method: str, score: int) -> str:
    if method == "exact-normalised-name-county":
        return "high"
    if score >= 90:
        return "medium"
    return "low"


def candidate_source_rows(capesaro_source: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows_by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in capesaro_source["records"]:
        if not record["active"]:
            continue
        if not record.get("sourceCode"):
            continue
        if not record.get("countyCode"):
            continue
        if not record["hasStreetAddress"] or not record["hasPublishedCoordinate"]:
            continue
        rows_by_county[record["countyCode"]].append(record)
    return rows_by_county


def capesaro_candidate(
    provider: dict[str, Any], source_record: dict[str, Any]
) -> dict[str, Any] | None:
    score, method, overlapping_tokens = match_score(provider["name"], source_record["name"])
    if method is None or score < MINIMUM_CANDIDATE_SCORE:
        return None
    signal = review_signal(method, score)
    return {
        "sourceRecordId": source_record["sourceRecordId"],
        "sourceNativeId": source_record["sourceNativeId"],
        "sourceCode": source_record["sourceCode"],
        "sourceName": source_record["name"],
        "sourceCountyName": source_record["sourceCountyName"],
        "sourceCity": source_record["sourceCity"],
        "address": source_record["address"],
        "latitude": source_record["latitude"],
        "longitude": source_record["longitude"],
        "website": source_record["website"],
        "matchMethod": method,
        "matchScore": score,
        "overlappingTokens": overlapping_tokens,
        "reviewSignal": signal,
    }


def provider_record(
    acquisition_record: dict[str, Any],
    rows_by_county: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    candidates = [
        candidate
        for source_record in rows_by_county.get(acquisition_record["countyCode"], [])
        if (candidate := capesaro_candidate(acquisition_record, source_record)) is not None
    ]
    candidates = sorted(
        candidates,
        key=lambda candidate: (-candidate["matchScore"], candidate["sourceRecordId"]),
    )[:MAX_CANDIDATES_PER_PROVIDER]
    candidate_signal = candidates[0]["reviewSignal"] if candidates else "none"

    return {
        "providerId": acquisition_record["providerId"],
        "name": acquisition_record["name"],
        "countyCode": acquisition_record["countyCode"],
        "countyName": acquisition_record["countyName"],
        "siruta": acquisition_record["siruta"],
        "localityName": acquisition_record["localityName"],
        "ownerType": acquisition_record["ownerType"],
        "acquisitionPriority": acquisition_record["acquisitionPriority"],
        "candidateStatus": ("has-capesaro-candidate" if candidates else "no-capesaro-candidate"),
        "candidateSignal": candidate_signal,
        "candidateCount": len(candidates),
        "nextAction": (
            "review-capesaro-source-row-for-supplemental-evidence"
            if candidates
            else "continue-other-source-acquisition"
        ),
        "candidates": candidates,
    }


def by_county_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        rows_by_county[record["countyCode"]].append(record)

    summaries = []
    for county_code in sorted(rows_by_county):
        rows = rows_by_county[county_code]
        summaries.append(
            {
                "countyCode": county_code,
                "countyName": rows[0]["countyName"],
                "providers": len(rows),
                "providersWithCandidates": sum(
                    1 for row in rows if row["candidateStatus"] == "has-capesaro-candidate"
                ),
                "candidateRows": sum(row["candidateCount"] for row in rows),
            }
        )
    return summaries


def validate_inputs(source_acquisition: dict[str, Any], capesaro_source: dict[str, Any]) -> None:
    if source_acquisition["id"] != "health-provider-point-source-acquisition-2024-2026":
        raise ValueError(f"unexpected source acquisition id: {source_acquisition['id']}")
    if capesaro_source["id"] != "anmcs-capesaro-public-hospitals-2026":
        raise ValueError(f"unexpected CAPeSaRo source id: {capesaro_source['id']}")

    provider_ids = [record["providerId"] for record in source_acquisition["records"]]
    duplicates = sorted(
        provider_id for provider_id, count in Counter(provider_ids).items() if count > 1
    )
    if duplicates:
        raise ValueError("source acquisition has duplicate provider ids: " + ", ".join(duplicates))

    source_record_ids = [record["sourceRecordId"] for record in capesaro_source["records"]]
    duplicate_sources = sorted(
        source_id for source_id, count in Counter(source_record_ids).items() if count > 1
    )
    if duplicate_sources:
        raise ValueError(
            "CAPeSaRo source has duplicate record ids: " + ", ".join(duplicate_sources)
        )


def build_document(
    source_acquisition: dict[str, Any],
    capesaro_source: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
) -> dict[str, Any]:
    validate_inputs(source_acquisition, capesaro_source)
    rows_by_county = candidate_source_rows(capesaro_source)

    records = [provider_record(record, rows_by_county) for record in source_acquisition["records"]]
    records = sorted(
        records,
        key=lambda record: (
            PRIORITY_RANK[record["acquisitionPriority"]],
            record["candidateSignal"] == "none",
            record["countyCode"],
            record["providerId"],
        ),
    )

    if len(records) != source_acquisition["summary"]["acquisitionProviders"]:
        raise ValueError("CAPeSaRo candidate report does not cover every acquisition row")

    providers_with_candidates = [
        record for record in records if record["candidateStatus"] == "has-capesaro-candidate"
    ]
    public_records = [record for record in records if record["ownerType"] == "public"]
    public_records_with_candidates = [
        record for record in public_records if record["candidateStatus"] == "has-capesaro-candidate"
    ]
    candidate_rows = [candidate for record in records for candidate in record["candidates"]]

    return {
        "$schema": "../schema/health-provider-point-capesaro-candidates.schema.json",
        "id": CANDIDATE_REPORT_ID,
        "title": "Health provider point CAPeSaRo candidate report",
        "publisher": "Cristian Nichifor",
        "scope": "provider-point-capesaro-candidate-review",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": f"{source_acquisition['id']} + {capesaro_source['id']}",
            "locator": (
                "remaining provider-point source-acquisition rows matched to active "
                "same-county CAPeSaRo dashboard rows by exact, contained or token-overlap "
                "provider names"
            ),
            "confidence": "derived",
            "note": (
                "This report is a candidate review aid. It does not promote CAPeSaRo "
                "rows into address aliases, coordinates or point-routing input."
            ),
        },
        "registry": {
            "sourceAcquisition": {
                "id": source_acquisition["id"],
                "periodStart": source_acquisition["periodStart"],
                "periodEnd": source_acquisition["periodEnd"],
            },
            "capesaroSource": {
                "id": capesaro_source["id"],
                "publisher": capesaro_source["publisher"],
                "sourceUrl": capesaro_source["sourceUrl"],
                "retrievedDate": capesaro_source["retrievedDate"],
                "records": capesaro_source["summary"]["sourceRecords"],
            },
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": (
                "packages/health_access/scripts/build_health_provider_point_capesaro_candidates.py"
            ),
            "version": TRANSFORM_VERSION,
        },
        "matchingPolicy": list(MATCHING_POLICY),
        "summary": {
            "sourceAcquisitionProviders": source_acquisition["summary"]["acquisitionProviders"],
            "capesaroSourceRecords": capesaro_source["summary"]["sourceRecords"],
            "activeCapesaroSourceRecords": capesaro_source["summary"]["activeSourceRecords"],
            "providersWithCandidates": len(providers_with_candidates),
            "providersWithoutCandidates": len(records) - len(providers_with_candidates),
            "candidateRows": len(candidate_rows),
            "publicProviders": len(public_records),
            "publicProvidersWithCandidates": len(public_records_with_candidates),
            "publicProvidersWithoutCandidates": (
                len(public_records) - len(public_records_with_candidates)
            ),
            "candidateStatus": count_by([record["candidateStatus"] for record in records]),
            "candidateSignals": count_by([record["candidateSignal"] for record in records]),
            "candidateMatchMethods": count_by(
                [candidate["matchMethod"] for candidate in candidate_rows]
            ),
            "candidateOwnerTypes": count_by(
                [record["ownerType"] for record in providers_with_candidates]
            ),
            "candidatePriorities": count_by(
                [record["acquisitionPriority"] for record in providers_with_candidates]
            ),
            "byCounty": by_county_summary(records),
        },
        "records": records,
        "limitations": [
            limitation(
                "candidate-report-not-point-evidence",
                "material",
                ["records", "records.candidates"],
                (
                    "Candidate rows must not be consumed as provider-point evidence. "
                    "Promotion still requires explicit supplemental evidence rows reviewed "
                    "by providerId and CAPeSaRo sourceCode."
                ),
            ),
            limitation(
                "token-overlap-is-review-only",
                "material",
                ["records.candidates.matchMethod", "records.candidates.matchScore"],
                (
                    "Contained-name and token-overlap candidates may still represent "
                    "branches, operators or similarly named providers. They require manual "
                    "review before any acceptance file is changed."
                ),
            ),
            limitation(
                "inactive-or-incomplete-capesaro-rows-excluded",
                "note",
                ["records.candidates"],
                (
                    "Candidates are generated only from active CAPeSaRo rows with source "
                    "codes, street-address evidence and published coordinates."
                ),
            ),
        ],
    }


def build_from_files(
    source_acquisition_path: Path,
    capesaro_source_path: Path,
    retrieved_date: str,
) -> dict[str, Any]:
    source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
    capesaro_source = json.loads(capesaro_source_path.read_text(encoding="utf-8"))
    return build_document(
        source_acquisition,
        capesaro_source,
        {
            "sourceAcquisitionSha256": sha256_file(source_acquisition_path),
            "capesaroSourceSha256": sha256_file(capesaro_source_path),
        },
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-acquisition", type=Path, default=SOURCE_ACQUISITION)
    parser.add_argument("--capesaro-source", type=Path, default=CAPESARO_SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    document = build_from_files(
        args.source_acquisition,
        args.capesaro_source,
        args.retrieved_date,
    )
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['providersWithCandidates']} "
        f"providers with CAPeSaRo candidates and {document['summary']['candidateRows']} "
        "candidate rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
