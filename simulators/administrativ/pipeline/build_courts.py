"""Which court each commune falls under, and therefore what a merger would span.

A merged unit whose members sit in two different judicial circumscriptions is a merger with a
problem nobody sees on the map: the administrative boundary and the judicial one stop
agreeing, and somebody has to move. That is a real argument for or against a particular
boundary, and it needs no modelling — the assignment is published.

Source: the justice simulator's `arondare-2023.json`, which is the Government's own list of
the localities in each judecătorie's circumscription. **Not** nearest-court-by-road, which
would have been a proxy: the legal circumscription is a fact, and the nearest court is a
guess that happens to be right most of the time.

Judecătorii, not tribunale. The sibling payload `court-distance.bin` measures distance to the
42 county tribunals, which are far too coarse for this — with one per county and no unit
allowed to cross a county line, no merger could ever span two. Judecătorii are the level where
a merger can actually straddle a boundary.

Output:
    web/public/data/courts.json     court names, and one court index per UAT
    data/processed/reports/courts.md

Usage:
    uv run python -m pipeline.build_courts
"""

from __future__ import annotations

import argparse
import json
import sys

from pipeline.build_geometry import Check, Report, write_report
from pipeline.paths import REPO_ROOT, REPORTS_DIR, WEB_DATA_DIR

# `REPO_ROOT` is the simulator root despite its name; the siblings are one level up.
JUSTICE = REPO_ROOT.parent / "justitie" / "data"

# A UAT the 2023 decision does not mention. Its own limitations name two communes created
# after it was adopted, so this is expected rather than a fault.
UNASSIGNED = -1


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    report = Report()

    source = JUSTICE / "arondare-2023.json"
    if not source.exists():
        raise SystemExit(f"Missing {source} — the justice simulator builds this")

    attributes_path = WEB_DATA_DIR / "attributes.json"
    if not attributes_path.exists():
        raise SystemExit(f"Missing {attributes_path}. Run: uv run python -m pipeline.export")
    attributes = json.loads(attributes_path.read_text(encoding="utf-8"))
    order = attributes["siruta"]
    index_of = {s: i for i, s in enumerate(order)}

    arondare = json.loads(source.read_text(encoding="utf-8"))
    courts = arondare["courts"]

    names = [c["name"] for c in courts]
    court_of = [UNASSIGNED] * len(order)
    claimed_twice: list[str] = []
    outside: set[str] = set()

    for c, court in enumerate(courts):
        for siruta in court.get("localities", []):
            i = index_of.get(str(siruta))
            if i is None:
                # The decision lists localities, and a locality is not always a UAT: villages
                # appear alongside communes. Only the UATs concern this map.
                outside.add(str(siruta))
                continue
            if court_of[i] != UNASSIGNED and court_of[i] != c:
                claimed_twice.append(f"{attributes['name'][i]}")
            court_of[i] = c

    assigned = sum(1 for c in court_of if c != UNASSIGNED)
    report.add(
        Check(
            "court_coverage",
            assigned > len(order) * 0.98,
            f"{assigned:,} of {len(order):,} UATs sit in a published circumscription; "
            f"{len(order) - assigned} do not, which the decision's own limitations explain "
            "for communes created after it was adopted",
            fatal=assigned <= len(order) * 0.95,
        )
    )
    report.add(
        Check(
            "no_double_assignment",
            not claimed_twice,
            "no UAT is claimed by two courts"
            if not claimed_twice
            else f"{len(claimed_twice)} UATs claimed by two courts: {claimed_twice[:5]}",
            fatal=bool(claimed_twice),
        )
    )
    report.add(
        Check(
            "localities_beyond_uats",
            True,
            f"{len(outside):,} listed localities are not UATs — the decision names villages "
            "as well as communes, and only the UATs are indexed here",
        )
    )
    report.add(Check("court_count", len(names) > 100, f"{len(names)} judecătorii"))

    out = WEB_DATA_DIR / "courts.json"
    out.write_text(
        json.dumps(
            {
                "period": arondare.get("period"),
                "source": arondare.get("title"),
                "publisher": arondare.get("publisher"),
                "courts": names,
                "courtOf": court_of,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    size_kb = out.stat().st_size / 1024
    report.add(Check("payload", size_kb < 256, f"courts.json is {size_kb:,.0f} KB"))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_report(report, REPORTS_DIR / "courts.md", REPORTS_DIR / "courts.json")
    print(f"\nWrote {out} ({size_kb:,.0f} KB)")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
