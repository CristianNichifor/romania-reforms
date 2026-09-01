"""Try every reader against every study, and report which chambers already work.

Writing a reader for a chamber is the expensive part of this simulator, so before writing
another one it is worth knowing which chambers the existing two already handle. That question
used to cost thirty seconds of PDF parsing per attempt and so was never asked; against the
cache it costs about half a second, so it can be asked of the whole country at once.

The answer is a coverage figure per county — how many of the localities the INS register lists
for it come back priced — which is the same measure the importer gates on. A chamber at 95%
needs a nudge; a chamber at 4% needs a reader of its own; and the difference is worth knowing
before choosing what to write next.

Nothing is written. This only reports.

Usage:
    uv run python simulators/impozit-teren/scripts/probe_readers.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dialect_alba  # noqa: E402
import dialect_generic  # noqa: E402
import dialect_iasi  # noqa: E402
from extract_cache import CACHE, load  # noqa: E402
from import_ghid import (  # noqa: E402
    key_of,
    keys_of,
    parse_villages,
    parse_zoned,
    register_roster,
    resolve,
)

ROOT = Path(__file__).resolve().parents[1]


def roster_for(county: str) -> dict[str, list[str]] | None:
    try:
        return register_roster(county)
    except SystemExit:
        return None


def coverage(roster: dict[str, list[str]], priced: set[str]) -> float:
    expected = [n for names in roster.values() for n in names]
    if not expected:
        return 0.0
    found = sum(1 for name in expected if resolve(key_of(name), {p: None for p in priced}))
    return found / len(expected)


def try_text(name: str, roster: dict[str, list[str]]) -> float:
    known = {key: n for names in roster.values() for n in names for key in keys_of(n)}
    rank_of = {key: r for r, names in roster.items() for n in names for key in keys_of(n)}
    pages = [page["text"] for page in load(name)["pages"]]
    try:
        communes, _ = parse_villages(pages, known, rank_of)
        zoned = parse_zoned(pages, known)
    except Exception:  # noqa: BLE001
        return 0.0
    return coverage(roster, {key_of(x["name"]) for x in [*communes, *zoned]})


def plausible(zoned: list[dict], communes: list[dict], roster: dict) -> tuple[float, float]:
    """Two numbers that say whether the prices are right, not merely present.

    Satu Mare taught this: a reader matched 93,8% of the county's names and priced the county
    seat at 10 €/m². Coverage was perfect and the values were a twentieth of reality, because
    the reader had locked onto some other table. So every candidate is now judged on what it
    says land costs, not only on how many places it found.

    Returned as the dearest building-land price anywhere in the county — a county seat is not
    priced like a garden — and the ratio of town prices to commune prices, which inverts when
    a reader has grabbed the wrong table.
    """
    towns = {key_of(n) for n in roster["municipii"] + roster["orase"]}

    def prices(entry: dict) -> list[float]:
        found = []
        for zone in entry.get("intravilan", {}).get("CC", {}).values():
            if zone:
                found.append(zone)
        for village in entry.get("villages", []):
            value = village.get("intravilan", {}).get("CC")
            if value:
                found.append(value)
        return found

    urban, rural = [], []
    for entry in [*zoned, *communes]:
        target = urban if key_of(entry["name"]) in towns else rural
        target.extend(prices(entry))
    top = max([*urban, *rural], default=0.0)
    ratio = (
        (sum(urban) / len(urban)) / (sum(rural) / len(rural))
        if urban and rural and sum(rural)
        else 0.0
    )
    return top, ratio


def try_module(module, name: str, roster: dict[str, list[str]]) -> float:
    """Coverage a reader reaches on one study, measured the way the importer gates on it."""
    local = {key for n in [x for names in roster.values() for x in names] for key in keys_of(n)}

    def is_local(text: str) -> bool:
        return resolve(key_of(text), {k: None for k in local}) is not None

    try:
        zoned, communes, _ = module.parse(name, is_local)
    except Exception:  # noqa: BLE001
        return 0.0
    share = coverage(roster, {key_of(x["name"]) for x in [*communes, *zoned]})
    LAST[:] = list(plausible(zoned, communes, roster))
    return share


LAST: list[float] = [0.0, 0.0]


def try_tables(name: str, roster: dict[str, list[str]]) -> float:
    local = {key for n in [x for names in roster.values() for x in names] for key in keys_of(n)}

    def is_local(text: str) -> bool:
        return resolve(key_of(text), {k: None for k in local}) is not None

    try:
        zoned, communes, _ = dialect_alba.parse(name, is_local)
    except Exception:  # noqa: BLE001
        return 0.0
    return coverage(roster, {key_of(x["name"]) for x in [*communes, *zoned]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=float, default=0.0, help="only show at or above this")
    args = parser.parse_args()

    manifest = json.loads(
        (ROOT / "sources" / "studies-2026.json").read_text(encoding="utf-8")
    )
    rows = []
    for study in manifest["studies"]:
        if not (CACHE / f"{study['file']}.json.gz").exists():
            continue
        for county in study["counties"]:
            roster = roster_for(county)
            if not roster:
                continue
            text = try_text(study["file"], roster)
            tables = try_tables(study["file"], roster)
            generic = try_module(dialect_generic, study["file"], roster)
            tiers = try_module(dialect_iasi, study["file"], roster)
            best = max(text, tables, generic, tiers)
            if best < args.min:
                continue
            rows.append(
                {
                    "county": county,
                    "chamber": study["chamber"],
                    "file": study["file"],
                    "text": round(text, 3),
                    "tables": round(tables, 3),
                    "generic": round(generic, 3),
                    "tiers": round(tiers, 3),
                    "best": round(best, 3),
                    "reader": max(
                        (("text", text), ("alba", tables), ("generic", generic), ("iasi", tiers)),
                        key=lambda x: x[1],
                    )[0],
                }
            )

    # Best study per county: several files can name the same county and only one prices it.
    best_by_county: dict[str, dict] = {}
    for row in rows:
        current = best_by_county.get(row["county"])
        if current is None or row["best"] > current["best"]:
            best_by_county[row["county"]] = row

    print(f"{'county':<8}{'reader':<9}{'text':<7}{'alba':<7}{'generic':<9}{'iasi':<7}{'best':<7}file")
    for county in sorted(best_by_county):
        row = best_by_county[county]
        print(
            f"{county:<8}{row['reader']:<9}{row['text']:<7}{row['tables']:<7}"
            f"{row['generic']:<9}{row['tiers']:<7}{row['best']:<7}{row['file'][:40]}"
        )

    usable = [c for c, r in best_by_county.items() if r["best"] >= 0.9]
    partial = [c for c, r in best_by_county.items() if 0.3 <= r["best"] < 0.9]
    print(f"\nready now (>=90%): {len(usable)} counties {sorted(usable)}")
    print(f"close (30-90%):    {len(partial)} counties {sorted(partial)}")
    print(f"needs a new reader: {len(best_by_county) - len(usable) - len(partial)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
