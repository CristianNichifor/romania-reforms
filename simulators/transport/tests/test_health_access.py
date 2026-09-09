"""Tests for attaching shared health access to transport rows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.health_access import (
    HEALTH_ACCESS_LIMITATION_ID,
    HEALTH_POINT_ACCESS_LIMITATION_ID,
    HEALTH_POINT_ACCESS_VIEW_ID,
    HEALTH_POINT_DISTANCE_METHOD,
    enrich_access_document,
)

ROOT = Path(__file__).resolve().parents[1]
HEALTH_ACCESS = (
    ROOT.parent.parent / "packages/health_access/data/health-service-access-uat-2024-2026.json"
)
HEALTH_POINT_ACCESS = (
    ROOT.parent.parent / "packages/health_access/data/health-point-access-2024-2026.json"
)


def health_unit(siruta: str, providers: int, beds: float = 0.0) -> dict:
    return {
        "siruta": siruta,
        "hasLocalProvider": providers > 0,
        "localProviderCount": providers,
        "localClinicalBedProviders": 1 if beds else 0,
        "localClinicalBeds": beds,
    }


def health_view(units: list[dict]) -> dict:
    return {
        "id": "health-service-access-uat-2024-2026",
        "summary": {
            "eligibleProviders": 10,
            "blockedProviders": 4,
            "namedExclusions": 4,
        },
        "units": units,
    }


def health_point(provider_id: str, latitude: float, longitude: float, beds: float = 0.0) -> dict:
    return {
        "providerId": provider_id,
        "name": f"Provider {provider_id}",
        "countyCode": "AB",
        "latitude": latitude,
        "longitude": longitude,
        "bedCount": beds,
    }


def point_view(points: list[dict]) -> dict:
    return {
        "id": HEALTH_POINT_ACCESS_VIEW_ID,
        "summary": {
            "pointAccessProviders": len(points),
            "pointAccessBlockedProviders": 4,
            "namedExclusions": 4,
        },
        "points": points,
    }


def access_row(siruta: str, county: str = "AB") -> dict:
    return {
        "siruta": siruta,
        "name": f"UAT {siruta}",
        "county": county,
        "population": 1,
        "feederMin": 1.0,
        "trunkMin": 1.0,
        "uncoordinatedMin": 32.0,
        "pulsedMin": 7.0,
        "railUncoordinatedMin": None,
        "railPulsedMin": None,
        "bestUncoordinatedMin": 32.0,
        "bestPulsedMin": 7.0,
        "mode": "bus",
    }


def access_doc(rows: list[dict]) -> dict:
    return {
        "provenance": {
            "source": "test",
            "locator": "test",
            "confidence": "derived",
            "note": "test",
        },
        "summary": {"uats": len(rows), "people": len(rows)},
        "uats": rows,
        "limitations": [{"id": "existing", "text": "existing"}],
    }


def test_enriches_transport_rows_from_the_shared_view() -> None:
    document = enrich_access_document(
        access_doc([access_row("10"), access_row("20")]),
        health_view([health_unit("10", 0), health_unit("20", 2, beds=25.5)]),
    )

    rows = {row["siruta"]: row for row in document["uats"]}
    assert rows["10"]["hasLocalHealthProvider"] is False
    assert rows["10"]["localHealthProviderCount"] == 0
    assert rows["20"]["hasLocalHealthProvider"] is True
    assert rows["20"]["localHealthProviderCount"] == 2
    assert rows["20"]["localHealthClinicalBedProviders"] == 1
    assert rows["20"]["localHealthClinicalBeds"] == 25.5
    assert document["summary"]["healthAccessView"] == "health-service-access-uat-2024-2026"
    assert document["summary"]["healthAccessRowsWithData"] == 2
    assert document["summary"]["healthAccessUatsWithLocalProvider"] == 1
    assert document["summary"]["healthAccessLocalProviders"] == 2
    assert document["summary"]["healthAccessLocalClinicalBeds"] == 25.5
    assert HEALTH_ACCESS_LIMITATION_ID in {
        limitation["id"] for limitation in document["limitations"]
    }


def test_enriches_transport_rows_with_nearest_health_point_distance() -> None:
    document = enrich_access_document(
        access_doc([access_row("10"), access_row("20")]),
        health_view([health_unit("10", 0), health_unit("20", 1)]),
        point_view(
            [
                health_point("provider-near-10", 44.0, 26.0),
                health_point("provider-near-20", 47.0, 23.0, beds=12.5),
            ]
        ),
        {
            "10": {"latitude": 44.0, "longitude": 26.0},
            "20": {"latitude": 47.0, "longitude": 23.0},
        },
    )

    rows = {row["siruta"]: row for row in document["uats"]}
    assert rows["10"]["nearestHealthPointProviderId"] == "provider-near-10"
    assert rows["10"]["nearestHealthPointDistanceMetres"] == 0
    assert rows["20"]["nearestHealthPointProviderId"] == "provider-near-20"
    assert rows["20"]["nearestHealthPointDistanceMetres"] == 0
    assert document["summary"]["healthPointAccessView"] == HEALTH_POINT_ACCESS_VIEW_ID
    assert document["summary"]["healthPointAccessProviders"] == 2
    assert document["summary"]["healthPointAccessBlockedProviders"] == 4
    assert document["summary"]["healthPointAccessRowsWithDistance"] == 2
    assert document["summary"]["healthPointAccessDistanceMethod"] == HEALTH_POINT_DISTANCE_METHOD
    assert HEALTH_POINT_ACCESS_LIMITATION_ID in {
        limitation["id"] for limitation in document["limitations"]
    }


def test_future_bucharest_sector_rows_stay_unassigned() -> None:
    document = enrich_access_document(
        access_doc([access_row("179141", county="B")]),
        health_view([health_unit("179132", 87, beds=8940.0)]),
    )

    row = document["uats"][0]
    assert row["hasLocalHealthProvider"] is None
    assert row["localHealthProviderCount"] is None
    assert row["localHealthClinicalBedProviders"] is None
    assert row["localHealthClinicalBeds"] is None
    assert row["healthAccessSectorRowExcluded"] is True
    assert document["summary"]["healthAccessRowsWithData"] == 0
    assert document["summary"]["healthAccessSectorRowsExcluded"] == 1


def test_missing_non_bucharest_rows_are_refused() -> None:
    with pytest.raises(ValueError, match="missing transport UAT rows"):
        enrich_access_document(
            access_doc([access_row("10"), access_row("20")]),
            health_view([health_unit("10", 1)]),
        )


def test_point_access_requires_row_locations_for_every_transport_row() -> None:
    with pytest.raises(ValueError, match="missing transport UAT row locations"):
        enrich_access_document(
            access_doc([access_row("10"), access_row("20")]),
            health_view([health_unit("10", 1), health_unit("20", 1)]),
            point_view([health_point("provider-near-10", 44.0, 26.0)]),
            {"10": {"latitude": 44.0, "longitude": 26.0}},
        )


def test_wrong_point_access_view_is_refused() -> None:
    bad = point_view([health_point("provider-near-10", 44.0, 26.0)])
    bad["id"] = "wrong"

    with pytest.raises(ValueError, match=HEALTH_POINT_ACCESS_VIEW_ID):
        enrich_access_document(
            access_doc([access_row("10")]),
            health_view([health_unit("10", 1)]),
            bad,
            {"10": {"latitude": 44.0, "longitude": 26.0}},
        )


def test_duplicate_rows_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate SIRUTA"):
        enrich_access_document(
            access_doc([access_row("10")]),
            health_view([health_unit("10", 1), health_unit("010", 2)]),
        )
    with pytest.raises(ValueError, match="duplicate SIRUTA"):
        enrich_access_document(
            access_doc([access_row("10"), access_row("010")]),
            health_view([health_unit("10", 1)]),
        )


class TestPublished:
    @staticmethod
    def _access() -> dict:
        path = ROOT / "data" / "access.json"
        if not path.exists():
            pytest.skip("access not built")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _health() -> dict:
        return json.loads(HEALTH_ACCESS.read_text(encoding="utf-8"))

    @staticmethod
    def _health_point() -> dict:
        return json.loads(HEALTH_POINT_ACCESS.read_text(encoding="utf-8"))

    def test_published_access_consumes_the_shared_health_view(self) -> None:
        access = self._access()
        health = self._health()
        summary = access["summary"]
        assert summary["healthAccessView"] == health["id"]
        assert summary["healthAccessEligibleProviders"] == health["summary"]["eligibleProviders"]
        assert summary["healthAccessBlockedProviders"] == health["summary"]["blockedProviders"]
        assert summary["healthAccessNamedExclusions"] == health["summary"]["namedExclusions"]
        assert summary["healthAccessRowsWithData"] == len(access["uats"])
        assert summary["healthAccessLocalProviders"] <= summary["healthAccessEligibleProviders"]
        assert HEALTH_ACCESS_LIMITATION_ID in {item["id"] for item in access["limitations"]}

    def test_published_row_counts_match_the_shared_view(self) -> None:
        access = self._access()
        health_by_siruta = {unit["siruta"]: unit for unit in self._health()["units"]}

        for row in access["uats"]:
            shared = health_by_siruta[row["siruta"]]
            assert row["hasLocalHealthProvider"] == shared["hasLocalProvider"], row["siruta"]
            assert row["localHealthProviderCount"] == shared["localProviderCount"], row["siruta"]
            assert row["localHealthClinicalBedProviders"] == shared["localClinicalBedProviders"], (
                row["siruta"]
            )
            assert row["localHealthClinicalBeds"] == shared["localClinicalBeds"], row["siruta"]
            assert row["healthAccessSectorRowExcluded"] is False, row["siruta"]

        assert access["summary"]["healthAccessLocalProviders"] == sum(
            row["localHealthProviderCount"] for row in access["uats"]
        )
        assert access["summary"]["healthAccessUatsWithLocalProvider"] == sum(
            1 for row in access["uats"] if row["hasLocalHealthProvider"]
        )

    def test_published_access_consumes_the_point_health_view(self) -> None:
        access = self._access()
        point_access = self._health_point()
        point_ids = {point["providerId"] for point in point_access["points"]}
        summary = access["summary"]

        assert summary["healthPointAccessView"] == point_access["id"]
        assert (
            summary["healthPointAccessProviders"] == point_access["summary"]["pointAccessProviders"]
        )
        assert (
            summary["healthPointAccessBlockedProviders"]
            == point_access["summary"]["pointAccessBlockedProviders"]
        )
        assert (
            summary["healthPointAccessNamedExclusions"]
            == point_access["summary"]["namedExclusions"]
        )
        assert summary["healthPointAccessDistanceMethod"] == HEALTH_POINT_DISTANCE_METHOD
        assert summary["healthPointAccessRowsWithDistance"] == len(access["uats"])
        assert HEALTH_POINT_ACCESS_LIMITATION_ID in {item["id"] for item in access["limitations"]}

        for row in access["uats"]:
            assert row["nearestHealthPointProviderId"] in point_ids, row["siruta"]
            assert row["nearestHealthPointDistanceMetres"] >= 0, row["siruta"]
