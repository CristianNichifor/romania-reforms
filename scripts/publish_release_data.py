"""Upload a derived payload to a release and record what was uploaded.

The counterpart to `fetch_release_data.py`. It uploads the file, then rewrites
`data-assets.json` with the size and SHA-256 of exactly what it sent — so the manifest can
never claim a checksum nobody produced, which is the only way the fetcher's integrity check
means anything.

**The checksum is written from the uploaded bytes, not from the local file as it was before.**
Same thing today, but it will not be the day someone edits the file between building and
publishing, and that is precisely the day a wrong payload would otherwise be blessed.

Needs the `gh` CLI, authenticated with write access. Creating or updating a release is a
public act on a public repository: it is the one step here that other people can see.

Usage:
    uv run python scripts/publish_release_data.py --id transport-road-speeds
    uv run python scripts/publish_release_data.py --id transport-road-speeds --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data-assets.json"

sys.path.insert(0, str(ROOT / "scripts"))
from fetch_release_data import digest  # noqa: E402


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def ensure_release(tag: str, dry_run: bool) -> None:
    """Create the release if it is not there. Idempotent, because re-publishing is normal."""
    existing = run(["gh", "release", "view", tag, "--json", "tagName"])
    if existing.returncode == 0:
        print(f"  release {tag} exists")
        return
    if dry_run:
        print(f"  would create release {tag}")
        return
    notes = (
        "Derived map payloads, kept out of the tracked tree so the repository stays under the "
        "size gate in scripts/check_repo_size.py. Fetched at build time by "
        "scripts/fetch_release_data.py, which verifies the checksum recorded in "
        "data-assets.json. Everything here is reproducible from the pipeline; nothing here is "
        "a source."
    )
    created = run(
        ["gh", "release", "create", tag, "--title", f"Data payloads {tag}", "--notes", notes]
    )
    if created.returncode != 0:
        raise SystemExit(f"gh release create failed: {created.stderr.strip()}")
    print(f"  created release {tag}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="asset id from data-assets.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next((a for a in document["assets"] if a["id"] == args.id), None)
    if entry is None:
        known = ", ".join(a["id"] for a in document["assets"])
        raise SystemExit(f"unknown id {args.id!r}; manifest has: {known}")

    source = ROOT / entry["destination"]
    if not source.exists():
        raise SystemExit(f"{source} does not exist — build it first with {entry['producedBy']}")

    size, sha = source.stat().st_size, digest(source)
    print(f"  {entry['id']}: {size / 1_048_576:.2f} MB, sha256 {sha[:16]}…")

    ensure_release(entry["tag"], args.dry_run)

    if args.dry_run:
        print(f"  would upload {source.name} as {entry['asset']} to {entry['tag']}")
        print("  would record the size and checksum in data-assets.json")
        return 0

    # --clobber so re-publishing replaces rather than erroring. The manifest is what pins the
    # version; the tag is only where the bytes live.
    uploaded = run(
        [
            "gh",
            "release",
            "upload",
            entry["tag"],
            f"{source}#{entry['asset']}",
            "--clobber",
        ]
    )
    if uploaded.returncode != 0:
        raise SystemExit(f"gh release upload failed: {uploaded.stderr.strip()}")
    print(f"  uploaded to {entry['tag']}")

    entry["bytes"], entry["sha256"] = size, sha
    MANIFEST.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  recorded size and checksum in data-assets.json — commit it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
