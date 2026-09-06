"""Tests for the snapshot coverage merge.

Summing twelve dictionaries needs no tests. The check in the middle does, because it is the one
that would have stopped a failure that shipped: on 2026-09-05 a release ended up holding ten
shards of a 3,7-year backfill beside two shards of a four-day incremental, and the result
validated, summed and rendered. Forty-one courts appeared to have heard a few dozen cases in
three and a half years.

So the tests are all about what the merge refuses, and about the fields that let a consumer
notice for itself if it ever gets past here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "simulators/justitie/scripts/merge_coverage.py"

spec = importlib.util.spec_from_file_location("merge_coverage", MODULE)
merge_coverage = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = merge_coverage
spec.loader.exec_module(merge_coverage)


def shard(since: str, *, dosare: int = 1000, complete: bool = True, courts=None) -> dict:
    return {
        "crawledAt": "2026-09-05T18:00:00",
        "window": {"since": f"{since}T00:00:00", "until": "2026-09-05T18:00:00"},
        "complete": complete,
        "courts": courts if courts is not None else {"JudecatoriaX": {}},
        "totals": {"dosare": dosare, "calls": 10},
        "note": "Snapshot of cases visible on portal.just.ro at crawledAt.",
    }


def test_shards_that_read_different_windows_are_refused():
    """The exact failure, reconstructed.

    Ten shards from a backfill and two left over from that morning's incremental. Every field
    merges cleanly; the totals add; nothing is malformed. It has to be rejected on the one thing
    that distinguishes it, which is that the parts describe different periods.
    """
    parts = [shard("2023-01-01") for _ in range(10)] + [shard("2026-07-05") for _ in range(2)]
    with pytest.raises(merge_coverage.MixedWindows) as caught:
        merge_coverage.merge(parts, collected=12)
    assert "2023-01-01" in str(caught.value)
    assert "2026-07-05" in str(caught.value)


def test_shards_that_agree_merge():
    report = merge_coverage.merge([shard("2023-01-01", dosare=500) for _ in range(12)], collected=12)
    assert report["dosare"] == 6000
    assert report["complete"] is True
    assert report["window"]["since"].startswith("2023-01-01")


def test_a_short_collection_is_never_complete():
    # Ten shards that each report success is still not a snapshot of the country. This is the
    # field the statistics builders read, and the one that was true and ignored.
    report = merge_coverage.merge([shard("2023-01-01") for _ in range(10)], collected=10)
    assert report["complete"] is False
    assert report["shardsCollected"] == 10
    assert report["shardsExpected"] == 12


def test_one_incomplete_shard_makes_the_day_incomplete():
    parts = [shard("2023-01-01") for _ in range(11)] + [shard("2023-01-01", complete=False)]
    assert merge_coverage.merge(parts, collected=12)["complete"] is False


def test_the_window_reaches_the_merged_file():
    """Without it, the merged report cannot be told apart from any other day's.

    A consumer holding only `coverage.json` has no way to know whether a court's count covers two
    months or four years — and those differ by two orders of magnitude, which is exactly the size
    of the gap that made the 2026-09-05 release look like real data.
    """
    report = merge_coverage.merge([shard("2023-01-01")], collected=1)
    assert report["window"]["since"].startswith("2023-01-01")


def test_courts_that_came_up_short_are_named():
    parts = [
        shard(
            "2023-01-01",
            courts={"JudecatoriaA": {}, "JudecatoriaB": {"failedWindows": [{"error": "timeout"}]}},
        )
    ]
    report = merge_coverage.merge(parts, collected=1)
    assert report["incompleteCourts"] == ["JudecatoriaB"]
    assert report["courtsCrawled"] == 2


def test_an_empty_merge_is_an_error_not_an_empty_report():
    # An empty report would publish as a valid snapshot of nothing.
    with pytest.raises(ValueError):
        merge_coverage.merge([], collected=0)


def test_the_cli_does_not_read_its_own_output_back_in(tmp_path):
    """`coverage.json` sits in the same directory and must not be globbed as a shard.

    It has no `window` key of the shard's shape and no `totals`, so reading it back would either
    crash or, worse, merge a summary into the thing it summarises.
    """
    (tmp_path / "coverage-part00of12.json").write_text(json.dumps(shard("2023-01-01")))
    (tmp_path / "coverage.json").write_text('{"not": "a shard"}')
    assert merge_coverage.main([str(tmp_path), "--shards", "1"]) == 0


def test_the_cli_exits_non_zero_on_mixed_windows(tmp_path, capsys):
    (tmp_path / "coverage-part00of12.json").write_text(json.dumps(shard("2023-01-01")))
    (tmp_path / "coverage-part01of12.json").write_text(json.dumps(shard("2026-07-05")))
    assert merge_coverage.main([str(tmp_path), "--shards", "2"]) == 1
    assert "refusing to publish" in capsys.readouterr().err
