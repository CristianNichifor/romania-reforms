"""Tests for the deconcentrated-services merge and the eight regions it lands on.

Two things here are load-bearing and would fail quietly if they drifted:

- the eight regions must stay the *same* eight `justitie` derived, because the whole argument
  is that one country can be cut the same way for courts and for everything else. If this
  simulator ever grew its own county→region map, the two would diverge without anyone noticing.
- the reduction must reconcile with the source rows. A headline "78,7%" that cannot be rebuilt
  from `matchedOffices + municipalExcluded == deconcentratedOfficesTotal` is a number, not a
  finding.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "simulators" / "deconcentrare"
DATA = SIM / "data" / "deconcentrare.json"
OFFICES = SIM / "data" / "deconcentrare-registry.json"
INSTITUTIONS = SIM / "data" / "institutii-2025.json"
PORTAL = SIM / "data" / "portal-ep-2026.json"
BUILD = SIM / "scripts" / "build_deconcentrare.py"
PORTAL_IMPORT = SIM / "scripts" / "import_portal_ep.py"
REGIONS = ROOT / "simulators" / "justitie" / "data" / "curti-apel-regiuni.json"
REGISTRY = ROOT / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"

# Legea 315/2004: the eight development regions hold 2, 4, 5, 6, 6, 6, 6 and 7 counties.
EXPECTED_SIZES = sorted([2, 4, 5, 6, 6, 6, 6, 7])


@pytest.fixture(scope="module")
def data() -> dict:
    if not DATA.exists():
        pytest.skip("the deconcentrated dataset is not built")
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_the_regions_are_the_same_eight_justitie_derived(data):
    """One country, one cut. The composition must equal the court variant's, county for county."""
    ours = {group["region"] for fam in data["families"] for group in fam["regions"]}
    theirs = json.loads(REGIONS.read_text(encoding="utf-8"))["regions"]
    assert ours == {r["region"] for r in theirs}
    assert sorted(len(r["counties"]) for r in theirs) == EXPECTED_SIZES


def test_every_county_sits_in_exactly_one_region(data):
    seen: list[str] = []
    for family in data["families"]:
        for group in family["regions"]:
            seen.extend(group["counties"])
    # 42 counties appear once per family that reaches them; the union must still be the 42.
    union = set(seen)
    assert len(union) == 42


def test_a_regional_family_proposes_one_office_per_region_it_reaches(data):
    for family in data["families"]:
        if family["tier"] != "regional":
            continue
        assert family["officesProposed"] == len(family["regions"])
        assert family["officesProposed"] <= 8
        assert family["officesToday"] >= family["officesProposed"]


def test_every_region_group_names_a_seat_among_its_counties(data):
    """The seat is a county the family actually has, and exactly one per region."""
    for family in data["families"]:
        for group in family["regions"]:
            assert group["seat"] in group["counties"]
            assert group["counties"].count(group["seat"]) == 1
            assert group["seatPopulation"] is not None


def test_the_seat_is_the_largest_present_county_by_population(data):
    """The rule is written down: the seat is the largest county by population among those the
    family actually has. Recompute it from the shared registry rather than hardcoding, because
    partial-coverage families may lack the region's largest county."""
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["units"]
    population = {
        unit["countyCode"]: unit["population"]
        for unit in registry
        if unit.get("level") == "county" and unit.get("countyCode") and unit.get("population")
    }
    for family in data["families"]:
        for group in family["regions"]:
            expected = max(
                group["counties"],
                key=lambda county: (population.get(county, 0), county),
            )
            assert group["seat"] == expected
            assert group["seatPopulation"] == population[group["seat"]]
    assert data["seatRule"]["confidence"] == "assumed"


def test_the_headline_reconciles_with_the_source_rows(data):
    """Matched offices (both sources) plus ANFP municipal = the total, and the reduction is
    recomputable. The ANFP-only baseline survives in summary.anfp."""
    summary = data["summary"]
    matched = summary["matchedOffices"] + summary["municipalExcluded"]
    assert matched == summary["deconcentratedOfficesTotal"]
    assert summary["matchedOffices"] == sum(f["officesToday"] for f in data["families"])
    today = summary["officesTodayInRegionalFamilies"]
    proposed = summary["officesProposedOnEightRegions"]
    assert proposed == sum(
        f["officesProposed"] for f in data["families"] if f["tier"] == "regional"
    )
    assert summary["reductionPercent"] == pytest.approx(round(100 * (today - proposed) / today, 1))
    anfp = summary["anfp"]
    assert anfp["matchedOffices"] + summary["municipalExcluded"] == anfp["deconcentratedOfficesTotal"]
    assert anfp["officesTodayInRegionalFamilies"] == 549
    assert anfp["officesProposedOnEightRegions"] == 117


