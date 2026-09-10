"""Build the compact public-enterprise compensation comparison used by salarizare.

The source is the documented companiidestat.ro aggregate API, attributed under CC BY 4.0.
The output contains only aggregate pay-scale statistics: no person rows, CUIs, authority
names or company-name lists enter the browser payload.

Usage:
    uv run python simulators/salarizare/scripts/build_amepip_compensation_comparison.py \
      --retrieved-date 2026-09-10
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Final

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DOCUMENT_ID: Final[str] = "amepip-public-enterprise-compensation"
SOURCE_ID: Final[str] = "companiidestat-api-data-v1"
SOURCE_URL: Final[str] = "https://companiidestat.ro/date/v1/data.json"
DEFAULT_OUT: Final[Path] = ROOT / f"data/fiscal/{DOCUMENT_ID}.json"
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"


def read_json(location: str | Path) -> dict[str, Any]:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(text).read_text(encoding="utf-8"))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] * (1 - (pos - lower)) + ordered[upper] * (pos - lower)


def row_value(rows: list[dict[str, Any]], label: str) -> float:
    row = next(item for item in rows if item.get("label") == label)
    return float(row["value"])


def provenance(locator: str, note: str | None = None) -> dict[str, str]:
    result = {"source": SOURCE_ID, "locator": locator, "confidence": "derived"}
    if note:
        result["note"] = note
    return result


def series_row(
    *,
    id_: str,
    label: str,
    unit: str,
    value: float,
    statistic: str,
    measure: str,
    note: str,
) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "geo": "RO",
        "unit": unit,
        "dims": {
            "kind": "public-enterprise-compensation",
            "scope": "companiidestat-pay-scale",
            "statistic": statistic,
            "measure": measure,
        },
        "observations": [{"period": "2025-08", "value": round(value, 2)}],
        "provenance": provenance("pay_scale_rows", note),
    }


def build_comparison_document(
    source: dict[str, Any],
    *,
    retrieved_date: str,
) -> dict[str, Any]:
    rows = source["pay_scale_rows"]
    tier_rows = [row for row in rows if row.get("kind") in {"tier", "tier-top"}]
    fixed_values = [float(row["value"]) for row in tier_rows]
    avg_gross = row_value(rows, "Salariu mediu brut 2025")
    president = row_value(rows, "Președintele României")
    minimum = row_value(rows, "Salariu minim brut")
    fixed_median = percentile(fixed_values, 0.5)
    fixed_top = max(fixed_values)
    extreme = max(float(row["value"]) for row in rows if row.get("kind") == "extreme")

    output_series = [
        series_row(
            id_="companiidestat-pay-scale-fixed-tier-count",
            label="Companii de stat: numar de trepte fixe publicate",
            unit="COUNT",
            value=len(fixed_values),
            statistic="count",
            measure="fixedTiers",
            note="Count of fixed monthly public-enterprise pay-scale tiers in the aggregate API row set.",
        ),
        series_row(
            id_="companiidestat-pay-scale-fixed-median",
            label="Companii de stat: mediana treptelor fixe publicate",
            unit="CP_MNAC",
            value=fixed_median,
            statistic="median",
            measure="fixedMonthlyGrossRon",
            note="Median over the aggregate fixed monthly tiers; no company/person rows are emitted.",
        ),
        series_row(
            id_="companiidestat-pay-scale-fixed-top",
            label="Companii de stat: varful treptelor fixe publicate",
            unit="CP_MNAC",
            value=fixed_top,
            statistic="max",
            measure="fixedMonthlyGrossRon",
            note="Highest fixed monthly tier from the aggregate API row set.",
        ),
        series_row(
            id_="companiidestat-pay-scale-extreme-monthly-equivalent",
            label="Companii de stat: varf cu bonus anual lunarizat",
            unit="CP_MNAC",
            value=extreme,
            statistic="max",
            measure="monthlyEquivalentWithAnnualBonusRon",
            note="Highest monthly equivalent once the annual bonus row is divided across 12 months by the source API.",
        ),
        series_row(
            id_="companiidestat-pay-scale-minimum-gross",
            label="Referinta: salariul minim brut",
            unit="CP_MNAC",
            value=minimum,
            statistic="reference",
            measure="minimumGrossMonthlyRon",
            note="Reference row carried by the source API.",
        ),
        series_row(
            id_="companiidestat-pay-scale-average-gross",
            label="Referinta: salariul mediu brut 2025",
            unit="CP_MNAC",
            value=avg_gross,
            statistic="reference",
            measure="averageGrossMonthlyRon",
            note="Reference row carried by the source API.",
        ),
        series_row(
            id_="companiidestat-pay-scale-president",
            label="Referinta: Presedintele Romaniei",
            unit="CP_MNAC",
            value=president,
            statistic="reference",
            measure="presidentMonthlyRon",
            note="Reference row carried by the source API.",
        ),
        series_row(
            id_="companiidestat-pay-scale-fixed-top-to-average-gross",
            label="Companii de stat: varful fix fata de salariul mediu brut",
            unit="RATE",
            value=fixed_top / avg_gross,
            statistic="ratio",
            measure="fixedTopToAverageGross",
            note="Derived from aggregate API pay-scale rows.",
        ),
        series_row(
            id_="companiidestat-pay-scale-extreme-to-average-gross",
            label="Companii de stat: varful cu bonus fata de salariul mediu brut",
            unit="RATE",
            value=extreme / avg_gross,
            statistic="ratio",
            measure="extremeToAverageGross",
            note="Derived from aggregate API pay-scale rows.",
        ),
        series_row(
            id_="companiidestat-pay-scale-fixed-top-to-president",
            label="Companii de stat: varful fix fata de indemnizatia presedintelui",
            unit="RATE",
            value=fixed_top / president,
            statistic="ratio",
            measure="fixedTopToPresident",
            note="Derived from aggregate API pay-scale rows.",
        ),
    ]

    return {
        "$schema": "../../schema/fiscal.schema.json",
        "id": DOCUMENT_ID,
        "title": "Companii de stat: scara agregata de compensatie manageriala",
        "publisher": "companiidestat.ro",
        "methodology": (
            "Aggregate pay-scale rows from the documented companiidestat.ro API, attributed "
            "under CC BY 4.0. The source integrates public AMEPIP salary rows and reference "
            "benchmarks, but this document emits only aggregate tiers and ratios."
        ),
        "retrieved": retrieved_date,
        "query": {"endpoint": SOURCE_URL, "field": "pay_scale_rows"},
        "provenance": provenance(
            SOURCE_URL,
            "Compact aggregate derived from companiidestat.ro/date/v1/data.json.",
        ),
        "series": output_series,
        "limitations": [
            {
                "id": "aggregate-only-no-nominal-rows",
                "severity": "material",
                "affects": ["browser-payload", "comparison"],
                "text": (
                    "This document intentionally emits only aggregate pay-scale statistics. "
                    "It omits CUI, authority, person and company-name lists from salarizare."
                ),
            },
            {
                "id": "companiidestat-derived-source",
                "severity": "note",
                "affects": ["provenance"],
                "text": (
                    "The source is the documented companiidestat.ro API under CC BY 4.0 "
                    "attribution, not a direct AMEPIP PDF import in this repository."
                ),
            },
            {
                "id": "governance-context-not-salary-grid",
                "severity": "material",
                "affects": ["comparison"],
                "text": (
                    "The pay-scale rows describe public-enterprise governance compensation "
                    "context. They are not salary-grid coefficients or public-sector payroll "
                    "entitlements."
                ),
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=SOURCE_URL, help="companiidestat data.json path or URL")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--retrieved-date", required=True)
    args = parser.parse_args()

    document = build_comparison_document(read_json(args.source), retrieved_date=args.retrieved_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} with {len(document['series'])} public-enterprise pay series")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
