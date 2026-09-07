"""Local-council votes per UAT, from the 2020 local elections.

The map can say what merging costs in town halls and councillors. What it cannot yet say is
what it costs in *representation*: whether the lists people actually voted for still hold
seats once their commune is pooled into a larger unit. That is the objection small communes
raise, and it is arithmetic rather than opinion — but only with real votes behind it.

Source: AEP's own open-data release on data.gov.ro, polling-station level, aggregated here to
one row per UAT and competitor. Keyed on `uat_siruta`, which is the same SIRUTA everything
else in this pipeline is indexed on, so the join is free.

**Why 2020 and not 2024.** The 2024 local elections are the current mandate, and they are not
published as open data: they live on a JavaScript-and-reCAPTCHA site, or in community mirrors
whose provenance is not something this project can cite. 2020 is AEP's own release under a
licence, and the counterfactual is structural — how pooling redistributes seats — so being
able to name the source matters more than the mandate being current. The payload says which
mandate it is and the panel repeats it.

**A limitation the data cannot resolve.** Legea 115/2015 raises the threshold for electoral
alliances: 7% for two parties, 8% for three or more, against 5% for one. The CSV names a
competitor but never says how many parties stood inside it, and the name will not tell you —
"ALIANȚA USR PLUS" is two, "ALIANȚA PNL-USR-PLUS" is three, and neither is inferrable in
general. Every list is therefore treated as a single party at 5%. That admits a few alliances
the law would exclude, so the count of lists losing their seats to a merger is if anything an
*under*-estimate. Said here rather than discovered later.

Output:
    web/public/data/votes.json      parties, and per-UAT (party index, votes)
    data/processed/reports/votes.md

Usage:
    uv run python -m pipeline.build_votes --csv path/to/bd_sectii.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd

from pipeline.build_geometry import Check, Report, normalise_siruta, write_report
from pipeline.paths import PROCESSED_DIR, REPORTS_DIR, WEB_DATA_DIR

# The election type this reads. The file carries five: P and PG (mayor, and the general mayor
# of Bucharest), CL (local councillor), CJ (county councillor), PCJ (county council
# president) and CGMB (Bucharest's general council). Only CL elects the body a merger changes.
LOCAL_COUNCIL = "CL"

# Fields, from the file's own header.
COL_TYPE = "Tip"
COL_SIRUTA = "uat_siruta"
COL_COMPETITOR = "Competitor"
COL_VOTES = "VVE"

# A competitor polling fewer than this nationally is dropped from the interned list and its
# votes folded into the UAT's total under a single "other" entry.
#
# Not a threshold on the election: every vote still counts towards the coefficient. It keeps
# the payload from carrying several thousand independents who stood in one commune each, which
# is most of the file's distinct names and none of its meaning.
MIN_NATIONAL_VOTES = 500

# Where those folded votes go. Index 0 by construction, so the browser can test for it.
OTHER_LABEL = "Alți competitori"

# SIRUTA codes that changed between the vintage this project is indexed on and the one AEP
# published the 2020 results under.
#
# One commune, and the evidence is unambiguous: Baneasa in Constanta is 61069 here and 63171
# in the results, while the other two Baneasas — Galati 75686 and Giurgiu 101001 — carry the
# same code on both sides, and each county has exactly one. A code changes when a commune's
# rank does, which is the failure mode the README warns about and the reason this is written
# out rather than absorbed by a fuzzy name match.
SIRUTA_CROSSWALK: dict[str, str] = {
    "63171": "61069",  # BANEASA, Constanta
}


def normalise_one(value: str) -> str:
    """Scalar twin of `normalise_siruta`, for a loop that runs 160,000 times.

    The pipeline's version takes a pandas Series, and building one per row turned a
    thirty-second job into one that did not finish. `main` asserts the two agree over every
    SIRUTA in the payload before using this, so the shortcut cannot drift from the definition
    the rest of the pipeline joins on.
    """
    text = value.strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.lstrip("0") or "0"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="AEP polling-station CSV for the 2020 locals")
    ap.add_argument("--mandate", default="2020-2024", help="which mandate the votes elected")
    args = ap.parse_args(argv)

    source = Path(args.csv)
    if not source.exists():
        raise SystemExit(f"Missing {source}")

    uat_path = PROCESSED_DIR / "uat_geometry.gpkg"
    if not uat_path.exists():
        raise SystemExit(f"Missing {uat_path}. Run: uv run python -m pipeline.build_geometry")
    uats = gpd.read_file(uat_path, layer="uat").sort_values("siruta", ignore_index=True)
    order = list(uats["siruta"])
    index_of = {s: i for i, s in enumerate(order)}

    report = Report()

    # The shortcut above must mean exactly what the pipeline's own normaliser means, or the
    # join silently loses rows. Checked against every code in the payload, not sampled.
    vectorised = list(normalise_siruta(gpd.pd.Series(order)))
    drift = [(a, b) for a, b in zip(order, vectorised, strict=True) if normalise_one(a) != b]
    report.add(
        Check(
            "siruta_normalisation_agrees",
            not drift,
            f"scalar and vectorised SIRUTA normalisation agree on all {len(order):,} codes"
            + (f"; first disagreement {drift[0]}" if drift else ""),
            fatal=bool(drift),
        )
    )
    if drift:
        raise SystemExit(f"normalisation disagrees, e.g. {drift[0]}")

    # Pass one: national totals per competitor, so the interning threshold can be applied
    # before anything is written.
    national: dict[str, int] = defaultdict(int)
    per_uat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    rows = 0
    unmatched: set[str] = set()

    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if row.get(COL_TYPE) != LOCAL_COUNCIL:
                continue
            raw = (row.get(COL_SIRUTA) or "").strip()
            if not raw:
                continue
            siruta = normalise_one(raw)
            siruta = SIRUTA_CROSSWALK.get(siruta, siruta)
            if siruta not in index_of:
                unmatched.add(siruta)
                continue
            try:
                votes = int(row.get(COL_VOTES) or 0)
            except ValueError:
                continue
            competitor = (row.get(COL_COMPETITOR) or "").strip()
            if not competitor or votes <= 0:
                continue
            national[competitor] += votes
            per_uat[siruta][competitor] += votes
            rows += 1

    print(f"read {rows:,} CL rows across {len(per_uat):,} UATs, {len(national):,} competitors")

    kept = sorted(n for n, v in national.items() if v >= MIN_NATIONAL_VOTES)
    parties = [OTHER_LABEL, *kept]
    party_index = {name: i for i, name in enumerate(parties)}

    # Per UAT: parallel arrays of party index and votes, in the canonical UAT order. A UAT with
    # no CL result — Bucharest's sectors elect a different body — gets empty arrays rather than
    # being omitted, so the browser can index straight in.
    party_of: list[list[int]] = [[] for _ in order]
    votes_of: list[list[int]] = [[] for _ in order]
    for siruta, tally in per_uat.items():
        i = index_of[siruta]
        folded = 0
        pairs: list[tuple[int, int]] = []
        for competitor, votes in tally.items():
            idx = party_index.get(competitor)
            if idx is None:
                folded += votes
            else:
                pairs.append((idx, votes))
        if folded:
            pairs.append((0, folded))
        pairs.sort(key=lambda p: (-p[1], p[0]))
        party_of[i] = [p for p, _ in pairs]
        votes_of[i] = [v for _, v in pairs]

    covered = sum(1 for p in party_of if p)
    report.add(
        Check(
            "votes_coverage",
            covered > len(order) * 0.95,
            f"{covered:,} of {len(order):,} UATs carry a local-council result "
            f"({len(order) - covered} without, mostly Bucharest sectors which elect a "
            "different body)",
            fatal=covered <= len(order) * 0.90,
        )
    )
    report.add(
        Check(
            "votes_unmatched_siruta",
            not unmatched,
            f"{len(unmatched)} SIRUTA codes in the results matched no UAT"
            + (f": {sorted(unmatched)[:5]}" if unmatched else ""),
            fatal=len(unmatched) > 20,
        )
    )
    report.add(
        Check(
            "party_interning",
            True,
            f"{len(parties):,} competitors kept at {MIN_NATIONAL_VOTES}+ national votes; "
            f"{len(national) - len(kept):,} folded into '{OTHER_LABEL}'",
        )
    )

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = WEB_DATA_DIR / "votes.json"
    out.write_text(
        json.dumps(
            {
                "mandate": args.mandate,
                "source": "AEP, alegeri locale 2020, via data.gov.ro",
                "parties": parties,
                "partyOf": party_of,
                "votesOf": votes_of,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    size_kb = out.stat().st_size / 1024
    report.add(Check("votes_payload", size_kb < 2048, f"votes.json is {size_kb:,.0f} KB"))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_report(report, REPORTS_DIR / "votes.md", REPORTS_DIR / "votes.json")
    print(f"\nWrote {out} ({size_kb:,.0f} KB)")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
