from __future__ import annotations

import pytest

from pipeline.build_local_finance import build_payload


def mart_record(
    year: int,
    siruta: str,
    revenue: float,
    own_revenue: float,
    spending: float = 0,
) -> dict:
    return {
        "year": year,
        "siruta": siruta,
        "revenueRon": revenue,
        "ownRevenueRon": own_revenue,
        "spendingRon": spending,
    }


def test_build_payload_aligns_shared_mart_to_web_uat_order() -> None:
    mart = {
        "id": "local-finance-mart-2023-2025",
        "publisher": "Transparenta.eu",
        "records": [
            mart_record(2023, "10", 1_000, 200, 1_000),
            mart_record(2023, "20", 100, 10, 200),
            mart_record(2024, "AB", 1_000, 100),
            mart_record(2024, "00010", 200, 50),
            mart_record(2024, "20", 300, 75),
            mart_record(2025, "10", 2_000, 800, 1_500),
            mart_record(2025, "20", 100, 20, 100),
        ],
    }
    attributes = {"siruta": ["20", "10"]}

    payload = build_payload(mart, attributes, 2024, "a" * 64)

    assert payload["id"] == "administrativ-local-finance-2024"
    assert payload["sourceMartId"] == "local-finance-mart-2023-2025"
    assert payload["sourceMartSha256"] == "a" * 64
    assert payload["sourceYears"] == [2023, 2024, 2025]
    assert payload["siruta"] == ["20", "10"]
    assert payload["revenueRon"] == [300.0, 200.0]
    assert payload["ownRevenueRon"] == [75.0, 50.0]
    assert payload["ownRevenueShare"] == [0.25, 0.25]
    assert payload["spendingRon2023"] == [200.0, 1_000.0]
    assert payload["spendingRon2025"] == [100.0, 1_500.0]
    assert payload["revenueRon2023"] == [100.0, 1_000.0]
    assert payload["revenueRon2025"] == [100.0, 2_000.0]
    assert payload["ownRevenueRon2023"] == [10.0, 200.0]
    assert payload["ownRevenueRon2025"] == [20.0, 800.0]
    assert payload["spendingGrowth2023To2025"] == [-0.5, 0.5]
    assert payload["ownRevenueShareChange2023To2025"] == [0.1, 0.2]
    assert payload["summary"]["excludedSourceRecords"] == 1


def test_build_payload_uses_null_for_missing_or_zero_trend_denominators() -> None:
    mart = {
        "id": "local-finance-mart-2023-2025",
        "records": [
            mart_record(2023, "10", 0, 0, 0),
            mart_record(2024, "10", 200, 50),
            mart_record(2024, "20", 300, 75),
            mart_record(2025, "10", 100, 50, 200),
            mart_record(2025, "20", 100, 50, 200),
        ],
    }
    attributes = {"siruta": ["10", "20"]}

    payload = build_payload(mart, attributes, 2024, "a" * 64)

    assert payload["spendingRon2023"] == [0.0, None]
    assert payload["spendingRon2025"] == [200.0, 200.0]
    assert payload["revenueRon2023"] == [0.0, None]
    assert payload["revenueRon2025"] == [100.0, 100.0]
    assert payload["spendingGrowth2023To2025"] == [None, None]
    assert payload["ownRevenueShareChange2023To2025"] == [None, None]


def test_build_payload_refuses_missing_uats() -> None:
    mart = {
        "id": "local-finance-mart-2023-2025",
        "records": [mart_record(2024, "10", 200, 50)],
    }
    attributes = {"siruta": ["10", "20"]}

    with pytest.raises(ValueError, match="missing 2024 rows"):
        build_payload(mart, attributes, 2024, "a" * 64)


def test_build_payload_refuses_duplicate_mart_rows() -> None:
    mart = {
        "id": "local-finance-mart-2023-2025",
        "records": [
            mart_record(2024, "10", 200, 50),
            mart_record(2024, "010", 250, 60),
        ],
    }
    attributes = {"siruta": ["10"]}

    with pytest.raises(ValueError, match="duplicate 2024 SIRUTA"):
        build_payload(mart, attributes, 2024, "a" * 64)
