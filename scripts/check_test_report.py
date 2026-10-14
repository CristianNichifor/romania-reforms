"""Refuse missing, empty or skipped pytest JUnit evidence in required CI jobs."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main(paths: list[str]) -> int:
    if not paths:
        print("No test reports supplied", file=sys.stderr)
        return 1
    failed = False
    for name in paths:
        try:
            cases = list(ET.parse(Path(name)).iter("testcase"))
        except (OSError, ET.ParseError) as exc:
            print(f"{name}: missing or invalid test evidence: {exc}", file=sys.stderr)
            failed = True
            continue
        if not cases:
            print(f"{name}: no tests executed", file=sys.stderr)
            failed = True
        for case in cases:
            for status in ("skipped", "failure", "error"):
                result = case.find(status)
                if result is not None:
                    print(
                        f"{name}: {case.get('classname')}.{case.get('name')}: "
                        f"{status}: {result.get('message', '')}",
                        file=sys.stderr,
                    )
                    failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
