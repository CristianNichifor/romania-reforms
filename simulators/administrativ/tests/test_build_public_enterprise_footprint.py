from __future__ import annotations

import pytest

from pipeline.build_public_enterprise_footprint import build_payload


def source_row(siruta: str, company_count: int, revenue: float = 0.0) -> dict:
    return {
        "siruta": siruta,
        "name": f"UAT {siruta}",
        "level": "commune",
        "countyCode": "TS",
        "countyName": "TEST",
        "population": 1000,
        "authorityCount": 1,
        "companyCount": company_count,
        "activeCompanyCount": company_count,
        "companiesWithFinancials": company_count,
        "lossMakingCompanyCount": 0,
        "subsidizedCompanyCount": 0,
        "employeeCount": 5,
        "revenueRon": revenue,
        "profitLossRon": 10,
        "debtRon": 20,
        "subsidiesRon": 30,
    }


def test_build_payload_aligns_public_enterprise_footprint_to_web_uat_order() -> None:
    source = {
        "id": "public-enterprise-administrative-footprint-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "publisher": "companiidestat.ro",
        "license": "CC BY 4.0",
        "attribution": "companiidestat.ro",
        "uats": [source_row("20", 2, 200), source_row("10", 1, 100), source_row("30", 3, 300)],
    }
    attributes = {"siruta": ["10", "20", "40"]}

    payload = build_payload(source, attributes, "a" * 64)

    assert payload["id"] == "administrativ-public-enterprise-footprint-2024-2026"
    assert payload["sourceViewId"] == source["id"]
    assert payload["siruta"] == ["10", "20", "40"]
    assert payload["companyCount"] == [1.0, 2.0, 0.0]
    assert payload["revenueRon"] == [100.0, 200.0, 0.0]
    assert payload["employeeCount"] == [5.0, 5.0, 0.0]
    assert payload["summary"]["matchedSourceUats"] == 2
    assert payload["summary"]["excludedSourceUats"] == 1
    assert payload["summary"]["excludedSourceSiruta"] == ["30"]


def test_build_payload_refuses_duplicate_source_uat_rows() -> None:
    source = {
        "id": "public-enterprise-administrative-footprint-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "publisher": "companiidestat.ro",
        "license": "CC BY 4.0",
        "attribution": "companiidestat.ro",
        "uats": [source_row("10", 1), source_row("010", 2)],
    }
    attributes = {"siruta": ["10"]}

    with pytest.raises(ValueError, match="duplicate UAT SIRUTA"):
        build_payload(source, attributes, "a" * 64)
