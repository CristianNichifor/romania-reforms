"""Tests for splitting the crawl across runners.

This is the code whose failure cost forty-one courts. Two shards hit the six-hour ceiling and
returned nothing, twice, on the two longest backfills attempted — and because the publish step
uploads what it has, the result was a release that validated, summed and rendered while missing a
sixth of the country.

The bug was not in the sharding's intent but in its arithmetic: round-robin over a list ordered
by size gives shard 0 the largest court of every group, which is the imbalance it was written to
prevent. So the tests are about the property, not the implementation — a split has to be a
partition, it has to be identical on every runner that computes it independently, and it has to
be flat even when the input is adversarially ordered.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "simulators/justitie/scripts/import_portal.py"

spec = importlib.util.spec_from_file_location("import_portal", MODULE)
portal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = portal
spec.loader.exec_module(portal)


def spread(parts: list[list[str]], weights: dict[str, int]) -> float:
    totals = [sum(weights.get(portal._shard_key(c), 0) for c in part) for part in parts]
    return max(totals) / min(totals) if min(totals) else float("inf")


def split(courts: list[str], shards: int, weights: dict[str, int]) -> list[list[str]]:
    return [portal.shard_courts(courts, index, shards, weights) for index in range(shards)]


def test_the_split_is_a_partition():
    # Every court crawled exactly once. A court in two shards is crawled twice; a court in none
    # is missing from the snapshot with nothing to say so.
    courts = [f"Judecatoria{index:03d}" for index in range(240)]
    weights = {portal._shard_key(c): index for index, c in enumerate(courts)}
    parts = split(courts, 12, weights)
    flat = [court for part in parts for court in part]
    assert sorted(flat) == sorted(courts)
    assert len(flat) == len(set(flat))


def test_every_runner_computes_the_same_assignment():
    """Each shard runs alone and takes its own part; nothing coordinates them.

    If the assignment depended on anything but the inputs — dict order, a tie broken by
    identity — two runners would disagree and a court would be crawled twice or not at all.
    """
    courts = [f"Court{index}" for index in range(50)]
    # Deliberately full of ties, which is where an unstable tie-break would show.
    weights = {portal._shard_key(c): 100 for c in courts}
    first = split(courts, 7, weights)
    for _ in range(5):
        assert split(courts, 7, weights) == first


def test_it_beats_round_robin_on_the_real_court_sizes():
    """Against the published volumes, not invented ones.

    An early version of this test used weights falling linearly from 240 to 1 and round-robin
    scored 1,10× — flat enough to look fine. Real court sizes are nothing like linear: Tribunalul
    Bucureşti carries 172.386 against a median court of about 12.000, and it is that tail which
    makes taking the largest of every group of twelve so costly. Using the actual figures is the
    difference between a test that passes and a test that would have caught this.
    """
    weights = portal.court_weights()
    assert weights, "instante-localizate-2025.json is missing; the weights come from it"
    # The enum runs roughly largest to smallest, which is the ordering the old rule assumed and
    # the one it handled worst.
    courts = sorted(weights, key=lambda name: -weights[name])

    round_robin = [courts[index::12] for index in range(12)]
    packed = split(courts, 12, weights)

    assert spread(round_robin, weights) > 1.5
    assert spread(packed, weights) < 1.05
    # And the number that decides whether a shard finishes inside the six-hour ceiling is the
    # heaviest one, not the ratio.
    heaviest = lambda parts: max(sum(weights[c] for c in part) for part in parts)  # noqa: E731
    assert heaviest(packed) < heaviest(round_robin) * 0.8


def test_one_court_far_larger_than_the_rest_cannot_be_split_away():
    """București's tribunal is 172.386 against a median court of about 12.000.

    No assignment makes that shard as light as the others, and the test says so rather than
    demanding an impossible flatness: what matters is that the giant sits alone with the
    smallest possible remainder, not that the totals match.
    """
    courts = ["Giant"] + [f"Small{index}" for index in range(60)]
    weights = {portal._shard_key("Giant"): 100_000}
    weights.update({portal._shard_key(f"Small{index}"): 1_000 for index in range(60)})
    parts = split(courts, 12, weights)
    giant = next(part for part in parts if "Giant" in part)
    assert len(giant) == 1


def test_an_unknown_court_is_not_assumed_to_be_free():
    """A court the register does not name takes the median weight, not zero.

    Zero would let a newly added court — or a whole tier the join missed — pile into one shard at
    no apparent cost, which is how this imbalance would quietly come back.
    """
    courts = [f"Known{index}" for index in range(12)] + [f"New{index}" for index in range(12)]
    weights = {portal._shard_key(f"Known{index}"): 1_000 for index in range(12)}
    parts = split(courts, 12, weights)
    # With a median prior every part holds one known and one unknown; with a zero prior all
    # twelve unknowns would land in whichever part happened to be lightest.
    assert all(len(part) == 2 for part in parts)


def test_a_single_shard_is_the_whole_list_unchanged():
    courts = ["A", "B", "C"]
    assert portal.shard_courts(courts, 0, 1, {}) == courts


def test_more_shards_than_courts_leaves_some_empty_rather_than_duplicating():
    courts = ["A", "B"]
    parts = split(courts, 5, {})
    assert sorted(c for part in parts for c in part) == ["A", "B"]
    assert sum(1 for part in parts if not part) == 3
