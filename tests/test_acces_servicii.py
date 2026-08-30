"""Tests for the court-against-hospital comparison.

This is the file most likely to be quoted as "justice would be sparser than health care", so
the checks are aimed at the two ways that sentence could be false: a hospital distance that is
not really an upper bound, and a headline mean that is an artefact of where consolidated seats
happen to sit rather than a fact about two networks.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVICII = ROOT / "simulators/justitie/data/acces-servicii.json"
SPITALE = ROOT / "simulators/justitie/data/spitale-2026.json"


@pytest.fixture(scope="module")
def servicii() -> dict:
    if not SERVICII.exists():
        pytest.skip("the service comparison is not built")
    return json.loads(SERVICII.read_text(encoding="utf-8"))


def test_the_unmapped_counties_are_kept_and_excluded(servicii):
    """A unit whose county has no plotted hospitals would read as far from care when its
    hospital simply was not drawn. Kept in the file, out of every figure."""
    if not SPITALE.exists():
        pytest.skip("hospitals not imported")
    missing = set(json.loads(SPITALE.read_text(encoding="utf-8"))["summary"]["countiesMissing"])
    assert missing, "the map gap vanished; this exclusion would be silently pointless"
    for unit in servicii["units"]:
        assert unit["comparable"] == (unit["county"] not in missing), unit["siruta"]
    comparable = [u for u in servicii["units"] if u["comparable"]]
    assert servicii["summary"]["comparableUnits"] == len(comparable)
    assert len(comparable) < len(servicii["units"]), "nothing was excluded"


def test_the_summary_recomputes_from_its_own_rows(servicii):
    comparable = [u for u in servicii["units"] if u["comparable"]]
    people = sum(u["population"] for u in comparable)
    summary = servicii["summary"]
    assert summary["comparablePeople"] == people
    for key, field in (
        ("meanMetresToCourt", "courtMetres"),
        ("meanMetresToHospitalAtMost", "hospitalMetresAtMost"),
    ):
        weighted = sum(u[field] * u["population"] for u in comparable) / people
        assert abs(weighted - summary[key]) <= 1, key
    assert summary["medianMetresToCourt"] == int(
        statistics.median(sorted(u["courtMetres"] for u in comparable))
    )


def test_the_seat_coincidence_is_measured_on_one_set_of_seats(servicii):
    """The claim that survives every objection about seat choice.

    Consolidated seats are chosen to be significant towns, which is exactly where hospitals
    are — so the population-weighted mean flatters the hospital network. This does not: it is
    one set of seats asked about both networks, and the answers differ by a wide margin.
    """
    comparable = [u for u in servicii["units"] if u["comparable"]]
    summary = servicii["summary"]
    assert summary["seatsThatAreHospitalTowns"] == sum(
        1 for u in comparable if u["hospitalMetresAtMost"] == 0
    )
    assert summary["seatsThatAreCourtTowns"] == sum(1 for u in comparable if u["courtMetres"] == 0)
    assert summary["seatsThatAreHospitalTowns"] > 2 * summary["seatsThatAreCourtTowns"]


def test_the_hospital_network_is_denser_than_the_proposed_court_network(servicii):
    """Asserted on the median as well as the mean, because the mean is skewed by the zeros and
    a finding that only survives one statistic is not a finding."""
    summary = servicii["summary"]
    assert summary["meanMetresToHospitalAtMost"] < summary["meanMetresToCourt"]
    assert summary["medianMetresToHospitalAtMost"] < summary["medianMetresToCourt"]


def test_the_baseline_is_todays_real_court_network(servicii):
    """Without it the proposed distance is unreadable.

    38 km to a court could be a doubling of what people drive now or roughly what they already
    do. It is neither: today's median is zero, because 153 of 248 consolidated seats already
    hold a judecatorie. The comparison is only meaningful if the baseline is the courts that
    exist, so the count is pinned near 175 rather than left to whatever the file happens to
    carry.
    """
    summary = servicii["summary"]
    assert 150 < summary["todayCourts"] < 200, summary["todayCourts"]
    assert summary["seatsThatAreTodayCourtTowns"] == sum(
        1 for u in servicii["units"] if u["todayCourtMetres"] == 0
    )
    assert summary["seatsThatAreTodayCourtTowns"] > 4 * summary["seatsThatAreCourtTowns"]


def test_consolidation_can_only_lengthen_the_journey_to_a_first_level_court(servicii):
    """Closing courts cannot bring one nearer.

    Every proposed seat is also a judecatorie town today, so the 42 are a subset of the 175 and
    no unit can come out closer. If one did, the two networks would not be nested and the
    comparison would be measuring something else.
    """
    closer = [
        u["siruta"] for u in servicii["units"] if u["courtMetres"] < u["todayCourtMetres"]
    ]
    assert closer == [], closer[:10]


def test_the_bands_show_a_change_in_kind_not_degree(servicii):
    """Recomputed from the rows, and asserted in the direction the finding claims."""
    units = servicii["units"]
    for km, band in servicii["summary"]["beyond"].items():
        limit = int(km) * 1000
        now = [u for u in units if u["todayCourtMetres"] > limit]
        after = [u for u in units if u["courtMetres"] > limit]
        assert band["todayUnits"] == len(now), km
        assert band["proposedUnits"] == len(after), km
        assert band["todayPeople"] == sum(u["population"] for u in now), km
        assert band["proposedPeople"] == sum(u["population"] for u in after), km
        assert band["proposedUnits"] >= band["todayUnits"], km
    # Nobody is beyond 75 km from a judecatorie today; that is what makes the tail new rather
    # than merely worse.
    assert servicii["summary"]["beyond"]["75"]["todayUnits"] == 0


def test_losing_a_local_court_is_counted_from_the_rows(servicii):
    units = servicii["units"]
    lose = [u for u in units if u["todayCourtMetres"] == 0 and u["courtMetres"] > 0]
    summary = servicii["summary"]
    assert summary["unitsLosingTheirLocalCourt"] == len(lose)
    assert summary["peopleLosingTheirLocalCourt"] == sum(u["population"] for u in lose)
    assert summary["unitsLosingTheirLocalCourt"] > 0


def test_the_baseline_uses_the_nearest_court_and_says_so(servicii):
    """Today's legal arondare sometimes sends a commune past a nearer courthouse, so nearest-of
    understates today's real journey and the comparison is conservative."""
    assert "azi-inseamna-cea-mai-apropiata-nu-cea-arondata" in {
        x["id"] for x in servicii["limitations"]
    }


