"""Build a source-acquisition queue for remaining health provider points.

This is not point evidence. It converts the manual review report into a
prioritised list of providers that need provider-specific address or coordinate
sources before they can be promoted into the point layer.

Usage:
    uv run python packages/health_access/scripts/build_health_provider_point_source_acquisition.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_POINTS = PACKAGE_ROOT / "data/health-provider-points-2024-2026.json"
POINT_REVIEW = PACKAGE_ROOT / "data/health-provider-point-evidence-review-2024-2026.json"
ACQUISITION_ID: Final[str] = "health-provider-point-source-acquisition-2024-2026"
OUT = PACKAGE_ROOT / f"data/{ACQUISITION_ID}.json"
TRANSFORM_VERSION: Final[int] = 1

LOCALITY_CANDIDATE_STATUS: Final[str] = "has-unused-ministry-review-candidate"
NO_MINISTRY_CANDIDATE_STATUS: Final[str] = "no-ministry-review-candidate"

SOURCE_TYPES: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "provider-official-website",
        "label": "Provider official website or contact page",
        "acceptedEvidence": ["provider-published-street-address", "provider-published-coordinate"],
    },
    {
        "id": "dsp-or-local-authority-list",
        "label": "County DSP, county council or local authority provider page",
        "acceptedEvidence": ["official-authority-street-address", "official-authority-coordinate"],
    },
    {
        "id": "cnas-or-official-contracting-list",
        "label": "CNAS or other official contracting/register source",
        "acceptedEvidence": ["official-authority-street-address"],
    },
    {
        "id": "osm-named-feature-manual-review",
        "label": "OSM named hospital feature checked manually against provider identity",
        "acceptedEvidence": ["named-osm-feature-coordinate"],
    },
    {
        "id": "ministry-locality-candidate-provider-verification",
        "label": (
            "Existing Ministry locality-only candidate checked against a provider-specific source"
        ),
        "acceptedEvidence": ["verified-ministry-source-row-alias"],
    },
)

ACCEPTANCE_RULES: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "provider-specific-source-required",
        "text": (
            "A new acceptance must name the provider or its official operator and carry "
            "locality/county context; locality-name overlap alone is not enough."
        ),
    },
    {
        "id": "street-address-before-address-alias",
        "text": (
            "A source-record alias can fill address evidence only when the accepted source "
            "row or external provider-specific source contains street-address evidence."
        ),
    },
    {
        "id": "coordinate-only-stays-coordinate-only",
        "text": (
            "Published coordinates may be accepted without address evidence only through "
            "a reviewed coordinate-only method that preserves addressEvidence.method none."
        ),
    },
    {
        "id": "license-and-retrieval-recorded",
        "text": (
            "Every adopted external source must record URL, publisher, retrieval date, "
            "checksum where applicable and license/usage limitation."
        ),
    },
)

PRIORITY_RANK: Final[dict[str, int]] = {
    "p1-locality-candidate-needs-provider-evidence": 1,
    "p2-public-bed-provider-no-ministry-candidate": 2,
    "p3-public-provider-no-ministry-candidate": 3,
    "p4-private-or-unknown-provider-no-ministry-candidate": 4,
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def provider_points_review_ids(provider_points: dict[str, Any]) -> set[str]:
    return {
        provider["providerId"]
        for provider in provider_points["providers"]
        if provider["serviceAccessEligible"]
        and provider["pointAccessBlockedReason"] == "no-point-evidence"
    }


def acquisition_status(review_record: dict[str, Any]) -> str:
    if review_record["candidateStatus"] == LOCALITY_CANDIDATE_STATUS:
        return "needs-provider-specific-evidence"
    return "needs-new-source"


def acquisition_priority(review_record: dict[str, Any]) -> str:
    if review_record["candidateStatus"] == LOCALITY_CANDIDATE_STATUS:
        return "p1-locality-candidate-needs-provider-evidence"
    if review_record["ownerType"] == "public" and (review_record["bedCount"] or 0) > 0:
        return "p2-public-bed-provider-no-ministry-candidate"
    if review_record["ownerType"] == "public":
        return "p3-public-provider-no-ministry-candidate"
    return "p4-private-or-unknown-provider-no-ministry-candidate"


def source_search_order(review_record: dict[str, Any]) -> list[str]:
    order = [
        "provider-official-website",
        "dsp-or-local-authority-list",
    ]
    if review_record["candidateStatus"] == LOCALITY_CANDIDATE_STATUS:
        order.append("ministry-locality-candidate-provider-verification")
    order.extend(
        [
            "cnas-or-official-contracting-list",
            "osm-named-feature-manual-review",
        ]
    )
    return order


def acceptable_evidence(review_record: dict[str, Any]) -> list[str]:
    evidence = [
        "provider-published-street-address",
        "provider-published-coordinate",
        "official-authority-street-address",
        "official-authority-coordinate",
        "named-osm-feature-coordinate",
    ]
    if review_record["candidateStatus"] == LOCALITY_CANDIDATE_STATUS:
        evidence.append("verified-ministry-source-row-alias")
    return evidence


def next_action(review_record: dict[str, Any]) -> str:
    if review_record["candidateStatus"] == LOCALITY_CANDIDATE_STATUS:
        return "verify-locality-only-ministry-candidate-with-provider-source"
    return "find-provider-specific-address-or-coordinate-source"


def acquisition_record(review_record: dict[str, Any]) -> dict[str, Any]:
    candidates = review_record["candidates"]
    return {
        "providerId": review_record["providerId"],
        "name": review_record["name"],
        "countyCode": review_record["countyCode"],
        "countyName": review_record["countyName"],
        "siruta": review_record["siruta"],
        "localityName": review_record["localityName"],
        "locationConfidence": review_record["locationConfidence"],
        "ownerType": review_record["ownerType"],
        "bedCount": review_record["bedCount"],
        "specialties": review_record["specialties"],
        "candidateStatus": review_record["candidateStatus"],
        "reviewSignal": review_record["reviewSignal"],
        "candidateCount": review_record["candidateCount"],
        "ministryCandidateSourceRecordIds": [
            candidate["sourceRecordId"] for candidate in candidates
        ],
        "candidateReviewMethods": sorted({candidate["reviewMethod"] for candidate in candidates}),
        "acquisitionStatus": acquisition_status(review_record),
        "acquisitionPriority": acquisition_priority(review_record),
        "sourceSearchOrder": source_search_order(review_record),
        "acceptableEvidence": acceptable_evidence(review_record),
        "nextAction": next_action(review_record),
    }


def by_county_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_county[record["countyCode"]].append(record)

    summaries = []
    for county_code in sorted(records_by_county):
        rows = records_by_county[county_code]
        summaries.append(
            {
                "countyCode": county_code,
                "countyName": rows[0]["countyName"],
                "acquisitionProviders": len(rows),
                "localityOnlyCandidateProviders": sum(
                    1 for row in rows if row["candidateStatus"] == LOCALITY_CANDIDATE_STATUS
                ),
                "noMinistryCandidateProviders": sum(
                    1 for row in rows if row["candidateStatus"] == NO_MINISTRY_CANDIDATE_STATUS
                ),
                "publicBedNoCandidateProviders": sum(
                    1
                    for row in rows
                    if row["acquisitionPriority"] == "p2-public-bed-provider-no-ministry-candidate"
                ),
            }
        )
    return summaries


def validate_review_matches_provider_points(
    provider_points: dict[str, Any],
    point_review: dict[str, Any],
) -> None:
    expected_ids = provider_points_review_ids(provider_points)
    review_ids = {record["providerId"] for record in point_review["records"]}
    if review_ids != expected_ids:
        missing = sorted(expected_ids - review_ids)
        stale = sorted(review_ids - expected_ids)
        raise ValueError(
            "point acquisition review ids do not match provider-point no-evidence ids: "
            f"missing={missing[:10]} stale={stale[:10]}"
        )


def build_document(
    provider_points: dict[str, Any],
    point_review: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
) -> dict[str, Any]:
    validate_review_matches_provider_points(provider_points, point_review)

    records = [
        acquisition_record(record)
        for record in point_review["records"]
        if record["pointAccessBlockedReason"] == "no-point-evidence"
    ]
    records = sorted(
        records,
        key=lambda record: (
            PRIORITY_RANK[record["acquisitionPriority"]],
            record["countyCode"],
            record["providerId"],
        ),
    )
    if len(records) != point_review["summary"]["reviewProviders"]:
        raise ValueError("source acquisition rows do not cover every review provider")

    source_search_types = [
        source_type for record in records for source_type in record["sourceSearchOrder"]
    ]
    summary = {
        "providerPoints": provider_points["summary"]["providers"],
        "pointAccessEligibleProviders": provider_points["summary"]["pointAccessEligibleProviders"],
        "pointAccessBlockedProviders": provider_points["summary"]["pointAccessBlockedProviders"],
        "reviewProviders": point_review["summary"]["reviewProviders"],
        "acquisitionProviders": len(records),
        "localityOnlyCandidateProviders": sum(
            1 for record in records if record["candidateStatus"] == LOCALITY_CANDIDATE_STATUS
        ),
        "noMinistryCandidateProviders": sum(
            1 for record in records if record["candidateStatus"] == NO_MINISTRY_CANDIDATE_STATUS
        ),
        "publicBedNoCandidateProviders": sum(
            1
            for record in records
            if record["acquisitionPriority"] == "p2-public-bed-provider-no-ministry-candidate"
        ),
        "acquisitionStatus": count_by([record["acquisitionStatus"] for record in records]),
        "acquisitionPriority": count_by([record["acquisitionPriority"] for record in records]),
        "sourceSearchTypes": count_by(source_search_types),
        "ownerTypes": count_by([record["ownerType"] for record in records]),
        "byCounty": by_county_summary(records),
    }

    return {
        "$schema": "../schema/health-provider-point-source-acquisition.schema.json",
        "id": ACQUISITION_ID,
        "title": "Health provider point source acquisition queue",
        "publisher": "Cristian Nichifor",
        "scope": "provider-point-source-acquisition",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": f"{point_review['id']} + {provider_points['id']}",
            "locator": (
                "service-eligible provider-point rows still blocked for no-point-evidence, "
                "prioritised by remaining Ministry candidate signal, ownership and bed counts"
            ),
            "confidence": "derived",
            "note": (
                "This queue is source-acquisition work planning. It does not promote "
                "candidate rows into point evidence."
            ),
        },
        "registry": {
            "providerPoints": {
                "id": provider_points["id"],
                "periodStart": provider_points["periodStart"],
                "periodEnd": provider_points["periodEnd"],
            },
            "providerPointReview": {
                "id": point_review["id"],
                "periodStart": point_review["periodStart"],
                "periodEnd": point_review["periodEnd"],
            },
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": (
                "packages/health_access/scripts/build_health_provider_point_source_acquisition.py"
            ),
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "sourceTypes": list(SOURCE_TYPES),
        "acceptanceRules": list(ACCEPTANCE_RULES),
        "records": records,
        "limitations": [
            limitation(
                "source-acquisition-not-point-evidence",
                "material",
                ["records", "sourceSearchOrder"],
                (
                    "This queue names work to find evidence. It must not be consumed as "
                    "provider coordinates, address aliases or routing input."
                ),
            ),
            limitation(
                "locality-only-ministry-candidates-not-accepted",
                "material",
                ["records.ministryCandidateSourceRecordIds"],
                (
                    "Remaining Ministry candidates are low-signal locality overlaps. "
                    "They require provider-specific corroboration before any alias or "
                    "coordinate acceptance can be created."
                ),
            ),
            limitation(
                "external-source-license-must-be-recorded",
                "material",
                ["sourceTypes", "acceptanceRules"],
                (
                    "Any future adopted provider website, authority page, register or "
                    "OSM-derived record must carry URL, publisher, retrieval date and "
                    "license or usage limitation in the accepting source file."
                ),
            ),
        ],
    }


def build_from_files(
    provider_points_path: Path,
    point_review_path: Path,
    retrieved_date: str,
) -> dict[str, Any]:
    provider_points = json.loads(provider_points_path.read_text(encoding="utf-8"))
    point_review = json.loads(point_review_path.read_text(encoding="utf-8"))
    return build_document(
        provider_points,
        point_review,
        {
            "providerPointsSha256": sha256_file(provider_points_path),
            "providerPointReviewSha256": sha256_file(point_review_path),
        },
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-points", type=Path, default=PROVIDER_POINTS)
    parser.add_argument("--point-review", type=Path, default=POINT_REVIEW)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    document = build_from_files(args.provider_points, args.point_review, args.retrieved_date)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['acquisitionProviders']} "
        "source-acquisition providers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
