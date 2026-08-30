"""Tests for routing zones.

A zone is where a bus may drive. Getting it wrong does not fail loudly — it silently strands
UATs and shrinks the fleet — so these tests are mostly about the one exception.
"""

from __future__ import annotations

from scripts.zones import zone_of, zones_from_counties


def test_an_ordinary_county_is_its_own_zone():
    assert zone_of("VL") == "VL"
    assert zone_of("MS") == "MS"


def test_bucharest_and_ilfov_share_a_zone():
    """The only cross-county case in the country: 28 Ilfov communes are assigned to
    Sectorul 1, because Bucharest is a municipality ringed by Ilfov and the ring commutes
    inward. Treating them separately makes those 28 unroutable."""
    assert zone_of("B") == zone_of("IF")


def test_the_shared_zone_is_not_some_other_county():
    assert zone_of("B") not in ("B", "IF")


def test_zones_group_every_uat():
    counties = {"1": "VL", "2": "VL", "3": "B", "4": "IF", "5": "MS"}
    zones = zones_from_counties(counties)
    assert sum(len(members) for members in zones.values()) == len(counties)


def test_the_bucharest_zone_holds_both_counties_members():
    counties = {"1": "B", "2": "IF", "3": "VL"}
    zones = zones_from_counties(counties)
    assert zones[zone_of("B")] == {"1", "2"}
    assert zones["VL"] == {"3"}


def test_an_unknown_county_still_gets_a_zone():
    """A county code this module has never seen must route within itself rather than raise:
    a new code should cost coverage, not the whole build."""
    assert zone_of("XX") == "XX"
