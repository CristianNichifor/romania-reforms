"""Freeze one administrative-consolidation scenario as this simulator's hub assignment.

The design document gives the transport engine a single input interface — `hubOf`, a map from
every UAT to the centre that serves it — and two providers for it. This is the **frozen** one:
administrativ's model is run once, at stated parameters, and its answer is written to a file.

Why frozen first. Under this provider transport can be built, tested and disputed without
administrativ running at all, and the hub assignment becomes a file a critic can open. The
**live** provider — administrativ's TypeScript model in the worker beside this one, so moving
the radius slider moves the bus fleet — is the same interface with a different source, and it
waits until the transport engine is proven.

**The parameters are recorded in the output, not assumed by the reader.** A hub assignment is
only meaningful next to the scenario that produced it, and this simulator's whole argument is
that a consolidation which saves administration adds travel. Quoting one without the other
would be the same error as quoting a cost without its standard.

Output:
    data/hubs.json      uat -> hub, plus the parameters and what they produced

Usage:
    uv run python -m scripts.export_hubs
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "hubs.json"

# The administrative simulator's own defaults, named here rather than inherited silently: a
# default that shifts upstream would otherwise change every route in this simulator without
# appearing in any diff. `scripts/export_hubs.py` records what it actually ran with, and the
# test compares the two.
SCENARIO: dict[str, int] = {
    "x": 7_500,
    "r_national_m": 15_000,
    "r_cap_m": 10_000,
    "r_town_m": 10_000,
    "n_min": 5,
    "p_target": 50_000,
}


def summarise(region_of: dict[str, str], county: dict[str, str]) -> dict:
    """Shape of the assignment, so a reader sees what they are standing on."""
    sizes = collections.Counter(region_of.values())
    counts = sorted(sizes.values())
    per_county = collections.Counter(county[hub] for hub in sizes)
    return {
        "uats": len(region_of),
        "hubs": len(sizes),
        "reductionPct": round((1 - len(sizes) / len(region_of)) * 100, 1),
        "membersMin": counts[0],
        "membersMedian": counts[len(counts) // 2],
        "membersMax": counts[-1],
        "singletonHubs": sum(1 for n in counts if n == 1),
        "counties": len(per_county),
        "hubsPerCountyMin": min(per_county.values()),
        "hubsPerCountyMax": max(per_county.values()),
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    sys.path.insert(0, str(ADMINISTRATIV))
    from pipeline.reference_model import Params, load_data, run  # noqa: PLC0415

    data = load_data()
    result, info = run(data, Params(**SCENARIO))
    region_of = dict(sorted(result.region_of.items()))

    summary = summarise(region_of, data.county)
    document = {
        "$schema": "../schema/hubs.schema.json",
        "id": "hubs",
        "title": "Centrele care deservesc fiecare UAT, într-un scenariu de comasare",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "administrativ-reference-model",
            "locator": (
                "simulators/administrativ pipeline.reference_model.run, la parametrii "
                "înregistrați în acest document"
            ),
            "confidence": "derived",
            "note": (
                "Un scenariu, nu o propunere. Alți parametri dau alte centre, deci alte "
                "trasee și alte costuri; parametrii sunt păstrați aici tocmai pentru ca "
                "cifrele să nu poată fi citate fără scenariul care le-a produs."
            ),
        },
        "scenario": SCENARIO,
        "summary": summary,
        # Reported by administrativ, carried across so the ledger has both columns in one
        # place: consolidation is argued as an administrative saving, and this simulator
        # exists to price what it costs in travel.
        "savingsRon": {
            "administrative": round(info["savings_admin_ron"]),
            "operating": round(info["savings_operating_ron"]),
        },
        "hubOf": region_of,
        "limitations": [
            {
                "id": "un-singur-scenariu",
                "text": (
                    "Este înghețat un singur scenariu. Cifrele de transport care rezultă "
                    "descriu această hartă, nu comasarea în general; alți parametri mută "
                    "centrele și odată cu ele fiecare traseu."
                ),
                "severity": "material",
                "affects": ["network", "cost", "access"],
            },
            {
                "id": "economiile-sunt-ale-administrativ",
                "text": (
                    "Economiile administrative și de funcționare sunt calculate de "
                    "simulatorul administrativ și preluate ca atare, cu limitările lui."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"{summary['uats']:,} UATs -> {summary['hubs']:,} hubs "
        f"({summary['reductionPct']}% fewer centres)"
    )
    print(
        f"  members per hub: min {summary['membersMin']}, median "
        f"{summary['membersMedian']}, max {summary['membersMax']}"
    )
    print(
        f"  hubs per county: {summary['hubsPerCountyMin']}-{summary['hubsPerCountyMax']} "
        f"across {summary['counties']}"
    )
    print(
        f"  savings claimed upstream: {document['savingsRon']['administrative']:,} RON "
        f"administrative, {document['savingsRon']['operating']:,} RON operating"
    )
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
