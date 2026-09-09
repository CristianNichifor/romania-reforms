"""Build a review report for remaining health providers without point evidence.

The report is deliberately not an alias source. It gives reviewers a compact,
auditable queue of service-eligible providers that are still blocked from
point-level access and names Ministry source rows that may deserve manual
review.

Usage:
    uv run python packages/health_access/scripts/build_health_provider_point_review.py
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
PROVIDER_POINTS = PACKAGE_ROOT / "data/health-provider-points-2024-2026.json"
HEALTH_MART = PACKAGE_ROOT / "data/health-access-mart-2024-2025.json"
ADDRESS_SOURCE = PACKAGE_ROOT / "sources/ms-unitati-sanitare-2026.json"
ADDRESS_ALIASES = PACKAGE_ROOT / "sources/ms-unitati-sanitare-address-aliases-2026.json"
REVIEW_ID: Final[str] = "health-provider-point-evidence-review-2024-2026"
OUT = PACKAGE_ROOT / f"data/{REVIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 1
MAX_CANDIDATES_PER_PROVIDER: Final[int] = 3
GENERIC_NAME_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "A",
        "AL",
        "ALE",
        "BD",
        "BUCURESTI",
        "BULEVARDUL",
        "CLINIC",
        "CLINICA",
        "CLINICE",
        "CLINICI",
        "COMUNA",
        "COMUNAL",
        "CU",
        "DE",
        "DIN",
        "DOCTOR",
        "DR",
        "INSTITUT",
        "INSTITUTIE",
        "INSTITUTUL",
        "JUDET",
        "JUDETEAN",
        "JUDETEANA",
        "JUDETEANUL",
        "JUDETUL",
        "LA",
        "LUI",
        "MEDICAL",
        "MEDICALE",
        "MUNICIPAL",
        "MUNICIPALUL",
        "MUNICIPIUL",
        "NATIONAL",
        "NATIONALA",
        "NR",
        "ORASENESC",
        "ORASENESCUL",
        "ORASUL",
        "PENTRU",
        "PROF",
        "SANITAR",
        "SANITARA",
        "SF",
        "SFA",
        "SFANTA",
        "SFANTUL",
        "SI",
        "SPITAL",
        "SPITALUL",
        "STR",
        "STRADA",
        "URGENTA",
    }
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def normalise_text(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def review_tokens(value: object) -> list[str]:
    words = normalise_text(value).split()
    expanded: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word == "C" and index + 1 < len(words) and words[index + 1] == "F":
            expanded.extend(["CAI", "FERATE"])
            index += 2
            continue
        if word == "TG":
            expanded.append("TARGU")
        else:
            expanded.append(word)
        index += 1
    return [
        word
        for word in expanded
        if len(word) > 1 and word not in GENERIC_NAME_TOKENS and not word.isdigit()
    ]


def mart_by_provider_id(health_mart: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index = {provider["providerId"]: provider for provider in health_mart["records"]}
    if len(index) != len(health_mart["records"]):
        counts = Counter(provider["providerId"] for provider in health_mart["records"])
        duplicates = sorted(provider_id for provider_id, count in counts.items() if count > 1)
        raise ValueError("duplicate health mart provider ids: " + ", ".join(duplicates))
    return index


def source_rows_by_exact_key(
    address_source: dict[str, Any],
) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    rows: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in address_source["records"]:
        rows[(normalise_text(row["name"]), row.get("countyCode"))].append(row)
    return rows


def matched_source_record_ids(provider_points: dict[str, Any]) -> set[str]:
    return {
        provider["addressSourceRecordId"]
        for provider in provider_points["providers"]
        if provider.get("addressSourceRecordId")
    }


def unused_street_rows_by_county(
    address_source: dict[str, Any],
    used_source_record_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in address_source["records"]:
        county_code = row.get("countyCode")
        if not county_code or not row.get("hasStreetAddress"):
            continue
        if row["sourceRecordId"] in used_source_record_ids:
            continue
        rows[county_code].append(row)
    return rows


def provider_review_candidates(
    provider: dict[str, Any],
    same_county_unused_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    provider_name_tokens = set(review_tokens(provider["name"]))
    provider_all_tokens = provider_name_tokens | set(review_tokens(provider.get("localityName")))
    locality_tokens = set(review_tokens(provider.get("localityName")))
    candidates = []

    for source_row in same_county_unused_rows:
        source_name_tokens = set(review_tokens(source_row["name"]))
        source_all_tokens = source_name_tokens | set(review_tokens(source_row["address"]))
        shared_name_tokens = provider_name_tokens & source_name_tokens
        shared_tokens = provider_all_tokens & source_all_tokens
        non_locality_tokens = shared_name_tokens - locality_tokens
        provider_coverage = (
            round(len(shared_tokens) / len(provider_all_tokens), 3) if provider_all_tokens else 0
        )
        source_coverage = (
            round(len(shared_tokens) / len(source_all_tokens), 3) if source_all_tokens else 0
        )
        token_score = (
            round(len(shared_tokens) / len(provider_all_tokens | source_all_tokens), 3)
            if provider_all_tokens or source_all_tokens
            else 0
        )

        if len(non_locality_tokens) >= 2:
            review_method = "specific-name-token-overlap-same-county-unused-source"
        elif (
            len(provider_name_tokens) <= 3
            and len(shared_name_tokens) >= 2
            and shared_name_tokens == provider_name_tokens
        ):
            review_method = "short-name-token-coverage-same-county-unused-source"
        elif len(shared_name_tokens) >= 2:
            review_method = "locality-name-token-overlap-same-county-unused-source"
        else:
            continue

        if review_method.startswith("specific") and provider_coverage >= 0.6:
            review_signal = "high"
        elif review_method.startswith("short"):
            review_signal = "high"
        elif review_method.startswith("locality"):
            review_signal = "low"
        else:
            review_signal = "medium"

        candidates.append(
            {
                "sourceRecordId": source_row["sourceRecordId"],
                "name": source_row["name"],
                "countyCode": source_row["countyCode"],
                "address": source_row["address"],
                "hasStreetAddress": bool(source_row["hasStreetAddress"]),
                "hasPublishedCoordinate": bool(source_row["hasPublishedCoordinate"]),
                "latitude": source_row["latitude"],
                "longitude": source_row["longitude"],
                "detailUrl": source_row["detailUrl"],
                "reviewMethod": review_method,
                "reviewSignal": review_signal,
                "sharedTokens": sorted(shared_tokens),
                "providerTokenCoverage": provider_coverage,
                "sourceTokenCoverage": source_coverage,
                "tokenScore": token_score,
                "reason": (
                    "Same-county unused Ministry source row with overlapping normalised "
                    "name tokens; manual review is required before any alias can be added."
                ),
            }
        )

    signal_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        candidates,
        key=lambda candidate: (
            signal_rank[candidate["reviewSignal"]],
            -candidate["providerTokenCoverage"],
            -candidate["tokenScore"],
            candidate["sourceRecordId"],
        ),
    )[:MAX_CANDIDATES_PER_PROVIDER]


def exact_no_street_candidates(
    provider: dict[str, Any],
    exact_source_rows: dict[tuple[str, str | None], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = exact_source_rows.get((normalise_text(provider["name"]), provider["countyCode"]), [])
    return [
        {
            "sourceRecordId": source_row["sourceRecordId"],
            "name": source_row["name"],
            "countyCode": source_row["countyCode"],
            "address": source_row["address"],
            "hasStreetAddress": bool(source_row["hasStreetAddress"]),
            "hasPublishedCoordinate": bool(source_row["hasPublishedCoordinate"]),
            "latitude": source_row["latitude"],
            "longitude": source_row["longitude"],
            "detailUrl": source_row["detailUrl"],
            "reviewMethod": "exact-normalised-name-county-without-street-address",
            "reviewSignal": "high",
            "sharedTokens": sorted(
                set(review_tokens(provider["name"])) & set(review_tokens(source_row["name"]))
            ),
            "providerTokenCoverage": 1,
            "sourceTokenCoverage": 1,
            "tokenScore": 1,
            "reason": (
                "Exact same-county Ministry source row exists, but the current "
                "provider-point contract rejects it because the source row has no "
                "street-address evidence."
            ),
        }
        for source_row in rows
        if not source_row.get("hasStreetAddress")
    ]


def review_signal(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "none"
    if any(candidate["reviewSignal"] == "high" for candidate in candidates):
        return "high"
    if any(candidate["reviewSignal"] == "medium" for candidate in candidates):
        return "medium"
    return "low"


def review_row(
    provider: dict[str, Any],
    health_provider: dict[str, Any],
    exact_source_rows: dict[tuple[str, str | None], list[dict[str, Any]]],
    same_county_unused_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    exact_candidates = exact_no_street_candidates(provider, exact_source_rows)
    token_candidates = provider_review_candidates(provider, same_county_unused_rows)
    candidates = exact_candidates + token_candidates
    if exact_candidates:
        candidate_status = "exact-source-row-lacks-street-address"
    elif token_candidates:
        candidate_status = "has-unused-ministry-review-candidate"
    else:
        candidate_status = "no-ministry-review-candidate"

    return {
        "providerId": provider["providerId"],
        "name": provider["name"],
        "countyCode": provider["countyCode"],
        "countyName": provider["countyName"],
        "siruta": provider["siruta"],
        "localityName": provider["localityName"],
        "locationConfidence": provider["locationConfidence"],
        "ownerType": health_provider["ownerType"],
        "bedCount": health_provider["bedCount"],
        "specialties": health_provider["specialties"],
        "pointAccessBlockedReason": provider["pointAccessBlockedReason"],
        "candidateStatus": candidate_status,
        "reviewSignal": review_signal(candidates),
        "candidateCount": len(candidates),
        "candidates": candidates,
    }


def by_county_summary(review_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in review_rows:
        rows_by_county[row["countyCode"]].append(row)

    summaries = []
    for county_code in sorted(rows_by_county):
        rows = rows_by_county[county_code]
        summaries.append(
            {
                "countyCode": county_code,
                "countyName": rows[0]["countyName"],
                "reviewProviders": len(rows),
                "providersWithAnyCandidate": sum(1 for row in rows if row["candidateCount"]),
                "exactSourceRowsWithoutStreetAddress": sum(
                    1
                    for row in rows
                    if row["candidateStatus"] == "exact-source-row-lacks-street-address"
                ),
                "unusedMinistryCandidateProviders": sum(
                    1
                    for row in rows
                    if row["candidateStatus"] == "has-unused-ministry-review-candidate"
                ),
                "providersWithoutMinistryCandidate": sum(
                    1 for row in rows if row["candidateStatus"] == "no-ministry-review-candidate"
                ),
            }
        )
    return summaries


def build_document(
    provider_points: dict[str, Any],
    health_mart: dict[str, Any],
    address_source: dict[str, Any],
    address_aliases: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
) -> dict[str, Any]:
    health_index = mart_by_provider_id(health_mart)
    exact_source_rows = source_rows_by_exact_key(address_source)
    used_source_record_ids = matched_source_record_ids(provider_points)
    unused_source_rows = unused_street_rows_by_county(address_source, used_source_record_ids)
    review_providers = [
        provider
        for provider in provider_points["providers"]
        if provider["serviceAccessEligible"]
        and provider["pointAccessBlockedReason"] == "no-point-evidence"
    ]
    unknown = sorted(
        provider["providerId"]
        for provider in review_providers
        if provider["providerId"] not in health_index
    )
    if unknown:
        raise ValueError("provider points missing from health mart: " + ", ".join(unknown[:10]))

    review_rows = [
        review_row(
            provider,
            health_index[provider["providerId"]],
            exact_source_rows,
            unused_source_rows.get(provider["countyCode"], []),
        )
        for provider in review_providers
    ]
    candidate_statuses = count_by([row["candidateStatus"] for row in review_rows])
    review_signals = count_by([row["reviewSignal"] for row in review_rows])
    candidates = [candidate for row in review_rows for candidate in row["candidates"]]

    summary = {
        "providerPoints": provider_points["summary"]["providers"],
        "pointAccessEligibleProviders": provider_points["summary"]["pointAccessEligibleProviders"],
        "pointAccessBlockedProviders": provider_points["summary"]["pointAccessBlockedProviders"],
        "reviewProviders": len(review_rows),
        "countiesWithReviewProviders": len({row["countyCode"] for row in review_rows}),
        "providersWithAnyCandidate": sum(1 for row in review_rows if row["candidateCount"]),
        "candidateRows": len(candidates),
        "candidateStatus": candidate_statuses,
        "reviewSignal": review_signals,
        "exactSourceRowsWithoutStreetAddress": candidate_statuses.get(
            "exact-source-row-lacks-street-address",
            0,
        ),
        "unusedMinistryCandidateProviders": candidate_statuses.get(
            "has-unused-ministry-review-candidate",
            0,
        ),
        "providersWithoutMinistryCandidate": candidate_statuses.get(
            "no-ministry-review-candidate",
            0,
        ),
        "ministrySourceRecords": address_source["summary"]["sourceRecords"],
        "ministrySourceRecordsAlreadyMatched": len(used_source_record_ids),
        "unusedMinistryStreetSourceRecords": sum(
            1
            for row in address_source["records"]
            if row.get("hasStreetAddress") and row["sourceRecordId"] not in used_source_record_ids
        ),
        "existingAddressAliases": len(address_aliases["aliases"]),
        "byCounty": by_county_summary(review_rows),
    }

    return {
        "$schema": "../schema/health-provider-point-evidence-review.schema.json",
        "id": REVIEW_ID,
        "title": "Remaining health provider point evidence review",
        "publisher": "Cristian Nichifor",
        "scope": "provider-point-evidence-review",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": (
                f"{provider_points['id']} + {health_mart['id']} + "
                f"{address_source['id']} + {address_aliases['id']}"
            ),
            "locator": (
                "service-eligible provider-point rows still blocked for no-point-evidence, "
                "compared with unmatched Ministry unitati sanitare source rows by same-county "
                "exact name and token-overlap review signals"
            ),
            "confidence": "derived",
            "note": (
                "This is a manual-review queue. Candidate rows are not point evidence and "
                "must not be used as aliases until source-record-pinned review accepts them."
            ),
        },
        "registry": {
            "providerPoints": {
                "id": provider_points["id"],
                "periodStart": provider_points["periodStart"],
                "periodEnd": provider_points["periodEnd"],
            },
            "healthMart": {
                "id": health_mart["id"],
                "periodStart": health_mart["periodStart"],
                "periodEnd": health_mart["periodEnd"],
            },
            "addressSource": {
                "id": address_source["id"],
                "publisher": address_source["publisher"],
                "sourceUrl": address_source["sourceUrl"],
                "retrievedDate": address_source["retrievedDate"],
            },
            "addressAliases": {
                "id": address_aliases["id"],
                "reviewedDate": address_aliases["reviewedDate"],
                "aliases": len(address_aliases["aliases"]),
            },
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": "packages/health_access/scripts/build_health_provider_point_review.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "records": review_rows,
        "limitations": [
            limitation(
                "review-report-not-point-evidence",
                "material",
                ["records.candidates", "candidateStatus"],
                (
                    "Candidate rows identify review leads only. They do not update "
                    "health-provider-points-2024-2026 and must not be consumed as "
                    "accepted provider coordinates."
                ),
            ),
            limitation(
                "token-overlap-is-not-fuzzy-acceptance",
                "material",
                ["records.candidates.reviewMethod", "records.candidates.sharedTokens"],
                (
                    "Token-overlap candidates are same-county, unmatched Ministry rows "
                    "kept for manual review. Generic fuzzy matching remains disabled."
                ),
            ),
            limitation(
                "exact-source-row-may-still-lack-street-address",
                "material",
                ["records.candidates.hasStreetAddress"],
                (
                    "Exact name/county source rows without street-address evidence are "
                    "reported separately because the provider-point builder intentionally "
                    "does not accept them as point evidence."
                ),
            ),
        ],
    }


def build_from_files(
    provider_points_path: Path,
    health_mart_path: Path,
    address_source_path: Path,
    address_aliases_path: Path,
    retrieved_date: str,
) -> dict[str, Any]:
    provider_points = json.loads(provider_points_path.read_text(encoding="utf-8"))
    health_mart = json.loads(health_mart_path.read_text(encoding="utf-8"))
    address_source = json.loads(address_source_path.read_text(encoding="utf-8"))
    address_aliases = json.loads(address_aliases_path.read_text(encoding="utf-8"))
    return build_document(
        provider_points,
        health_mart,
        address_source,
        address_aliases,
        {
            "providerPointsSha256": sha256_file(provider_points_path),
            "healthAccessMartSha256": sha256_file(health_mart_path),
            "msUnitatiSanitareSha256": sha256_file(address_source_path),
            "msUnitatiSanitareAliasesSha256": sha256_file(address_aliases_path),
        },
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-points", type=Path, default=PROVIDER_POINTS)
    parser.add_argument("--health-mart", type=Path, default=HEALTH_MART)
    parser.add_argument("--address-source", type=Path, default=ADDRESS_SOURCE)
    parser.add_argument("--address-aliases", type=Path, default=ADDRESS_ALIASES)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    document = build_from_files(
        args.provider_points,
        args.health_mart,
        args.address_source,
        args.address_aliases,
        args.retrieved_date,
    )
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['reviewProviders']} providers, "
        f"{document['summary']['providersWithAnyCandidate']} candidate providers and "
        f"{document['summary']['providersWithoutMinistryCandidate']} without Ministry candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
