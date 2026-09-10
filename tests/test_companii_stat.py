"""Tests for the state-company cluster view and its regional-operator scenario.

The scenario is the soft part of this simulator — which activities count as network utilities is
a policy choice — so the tests pin the parts that are *not* a choice: the clusters must rebuild
the company count exactly, the headcount must stay a lower bound, and the tier table must not be
able to quietly merge a strategic holding into a regional operator.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "simulators" / "companii-stat"
DATA = SIM / "data" / "companii-stat.json"
COMPANIES = SIM / "data" / "companii-2025.json"
BUILD = SIM / "scripts" / "build_companii_stat.py"

REGIONS = 8


@pytest.fixture(scope="module")
def data() -> dict:
    if not DATA.exists():
        pytest.skip("the state-company dataset is not built")
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_the_clusters_rebuild_the_company_count(data):
    assert sum(c["companies"] for c in data["clusters"]) == data["summary"]["companies"]
    assert data["summary"]["clusters"] == len(data["clusters"])


def test_a_regional_cluster_proposes_one_operator_per_region(data):
    for cluster in data["clusters"]:
        if cluster["tier"] == "regional":
            assert cluster["proposed"] == REGIONS
            assert cluster["companies"] >= cluster["proposed"]
        else:
            assert cluster["proposed"] == cluster["companies"]


def test_the_scenario_reconciles(data):
    summary = data["summary"]
    regional = [c for c in data["clusters"] if c["tier"] == "regional"]
    assert summary["regionalClusters"] == len(regional)
    assert summary["companiesInRegionalClusters"] == sum(c["companies"] for c in regional)
    assert summary["operatorsProposedOnEightRegions"] == REGIONS * len(regional)
    today = summary["companiesInRegionalClusters"]
    proposed = summary["operatorsProposedOnEightRegions"]
    assert summary["reductionPercent"] == pytest.approx(round(100 * (today - proposed) / today, 1))


def test_micro_companies_are_counted_but_never_guessed(data):
    assert data["summary"]["microUnder20"] == sum(c["micro"] for c in data["clusters"])
    for cluster in data["clusters"]:
        assert cluster["micro"] <= cluster["headcountKnown"] <= cluster["companies"]


def test_the_headcount_is_a_lower_bound_and_says_so(data):
    limitations = {x["id"]: x for x in data["limitations"]}
    assert limitations["headcount-partial"]["severity"] == "material"
    assert data["summary"]["headcountKnown"] < data["summary"]["companies"]


def test_the_tier_table_is_declared_a_policy_choice(data):
    assert data["provenance"]["confidence"] == "assumed"
    assert "tier-is-policy" in {x["id"] for x in data["limitations"]}


def test_strategic_holdings_are_not_swept_into_regions(data):
    """Electricity, weapons and airports stay national: merging them is another argument."""
    by_caen = {c["caen"]: c for c in data["clusters"]}
    for caen in ("3511", "2540", "5223"):
        if caen in by_caen:
            assert by_caen[caen]["tier"] == "national"


def test_the_import_carries_the_checksum_of_the_committed_source(data):
    if not COMPANIES.exists():
        pytest.skip("the state-company import is not built")
    source = json.loads(COMPANIES.read_text(encoding="utf-8"))
    assert len(source["sourceChecksum"]["sha256"]) == 64
    assert source["summary"]["companies"] == data["summary"]["companies"]


def test_the_murighiol_headcount_is_excluded_and_named():
    """A village waste utility reporting 10 776 employees is an entry error. The value must
    not reach the cluster totals, and the exclusion must name the row so nobody has to
    rediscover it."""
    if not COMPANIES.exists():
        pytest.skip("the state-company import is not built")
    source = json.loads(COMPANIES.read_text(encoding="utf-8"))
    murighiol = next((c for c in source["companies"] if c["id"] == 1217), None)
    assert murighiol is not None, "the outlier row disappeared instead of being excluded"
    assert murighiol.get("employees") is None
    excluded = source["dataQuality"]["headcountExcluded"]
    assert len(excluded) == 1
    row = excluded[0]
    assert row["companyId"] == 1217
    assert row["reported"] == 10776
    assert row["year"] == 2023
    assert "MURIGHIOL" in row["name"]


def test_the_build_is_deterministic():
    if not COMPANIES.exists():
        pytest.skip("the state-company import is not built")
    first = DATA.read_bytes()
    subprocess.run([sys.executable, str(BUILD)], check=True, capture_output=True)
    assert DATA.read_bytes() == first


def test_every_company_carries_a_registration_county(data):
    """The county join must be complete: a company without one silently drops out of the
    regional operators below."""
    if not COMPANIES.exists():
        pytest.skip("the state-company import is not built")
    source = json.loads(COMPANIES.read_text(encoding="utf-8"))
    with_county = sum(1 for c in source["companies"] if c.get("county"))
    assert with_county == source["summary"]["companies"]
    assert source["dataQuality"]["unmatchedCounties"] == []


def test_regional_operators_rebuild_the_cluster(data):
    """Absorbed + absorber must account for every company in the cluster."""
    for cluster in data["clusters"]:
        if cluster["tier"] != "regional":
            continue
        assert len(cluster["regions"]) <= 8
        accounted = sum(
            group["absorbedCount"] + (1 if group["absorber"] else 0) for group in cluster["regions"]
        )
        assert accounted == cluster["companies"]


def test_the_absorber_is_the_largest_by_headcount_in_the_seat_county(data):
    """The rule: the seat county's largest company by reported headcount. Where none report
    one, the operator stays unnamed rather than guessed."""
    if not COMPANIES.exists():
        pytest.skip("the state-company import is not built")
    source = json.loads(COMPANIES.read_text(encoding="utf-8"))
    for cluster in data["clusters"]:
        if cluster["tier"] != "regional":
            continue
        for group in cluster["regions"]:
            members = [
                c
                for c in source["companies"]
                if c["caen"] == cluster["caen"]
                and c.get("county") == group["seatCounty"]
                and c.get("employees") is not None
            ]
            if not members:
                assert group["absorber"] is None
                continue
            largest = max(members, key=lambda c: c["employees"])
            assert group["absorber"] is not None
            assert group["absorber"]["cui"] == largest["cui"]
            assert group["absorber"]["employees"] == largest["employees"]


def test_in_flight_mergers_are_reported_as_status_only(data):
    for merger in data["inFlightMergers"]:
        assert "fuziune" in merger["status"] or "absorb" in merger["status"].lower()
    assert data["summary"]["inFlightMergers"] == len(data["inFlightMergers"])
    assert "in-flight-status-only" in {x["id"] for x in data["limitations"]}
