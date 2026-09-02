"""Tests for the payloads that are published but not committed.

Three simulators now draw map geometry that is not in the repository. That was the right
trade — `check_repo_size.py` names those files as the ones to move out — but it moved a whole
class of failure from "the file is wrong" to "the file is absent, or worse, quietly different",
and none of that was covered when the mechanism landed.

Two of these tests guard properties that no amount of care survives without them. A manifest
entry whose destination is not gitignored will be re-committed by the next `git add -A` and
the repository silently regrows. And a checksum that does not match must stop a build rather
than publish a plausible map, because a wrong map is the failure nobody reports.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data-assets.json"

sys.path.insert(0, str(ROOT / "scripts"))
from fetch_release_data import digest, fetch, load_manifest  # noqa: E402


@pytest.fixture(scope="module")
def assets() -> list[dict]:
    return load_manifest()


def test_every_asset_says_what_it_is_and_what_breaks_without_it(assets):
    """A manifest is the only place a reader learns why a file they cannot see is missing."""
    assert assets, "the manifest must not be empty while simulators depend on it"
    for entry in assets:
        for field in ("id", "tag", "asset", "destination", "producedBy", "what", "withoutIt"):
            assert entry.get(field), f"{entry.get('id')}: missing {field}"
        assert not entry["destination"].startswith("/"), "destinations are repo-relative"


def test_ids_and_destinations_are_unique(assets):
    """Two entries writing the same path would race, and the loser would be published."""
    ids = [entry["id"] for entry in assets]
    destinations = [entry["destination"] for entry in assets]
    assert len(ids) == len(set(ids))
    assert len(destinations) == len(set(destinations))


def test_every_destination_is_gitignored(assets):
    """The property that keeps the repository from regrowing.

    These files are large and are produced into the working tree by the pipeline, so the next
    `git add -A` re-commits them unless they are ignored. That would restore the exact problem
    the release mechanism exists to solve, and it would do it silently — the size gate would
    only complain once the ceiling was reached again.
    """
    for entry in assets:
        result = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", entry["destination"]],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"{entry['destination']} is NOT gitignored — the next `git add -A` commits "
            f"{entry.get('bytes', 0) / 1_048_576:.1f} MB back into the tree"
        )


def test_no_destination_is_tracked_by_git(assets):
    """Belt and braces: ignored but already tracked would still be committed on change."""
    for entry in assets:
        result = subprocess.run(  # noqa: S603
            ["git", "ls-files", "--error-unmatch", entry["destination"]],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, f"{entry['destination']} is still tracked"


def test_published_entries_carry_a_checksum(assets):
    """An entry with a size but no checksum has been uploaded and not recorded, which means
    the fetcher would accept whatever the tag serves today."""
    for entry in assets:
        if entry.get("bytes"):
            assert len(entry.get("sha256", "")) == 64, f"{entry['id']}: no usable sha256"


def test_a_present_and_correct_file_is_left_alone(tmp_path):
    """What makes the mechanism usable locally: whoever rebuilt a payload from the OSM extract
    must not have it silently replaced by an older release copy."""
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"the real thing")
    entry = {
        "id": "sample",
        "tag": "data-v1",
        "asset": "payload.bin",
        "destination": str(payload),
        "sha256": digest(payload),
        "withoutIt": "nothing",
    }
    # An unreachable repo: if this tried to download, it would fail rather than pass.
    ok, message = fetch(entry, repo="example/does-not-exist")
    assert ok
    assert "matches" in message
    assert payload.read_bytes() == b"the real thing"


def test_a_present_but_wrong_file_is_fatal_and_not_overwritten(tmp_path):
    """The case that must never be papered over. Overwriting would destroy a local rebuild;
    accepting would publish geometry nobody produced. So: refuse, loudly, and touch nothing."""
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"locally rebuilt, newer")
    entry = {
        "id": "sample",
        "tag": "data-v1",
        "asset": "payload.bin",
        "destination": str(payload),
        "sha256": "0" * 64,
        "withoutIt": "nothing",
    }
    ok, message = fetch(entry, repo="example/does-not-exist")
    assert not ok
    assert "does not match" in message
    assert payload.read_bytes() == b"locally rebuilt, newer", "a local rebuild was clobbered"


def test_an_unreachable_asset_is_a_warning_not_a_failure(tmp_path):
    """A GitHub outage must not stop five simulators publishing. The apps degrade on their own
    and say so; losing one map layer is not a reason to ship nothing."""
    entry = {
        "id": "sample",
        "tag": "data-v1",
        "asset": "payload.bin",
        "destination": str(tmp_path / "absent.bin"),
        "sha256": "0" * 64,
        "withoutIt": "the toggle disables itself",
    }
    ok, message = fetch(entry, repo="example/does-not-exist")
    assert ok, "a missing payload must not fail the build"
    assert "NOT AVAILABLE" in message
    assert "the toggle disables itself" in message
    assert not (tmp_path / "absent.bin").exists(), "no partial file may be left behind"


def test_the_manifest_matches_what_is_on_disk(assets):
    """When a payload is present locally it must be the one the manifest promises — otherwise
    the site and this checkout are drawing different maps and nothing says so."""
    for entry in assets:
        path = ROOT / entry["destination"]
        if not path.exists() or not entry.get("sha256"):
            continue
        assert digest(path) == entry["sha256"], (
            f"{entry['destination']} differs from the manifest. If you rebuilt it, publish it "
            "with scripts/publish_release_data.py and commit the manifest."
        )
