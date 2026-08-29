"""Measure the Art. 21(2) ceiling where the law actually measures it.

    uv run python scripts/import_plafon.py

Writes data/fiscal/plafon-sporuri.json.

Art. 21 alin. (2) caps supplements at 20% of the base wage bill **per ordonator principal
de credite and per funding source** — not per person. The page has always said so, and has
always had to stop there, because the fiscal importer recorded that no open dataset
published personnel spending at that level. So the ceiling could be illustrated (add 20%
to a base salary and see what it looks like) but never evaluated: nobody could say which
institutions it would bind, or how many are already past it.

That level is published. transparenta.eu's `entityAnalytics` returns spending per
reporting entity, `report_type: PRINCIPAL_AGGREGATED` puts each subordinate institution
inside its principal — which is exactly the unit the law names — and `funding_source_ids`
splits by the second dimension the law names. Two filters, and the ceiling becomes a
measurement.

What is measured, precisely, because the difference matters:

  * The denominator is 10.01.01, "Salarii de baza". That is the law's denominator too.
  * The narrow numerator is 10.01.05 + 10.01.06, the two paragraphs the budget calls
    supplements. It is *not* the Art. 21 set: the statute lifts overtime, night work,
    disability, three-shift health work, Delta isolation, EU-fund administration and the
    performance premium out of the ceiling, and the accounting code does not know that.
  * The wide numerator is everything in 10.01 that is neither base salary nor a reimbursed
    expense — the whole layer above base pay, whatever it is called.

The narrow figure is the closest proxy for the ceiling. The wide one is the honest answer
to "how far above base salary is this institution actually paying". Both are published
here because reporting only one of them would be choosing an argument.
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/fiscal/plafon-sporuri.json"

API = "https://api.transparenta.eu/graphql"
UA = "public-pay-simulator/1.0 (+https://github.com/CristianNichifor/public-pay-simulator)"

YEAR = "2025"
CAP = 0.20

QUERY = """
query EntityAnalytics($filter: AnalyticsFilterInput!, $limit: Int, $offset: Int) {
  entityAnalytics(filter: $filter, limit: $limit, offset: $offset) {
    nodes { entity_cui entity_name entity_type county_code amount }
    pageInfo { totalCount hasNextPage }
  }
}
"""

FUNDING_SOURCES = {
    1: "Integral de la buget",
    2: "Credite externe",
    3: "Credite interne",
    4: "Fonduri externe nerambursabile",
    5: "Activități finanțate integral din venituri proprii",
    6: "Integral venituri proprii",
    7: "Venituri proprii și subvenții",
    8: "Buget aferent activității din privatizare",
    9: "Bugetul Fondului pentru Mediu",
    10: "Bugetul Trezoreriei Statului",
}

# Four cuts of the same title, joined per entity afterwards.
CUTS = {
    "base": {"economic_codes": ["10.01.01"]},
    "sporuri": {"economic_codes": ["10.01.05", "10.01.06"]},
    # Delegation, secondment and payments to people who are not employees: reimbursed
    # cost, not remuneration, so they belong in neither numerator.
    "nonpay": {"economic_codes": ["10.01.12", "10.01.13", "10.01.14"]},
    "all": {"economic_prefixes": ["10.01"]},
}

BANDS = [
    (0.0, 0.0, "fără sporuri raportate"),
    (0.0, 0.10, "sub 10%"),
    (0.10, CAP, "10–20%"),
    (CAP, 0.30, "20–30%"),
    (0.30, 0.50, "30–50%"),
    (0.50, float("inf"), "peste 50%"),
]


def fetch(cut: dict, source: int | None) -> list[dict]:
    filter_ = {
        "account_category": "ch",
        "report_type": "PRINCIPAL_AGGREGATED",
        "report_period": {"type": "YEAR", "selection": {"interval": {"start": YEAR, "end": YEAR}}},
        **cut,
    }
    if source is not None:
        filter_["funding_source_ids"] = [source]
    body = json.dumps({
        "query": QUERY,
        "variables": {"filter": filter_, "limit": 5000, "offset": 0},
    }).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json", "User-Agent": UA}
    )
    with urllib.request.urlopen(request, timeout=240) as response:  # noqa: S310
        document = json.loads(response.read().decode())
    if document.get("errors"):
        raise SystemExit(f"API refused the query: {json.dumps(document['errors'])[:500]}")
    payload = document["data"]["entityAnalytics"]
    if payload["pageInfo"]["hasNextPage"]:
        raise SystemExit("more entities than one page holds — add pagination before trusting this")
    return payload["nodes"]


def band_of(ratio: float) -> str:
    for low, high, label in BANDS:
        if low == high == 0.0:
            if ratio == 0.0:
                return label
            continue
        if low < ratio <= high or (low == 0.0 and 0.0 < ratio <= high):
            return label
    return BANDS[-1][2]


def main() -> None:
    print(f"reading per-ordonator execution for {YEAR}\n")

    # (cui, source) -> amounts. The law's unit of measurement, both dimensions.
    pairs: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    names: dict[str, str] = {}
    types: dict[str, str] = {}

    for source, source_label in FUNDING_SOURCES.items():
        found = 0
        for cut_name, cut in CUTS.items():
            for row in fetch(cut, source):
                cui = str(row["entity_cui"])
                names[cui] = row["entity_name"]
                types[cui] = row.get("entity_type") or ""
                pairs[(cui, source)][cut_name] += row["amount"]
                found += 1
        print(f"  sursa {source:2}  {source_label[:44]:46} {found:5,} rânduri")

    # Two ratios per pair: the ceiling's proxy, and the whole layer above base pay.
    records = []
    for (cui, source), amounts in pairs.items():
        base = amounts.get("base", 0.0)
        if base <= 0:
            continue  # No base wage bill means no denominator; the cap says nothing.
        layer = amounts.get("all", 0.0) - base - amounts.get("nonpay", 0.0)
        records.append({
            "cui": cui,
            "name": names[cui],
            "entityType": types.get(cui, ""),
            "source": source,
            "base": base,
            "sporuri": amounts.get("sporuri", 0.0),
            "narrow": amounts.get("sporuri", 0.0) / base,
            "wide": max(layer, 0.0) / base,
        })

    # The same thing with funding sources merged, which is *not* what the law says but is
    # what a reader assumes it says. Publishing both shows how much the second dimension
    # matters: a principal can sit under the cap overall and breach it on one source.
    by_entity: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        for key in ("base", "sporuri"):
            by_entity[r["cui"]][key] += r[key]
        by_entity[r["cui"]]["layer"] += r["wide"] * r["base"]

    entity_records = [
        {
            "cui": cui,
            "name": names[cui],
            "entityType": types.get(cui, ""),
            "base": v["base"],
            "narrow": v["sporuri"] / v["base"],
            "wide": v["layer"] / v["base"],
        }
        for cui, v in by_entity.items()
        if v["base"] > 0
    ]

    series: list[dict] = []

    def emit(id_: str, label: str, unit: str, dims: dict, value: float, locator: str) -> None:
        series.append({
            "id": id_, "label": label, "geo": "RO", "unit": unit, "dims": dims,
            "observations": [{"period": YEAR, "value": value}],
            "provenance": {
                "source": "transparenta-eu-executie",
                "locator": locator,
                "confidence": "derived",
            },
        })

    for scope, rows, unit_label in (
        ("pereche", records, "perechi ordonator × sursă"),
        ("ordonator", entity_records, "ordonatori principali"),
    ):
        for measure in ("narrow", "wide"):
            counts: dict[str, int] = defaultdict(int)
            for r in rows:
                counts[band_of(r[measure])] += 1
            for index, (low, _, label) in enumerate(BANDS):
                emit(
                    f"plafon-{scope}-{measure}-banda-{label.replace(' ', '-').replace('%', 'pct')}",
                    f"{unit_label} în banda {label} ({measure})",
                    "COUNT",
                    {
                        "kind": "band", "scope": scope, "measure": measure, "band": label,
                        # The order and the verdict travel with the data, so no reader has
                        # to re-derive them by parsing a human label.
                        "bandIndex": str(index),
                        "overCap": "true" if low >= CAP else "false",
                    },
                    counts.get(label, 0),
                    f"Numărul de {unit_label} cu raport sporuri/salarii de bază în banda {label}, {YEAR}",
                )

            over = [r for r in rows if r[measure] > CAP]
            total_base = sum(r["base"] for r in rows)
            emit(
                f"plafon-{scope}-{measure}-peste-plafon",
                f"{unit_label} peste plafonul de 20% ({measure})",
                "COUNT",
                {"kind": "overCap", "scope": scope, "measure": measure},
                len(over),
                f"Câte {unit_label} depășesc 20%, {YEAR}",
            )
            emit(
                f"plafon-{scope}-{measure}-pondere-masa",
                f"Din masa salarială de bază, partea aflată peste plafon ({measure})",
                "PC_TOT",
                {"kind": "overCapWeight", "scope": scope, "measure": measure},
                round(sum(r["base"] for r in over) / total_base, 5) if total_base else 0,
                f"Salariile de bază ale {unit_label} peste 20%, ÷ total, {YEAR}",
            )
            print(
                f"\n  {unit_label:26} {measure:6}  peste 20%: {len(over):5,} din {len(rows):5,}"
                f"   ({sum(r['base'] for r in over) / total_base * 100 if total_base else 0:5.1f}% din masa de bază)"
            )

    # The named ones, because a distribution without institutions in it cannot be argued
    # with. Largest by base wage bill, which is also who moves the national number.
    biggest = sorted(entity_records, key=lambda r: -r["base"])[:40]
    print("\n  cei mai mari ordonatori:")
    for r in biggest[:12]:
        print(
            f"    {r['base'] / 1e9:7.2f} mld  sporuri {r['narrow'] * 100:5.1f}%"
            f"  tot ce e peste bază {r['wide'] * 100:5.1f}%  {r['name'][:46]}"
        )
    for r in biggest:
        for measure in ("narrow", "wide"):
            emit(
                f"plafon-entitate-{r['cui']}-{measure}",
                f"{r['name']} — {measure}",
                "RATE",
                {
                    "kind": "entity", "cui": r["cui"], "name": r["name"],
                    "entityType": r["entityType"], "measure": measure,
                },
                round(r[measure], 5),
                f"{r['name']} (CUI {r['cui']}), sporuri ÷ salarii de bază, {YEAR}",
            )
        emit(
            f"plafon-entitate-{r['cui']}-baza",
            f"{r['name']} — masa salarială de bază",
            "CP_MNAC",
            {"kind": "entityBase", "cui": r["cui"], "name": r["name"]},
            round(r["base"], 2),
            f"{r['name']} (CUI {r['cui']}), 10.01.01, {YEAR}",
        )

    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "plafon-sporuri",
        "title": "Plafonul de 20% măsurat acolo unde îl măsoară legea: pe ordonator principal și pe sursă de finanțare",
        "publisher": "Ministerul Finanțelor (execuții bugetare), agregat de transparenta.eu",
        "methodology": (
            "Execuția pe entitate raportoare, agregată la nivel de ordonator principal de "
            "credite și defalcată pe sursă de finanțare. Numitor: 10.01.01. Numărător "
            "strict: 10.01.05 + 10.01.06. Numărător larg: tot titlul 10.01 minus salariul "
            "de bază și minus decontările (10.01.12–14)."
        ),
        "retrieved": YEAR,
        "query": {
            "endpoint": API, "field": "entityAnalytics",
            "reportType": "PRINCIPAL_AGGREGATED", "accountCategory": "ch",
            "year": YEAR, "fundingSources": list(FUNDING_SOURCES),
        },
        "provenance": {
            "source": "transparenta-eu-executie",
            "locator": "transparenta.eu GraphQL, entityAnalytics",
            "confidence": "derived",
        },
        "series": series,
        "limitations": [
            {
                "id": "codul-contabil-nu-e-multimea-din-art-21",
                "text": (
                    "10.01.05 și 10.01.06 sunt paragrafele pe care contabilitatea le "
                    "numește sporuri; nu sunt mulțimea pe care Art. 21 o plafonează. "
                    "Legea scoate din plafon munca de noapte, orele suplimentare, sporul "
                    "de handicap, turele din sănătate, izolarea în Deltă, administrarea "
                    "fondurilor europene și premiul de performanță — iar clasificația "
                    "economică nu știe asta. Cifra strictă e cea mai bună aproximare "
                    "publicată, nu plafonul însuși."
                ),
                "affects": ["structure", "gross"],
                "severity": "material",
            },
            {
                "id": "regimul-actual-nu-proiectul",
                "text": (
                    "Execuția arată ce s-a plătit sub legea în vigoare. Plafonul de 20% "
                    "aparține proiectului și nu s-a aplicat încă niciun an. Cifrele spun "
                    "pe cine ar prinde plafonul dacă lucrurile rămân cum sunt, nu ce s-a "
                    "întâmplat sub el."
                ),
                "affects": ["structure"],
                "severity": "material",
            },
            {
                "id": "sporuri-raportate-la-alt-paragraf",
                "text": (
                    "Un ordonator care nu raportează nimic la 10.01.05 sau 10.01.06 apare "
                    "cu zero sporuri, deși poate plăti drepturi similare la 10.01.30 "
                    "„Alte drepturi salariale în bani”. De aceea se publică și raportul "
                    "larg, care ia tot ce nu e salariu de bază: acolo nu se poate ascunde "
                    "nimic prin alegerea paragrafului."
                ),
                "affects": ["structure"],
                "severity": "material",
            },
            {
                "id": "doua-dimensiuni-nu-una",
                "text": (
                    "Plafonul se măsoară pe ordonator principal ȘI pe sursă de finanțare. "
                    "Un ordonator poate sta sub 20% pe total și să depășească pe una "
                    "dintre surse. De aceea se publică ambele numărători: pe perechi "
                    "ordonator × sursă, cum spune legea, și pe ordonator cu sursele "
                    "însumate, cum se citește de obicei."
                ),
                "affects": ["structure"],
                "severity": "note",
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(series)} series")


if __name__ == "__main__":
    main()