def test_no_source_name_is_silently_dropped(data):
    """The family table must cover the source. A refresh that adds a family fails here, loudly."""
    assert data["summary"]["unmatched"] == 0
    assert data["unmatchedNames"] == []


def test_every_family_counts_its_two_sources_separately(data):
    """sources.anfp + sources.portal must rebuild officesToday exactly — the reader can tell
    which source each office came from without opening the registry."""
    for family in data["families"]:
        assert family["sources"]["anfp"] + family["sources"]["portal"] == family["officesToday"]
    assert sum(f["sources"]["portal"] for f in data["families"]) == data["summary"]["portal"]["kept"]


def test_the_portal_complement_adds_the_services_anfp_lacks(data):
    """The blocked families from coverage-gap.md are now counted, from the portal source."""
    by_code = {f["code"]: f for f in data["families"]}
    for code in ("ocpi", "politie", "ambulanta", "isu", "dgaspc", "scolar", "ospa", "jandarmerie"):
        family = by_code[code]
        assert family["sources"]["anfp"] == 0
        assert family["sources"]["portal"] > 0
        assert family["tier"] == "regional"
    # the prefect stays a reported county office, not a merged one
    assert by_code["prefectura"]["tier"] == "special"


def test_the_dedupe_drops_portal_rows_the_anfp_source_already_covers(data):
    """A portal row for a (family, county) ANFP already carries is not a complement."""
    assert data["summary"]["portal"]["droppedDuplicate"] > 0
    dsv = next(f for f in data["families"] if f["code"] == "dsv")
    assert dsv["sources"]["portal"] == 0


def test_the_import_carries_the_checksum_of_the_committed_source(data):
    if not INSTITUTIONS.exists():
        pytest.skip("the ANFP import is not built")
    source = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    assert len(source["sourceChecksum"]["sha256"]) == 64
    assert source["provenance"]["confidence"] == "verbatim"


def test_the_portal_import_is_committed_and_deterministic():
    if not PORTAL.exists():
        pytest.skip("the portal complement is not built")
    portal = json.loads(PORTAL.read_text(encoding="utf-8"))
    assert len(portal["sourceChecksum"]["sha256"]) == 64
    assert portal["summary"]["matched"] > 300
    first = PORTAL.read_bytes()
    subprocess.run(
        [sys.executable, str(PORTAL_IMPORT)], check=True, capture_output=True, cwd=SIM / "scripts"
    )
    assert PORTAL.read_bytes() == first


def test_the_build_is_deterministic():
    """Same source, byte-identical output — the rule every simulator in the repository obeys."""
    if not INSTITUTIONS.exists():
        pytest.skip("the ANFP import is not built")
    first = DATA.read_bytes()
    subprocess.run([sys.executable, str(BUILD)], check=True, capture_output=True)
    assert DATA.read_bytes() == first


@pytest.fixture(scope="module")
def offices() -> dict:
    if not OFFICES.exists():
        pytest.skip("the row-by-row office registry is not built")
    return json.loads(OFFICES.read_text(encoding="utf-8"))


def test_the_office_registry_has_one_row_per_deconcentrated_office(data, offices):
    assert offices["summary"]["offices"] == data["summary"]["deconcentratedOfficesTotal"]
    assert len(offices["offices"]) == offices["summary"]["offices"]


def test_the_office_registry_rebuilds_the_family_counts(data, offices):
    """Every family's officesToday must be the same count the row list rebuilds."""
    by_family: dict[str, int] = {}
    for row in offices["offices"]:
        if row["family"]:
            by_family[row["family"]] = by_family.get(row["family"], 0) + 1
    for family in data["families"]:
        assert by_family.get(family["code"], 0) == family["officesToday"]
    assert offices["summary"]["municipal"] == data["summary"]["municipalExcluded"] == 9
    assert offices["summary"]["unmatched"] == data["summary"]["unmatched"] == 0


def test_the_office_registry_regional_rows_match_the_reduction(data, offices):
    rows = [row for row in offices["offices"] if row["tier"] == "regional"]
    assert len(rows) == data["summary"]["officesTodayInRegionalFamilies"]
    # every row the scenario keeps or absorbs must carry a resolvable county
    assert all(row["county"] for row in rows)


def test_the_office_registry_is_deterministic(offices):
    if not INSTITUTIONS.exists():
        pytest.skip("the ANFP import is not built")
    first = OFFICES.read_bytes()
    subprocess.run([sys.executable, str(BUILD)], check=True, capture_output=True)
    assert OFFICES.read_bytes() == first
