"""Verify that every vendored Civic UI archive is pinned to the published release."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = "https://github.com/CristianNichifor/civic-ui/releases/download/v0.3.0/civic-ui-css-0.3.0.tgz"
SHA256 = "644b181b1a061516ddfe7cbcbba9d94101e7e0b4f97f4a52c085cccba1f27226"


def main() -> None:
    manifests = sorted(ROOT.glob("simulators/**/vendor/civic-ui/provenance.json"))
    if not manifests:
        raise SystemExit("no Civic UI provenance manifests found")
    for manifest in manifests:
        document = json.loads(manifest.read_text(encoding="utf-8"))
        if document.get("release") != RELEASE:
            raise SystemExit(f"{manifest}: unexpected release URL")
        if document.get("sha256") != SHA256:
            raise SystemExit(f"{manifest}: unexpected archive checksum")
        vendor = manifest.parent
        for relative in document.get("files", []):
            path = vendor / relative
            if not path.is_file():
                raise SystemExit(f"{manifest}: missing listed file {relative}")
    print(f"verified {len(manifests)} Civic UI provenance manifests")


if __name__ == "__main__":
    main()
