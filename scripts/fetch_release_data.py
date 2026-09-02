"""Fetch the derived payloads that are published but not committed.

`check_repo_size.py` caps the tracked tree and says, when that cap trips, the fix is to stop
committing derived payloads rather than to raise it. This is the other half of that sentence:
the payloads live as release assets and are pulled in at build time, listed in
`data-assets.json` with the checksum each must have.

**The two failure modes are treated differently on purpose.**

A *missing* asset is a warning and the build continues. The apps already degrade — the
transport map disables its speed-limit toggle and says why — and a GitHub outage must not be
able to stop four other simulators from publishing. The site loses a layer; nobody ships a
broken page.

A *wrong* asset is fatal. A payload that downloaded corrupt, or that a rolling tag quietly
replaced, would be published as though it were the real measurement, and a map is exactly the
place where nobody would notice. So the checksum is verified before the file is written, and a
mismatch stops the build rather than shipping something plausible.

**Already-correct files are left alone**, which is what makes this usable locally: whoever has
the OSM extract builds the payload, and running this afterwards neither re-downloads it nor
overwrites it — it just confirms the checksum matches what the manifest promises.

Usage:
    uv run python scripts/fetch_release_data.py
    uv run python scripts/fetch_release_data.py --list
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data-assets.json"

REPO: Final[str] = "CristianNichifor/romania-reforms"
RELEASE_URL: Final[str] = "https://github.com/{repo}/releases/download/{tag}/{asset}"
TIMEOUT_S: Final[int] = 300


def digest(path: Path) -> str:
    """SHA-256 of a file, read in chunks so a 300 MB payload does not become 300 MB of RAM."""
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["assets"]


def fetch(entry: dict, repo: str = REPO) -> tuple[bool, str]:
    """Return (ok, message). `ok` False only for a fault worth failing the build over."""
    destination = ROOT / entry["destination"]
    expected = entry.get("sha256") or ""

    if destination.exists():
        if not expected:
            return True, f"{entry['id']}: present, manifest carries no checksum yet"
        found = digest(destination)
        if found == expected:
            return True, f"{entry['id']}: present and matches the manifest"
        # Present but wrong. Do not overwrite silently: locally this is almost always a
        # freshly rebuilt payload that the manifest has not caught up with, and clobbering
        # someone's rebuild with an older release would be the rudest possible behaviour.
        return False, (
            f"{entry['id']}: {entry['destination']} does not match the manifest\n"
            f"    expected {expected}\n    found    {found}\n"
            "    If you rebuilt it, publish it and update the manifest; otherwise delete it "
            "and re-run to take the release copy."
        )

    url = RELEASE_URL.format(repo=repo, tag=entry["tag"], asset=entry["asset"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response:  # noqa: S310
            temporary.write_bytes(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
        temporary.unlink(missing_ok=True)
        # Warning, not failure. See the module docstring: the apps degrade, and one missing
        # layer must not stop the other simulators publishing.
        return True, f"{entry['id']}: NOT AVAILABLE ({error}) — {entry['withoutIt']}"

    if expected:
        found = digest(temporary)
        if found != expected:
            temporary.unlink(missing_ok=True)
            return False, (
                f"{entry['id']}: downloaded payload has the wrong checksum\n"
                f"    expected {expected}\n    found    {found}\n"
                f"    from {url}"
            )
    temporary.replace(destination)
    size_mb = destination.stat().st_size / 1_048_576
    return True, f"{entry['id']}: fetched {size_mb:.1f} MB from {entry['tag']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show the manifest and exit")
    parser.add_argument("--repo", default=REPO, help="owner/name to fetch releases from")
    args = parser.parse_args(argv)

    assets = load_manifest()
    if args.list:
        for entry in assets:
            state = "present" if (ROOT / entry["destination"]).exists() else "absent"
            print(f"  {entry['id']:<28} {state:<8} {entry['tag']}/{entry['asset']}")
        return 0

    failures = []
    for entry in assets:
        ok, message = fetch(entry, args.repo)
        print(f"  {message}")
        if not ok:
            failures.append(entry["id"])

    if failures:
        print(f"\n{len(failures)} payload(s) wrong, not merely missing: {', '.join(failures)}")
        return 1
    print(f"\n{len(assets)} payload(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