def test_police_join_the_comparison_without_a_county_exclusion(servicii):
    """Police cover all 42 counties, so unlike hospitals every routed unit counts.

    The three-way seat count is the finding: the towns the reform picks are already policing
    and health centres, and the only thing they would not be is court towns.
    """
    summary = servicii["summary"]
    units = servicii["units"]
    assert summary["seatsThatArePoliceTowns"] == sum(
        1 for u in units if u["policeMetresAtMost"] == 0
    )
    assert summary["seatsThatArePoliceTowns"] > summary["seatsThatAreCourtTowns"]
    assert summary["medianMetresToPoliceAtMost"] < summary["medianMetresToCourt"]


def test_the_police_source_is_declared(servicii):
    assert "politia-e-din-osm" in {x["id"] for x in servicii["limitations"]}


def test_hospital_distances_are_upper_bounds_and_say_so(servicii):
    """The direction of the error is the whole licence for the comparison: an unplotted
    hospital shortens the true journey, so a court that looks nearer here really is."""
    ids = {x["id"] for x in servicii["limitations"]}
    assert "distanta-la-spital-e-o-limita-de-sus" in ids
    assert "judetele-fara-spitale-marcate-sunt-excluse" in ids
    assert "media-e-trasa-in-jos-de-sedii" in ids


def test_the_comparison_does_not_equate_a_trial_with_an_emergency(servicii):
    assert "o-instanta-nu-e-o-urgenta" in {x["id"] for x in servicii["limitations"]}


def test_distances_are_plausible(servicii):
    """Romania is about 700 km across; anything past 200 km from a court is the graph."""
    for unit in servicii["units"]:
        assert 0 <= unit["courtMetres"] < 200_000, unit["siruta"]
        assert 0 <= unit["hospitalMetresAtMost"] < 200_000, unit["siruta"]


def test_units_further_from_court_are_counted_from_the_rows(servicii):
    comparable = [u for u in servicii["units"] if u["comparable"]]
    further = [u for u in comparable if u["courtMetres"] > u["hospitalMetresAtMost"]]
    assert servicii["summary"]["unitsFurtherFromCourt"] == len(further)
    assert servicii["summary"]["peopleFurtherFromCourt"] == sum(u["population"] for u in further)
