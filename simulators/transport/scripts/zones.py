"""Where a bus route may travel.

The design document says routes are built over the network "restricted to that region". That
is wrong, and measurably so: restricting a route to the region it serves **strands 91 UATs**
that a county-wide route reaches without difficulty. Gurghiu, Hodac and Ibănești all reach
Sovata only by leaving their region. Roads do not respect region boundaries.

A region is what a route **serves**. A zone is what a route may **cross**. With zone routing
only 14 UATs in the country are genuinely unroutable, against 105 under the region rule.

A zone is a county, with one exception. Administrativ's regions never cross county lines
except for Bucharest: **28 Ilfov communes are assigned to Sectorul 1**, because Bucharest is
a municipality ringed by Ilfov and the ring commutes inward. Treating the two separately does
not fail loudly — it quietly makes those 28 unroutable and shrinks the fleet.
"""

from __future__ import annotations

from typing import Final

# Bucharest and its ring. The only cross-county region in the country.
CAPITAL_ZONE: Final[str] = "B+IF"
CAPITAL_COUNTIES: Final[frozenset[str]] = frozenset({"B", "IF"})


def zone_of(county_code: str) -> str:
    """The routing zone a county belongs to.

    An unrecognised code routes within itself rather than raising: a county code this module
    has not seen should cost coverage, not the whole national build.
    """
    return CAPITAL_ZONE if county_code in CAPITAL_COUNTIES else county_code


def zones_from_counties(county_of: dict[str, str]) -> dict[str, set[str]]:
    """Group UATs into the zones their routes may travel within."""
    zones: dict[str, set[str]] = {}
    for uat, county_code in county_of.items():
        zones.setdefault(zone_of(county_code), set()).add(uat)
    return zones
