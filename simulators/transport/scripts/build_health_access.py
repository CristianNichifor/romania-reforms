"""Refresh transport access rows from the shared health-access UAT view.

Usage:
    uv run python -m scripts.build_health_access
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.health_access import DEFAULT_HEALTH_ACCESS, enrich_access_document

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACCESS = ROOT / "data" / "access.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(ROOT.parent.parent)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access", type=Path, default=DEFAULT_ACCESS)
    parser.add_argument("--health-access", type=Path, default=DEFAULT_HEALTH_ACCESS)
    parser.add_argument("--out", type=Path, default=DEFAULT_ACCESS)
    args = parser.parse_args(argv)

    if not args.access.exists():
        raise SystemExit(f"Missing {args.access} - run uv run python -m scripts.build_access")
    if not args.health_access.exists():
        raise SystemExit(f"Missing {args.health_access} - build packages/health_access first")

    document = enrich_access_document(read_json(args.access), read_json(args.health_access))
    args.out.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = document["summary"]
    print(
        f"{summary['healthAccessRowsWithData']:,} transport UAT rows carry health data from "
        f"{summary['healthAccessView']}; "
        f"{summary['healthAccessLocalProviders']:,} eligible local providers on routed rows"
    )
    print(f"Wrote {display_path(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
