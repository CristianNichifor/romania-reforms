from __future__ import annotations

import pytest

from pipeline.build_health_access import build_payload


def health_unit(
    siruta: str,
    providers: int,
    county_eligible: int = 2,
    county_blocked: int = 1,
) -> dict:
    return {
        "siruta": siruta,
        "hasLocalProvider": providers > 0,
        "localProviderCount": providers,
        "localClinicalBedProviders": 1 if providers else 0,
        "localClinicalBeds": 25.25 if providers else 0,
        "countyEligibleProviderCount": county_eligible,
        "countyBlockedProviderCount": county_blocked,
    }


def access_view(units: list[dict]) -> dict:
    return {
        "id": "health-service-access-uat-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "publisher": "Ministerul Sanatatii / ANMCS",
        "summary": {
            "eligibleProviders": 10,
            "blockedProviders": 4,
            "namedExclusions": 4,
            "excludedSectorRows": 6,
        },
        "units": units,
    }


def test_build_payload_aligns_shared_health_view_to_web_uat_order() -> None:
    payload = build_payload(
        access_view([health_unit("10", 0), health_unit("20", 3)]),
        {"siruta": ["20", "10"], "county": ["AB", "AB"]},
        "a" * 64,
    )

    assert payload["id"] == "administrativ-health-access-uat-2024-2026"
    assert payload["sourceViewId"] == "health-service-access-uat-2024-2026"
    assert payload["sourceViewSha256"] == "a" * 64
    assert payload["periodStart"] == "2024"
    assert payload["periodEnd"] == "2026"
    assert payload["siruta"] == ["20", "10"]
    assert payload["hasLocalProvider"] == [True, False]
    assert payload["localProviderCount"] == [3, 0]
    assert payload["localClinicalBedProviders"] == [1, 0]
    assert payload["localClinicalBeds"] == [25.25, 0.0]
    assert payload["countyEligibleProviderCount"] == [2, 2]
    assert payload["countyBlockedProviderCount"] == [1, 1]
    assert payload["sectorRowExcluded"] == [False, False]
    assert payload["summary"]["uatsWithHealthData"] == 2
    assert payload["summary"]["uatsWithLocalProvider"] == 1
    assert payload["summary"]["localProviderCount"] == 3


def test_build_payload_keeps_bucharest_sector_rows_unassigned() -> None:
    payload = build_payload(
        access_view([health_unit("179132", 87)]),
        {"siruta": ["179141", "179150"], "county": ["B", "B"]},
        "a" * 64,
    )

    assert payload["hasLocalProvider"] == [None, None]
    assert payload["localProviderCount"] == [None, None]
    assert payload["localClinicalBedProviders"] == [None, None]
    assert payload["localClinicalBeds"] == [None, None]
    assert payload["sectorRowExcluded"] == [True, True]
    assert payload["summary"]["sectorRowsExcluded"] == 2
    assert payload["summary"]["uatsWithHealthData"] == 0


def test_build_payload_refuses_missing_non_bucharest_uats() -> None:
    with pytest.raises(ValueError, match="missing UAT rows"):
        build_payload(
            access_view([health_unit("10", 1)]),
            {"siruta": ["10", "20"], "county": ["AB", "AB"]},
            "a" * 64,
        )


def test_build_payload_refuses_duplicate_health_view_rows() -> None:
    with pytest.raises(ValueError, match="duplicate SIRUTA"):
        build_payload(
            access_view([health_unit("10", 1), health_unit("010", 2)]),
            {"siruta": ["10"], "county": ["AB"]},
            "a" * 64,
        )
