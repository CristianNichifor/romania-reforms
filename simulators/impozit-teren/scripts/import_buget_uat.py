"""What each commune raises and what it spends, from its own budget execution.

This is the other half of a question the simulator could pose but not answer: **which
communes could pay for themselves?**

The land value is already known per locality — that is what the rest of this directory
computes — and a land value tax at a chosen rate turns it into a yearly revenue for each of
3 181 localities. What was missing was the denominator. A revenue figure means nothing
until it is held against what the place actually costs to run, and that number is filed,
per authority, every year.

transparenta.eu serves those filings, and its entity records carry `siruta_code` — the same
key the notary grids, the land register and the boundary polygons are joined on. So the two
halves can be put in one sentence without inventing a mapping.

**Own revenue, and why it is separated from the rest.** A commune's budget is mostly not
its own money: shares of income tax (04), sums broken out of VAT (11), subsidies (42, 43)
and European projects (45, 48) arrive from above. What is left — local taxes, fees, rents,
asset sales — is what the place raises itself. The split matters because "could this commune
pay for itself" is asked against the whole bill, while "how much would a land tax change
what it raises" is asked against the part it controls. Both are reported.

**The classification prefixes are a decision, not a fact.** Which chapters count as
transfers is written down here, in one list, rather than being spread through the arithmetic.
A reader who disagrees can move a chapter and re-run.

**One filing per authority.** `PRINCIPAL_AGGREGATED` reports each ordonator principal once
rather than the authority plus every school and hospital under it repeating the same money.
Without it a commune with a large hospital appears to spend it twice.

Usage:
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py
    uv run python simulators/impozit-teren/scripts/import_buget_uat.py --year 2024
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retea  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.transparenta.eu/graphql"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
YEAR = 2025

# Revenue that arrives from above rather than being raised locally. Chapter prefixes of the
# revenue classification: shares of income tax, sums broken out of VAT, subsidies from other
# budgets, and European money. Everything else is treated as the commune's own.
TRANSFER_PREFIXES = ("04.", "11.", "42.", "43.", "44.", "45.", "46.", "48.")

# How many UATs are asked for in one HTTP request. The endpoint has no group-by, so each
# commune needs its own filter; GraphQL aliases let forty of them share a request, which
# turns 3 228 round trips into 81.
BATCH = 40

ROSTER = """
query Roster($limit: Int!, $offset: Int!) {
  entities(limit: $limit, offset: $offset, filter: {is_uat: true}) {
    nodes {
      name
      uat_id
      uat { siruta_code county_code population }
    }
    pageInfo { totalCount hasNextPage }
  }
}
"""


def post(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json", "User-Agent": UA}
    )
    document = json.loads(retea.read(request, timeout=180))
    if document.get("errors"):
        raise SystemExit(f"transparenta.eu: {document['errors'][0]['message']}")
    return document["data"]


def roster() -> list[dict]:
    """Every reporting UAT, with the SIRUTA code that joins it to the rest of the data."""
    out: list[dict] = []
    offset = 0
    while True:
        # Advanced by what came back, never by what was asked for. The endpoint silently
        # caps a page at 100: asking for 200 and stepping 200 returns half the country
        # with `hasNextPage` still true, and the roster looks complete because every page
        # was full. It cost one silent half-import to find.
        page = post(ROSTER, {"limit": 100, "offset": offset})["entities"]
        received = len(page["nodes"])
        if received == 0:
            break
        for node in page["nodes"]:
            uat = node.get("uat") or {}
            if not uat.get("siruta_code"):
                continue
            out.append(
                {
                    "uatId": node["uat_id"],
                    "siruta": str(uat["siruta_code"]),
                    "county": uat.get("county_code"),
                    "name": node["name"],
                    "population": uat.get("population"),
                }
            )
        offset += received
        if not page["pageInfo"]["hasNextPage"]:
            break
        print(f"  roster: {len(out)} of {page['pageInfo']['totalCount']}", file=sys.stderr)
    return out


def batch_query(uat_ids: list[str], category: str, year: int, offset: int = 0) -> str:
    """One request, forty communes, one alias each.

    The ids are checked against `\\d+` before they are pasted into the document. They come
    from the same API, so this is not a defence against an attacker — it is a defence
    against a malformed id silently turning into a syntactically valid query that answers a
    different question.
    """
    parts = []
    for uat in uat_ids:
        if not re.fullmatch(r"\d+", uat):
            raise SystemExit(f"uat id is not a number: {uat!r}")
        parts.append(
            f'  u{uat}: aggregatedLineItems(filter: {{account_category: {category}, '
            f"report_type: PRINCIPAL_AGGREGATED, uat_ids: [\"{uat}\"], "
            f'report_period: {{type: YEAR, selection: {{interval: {{start: "{year}", '
            f'end: "{year}"}}}}}}}}, limit: 400, offset: {int(offset)}) '
            "{ nodes { functional_code amount } pageInfo { hasNextPage } }"
        )
    return "query Batch {\n" + "\n".join(parts) + "\n}"


def totals(rows: list[dict]) -> tuple[float, float]:
    """(everything, the part raised locally), in lei."""
    total = 0.0
    own = 0.0
    for row in rows:
        code = row["functional_code"] or ""
        amount = row["amount"] or 0.0
        total += amount
        if not code.startswith(TRANSFER_PREFIXES):
            own += amount
    return total, own


def all_rows(uat_id: str, category: str, year: int) -> list[dict]:
    """Every line for one authority, paged.

    Only the few that need it: a commune files two dozen revenue lines and a Bucharest
    sector files 423. The batch asks for 400 and this finishes whoever overflows, rather
    than the whole country paying for the exceptions.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        page = post(batch_query([uat_id], category, year, offset=offset))[f"u{uat_id}"]
        rows.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"] or not page["nodes"]:
            return rows
        offset += len(page["nodes"])


def fetch(uats: list[dict], category: str, year: int) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for start in range(0, len(uats), BATCH):
        chunk = uats[start : start + BATCH]
        data = post(batch_query([u["uatId"] for u in chunk], category, year))
        for uat in chunk:
            found = data.get(f"u{uat['uatId']}")
            if not found:
                continue
            nodes = found["nodes"]
            if found["pageInfo"]["hasNextPage"]:
                nodes = all_rows(uat["uatId"], category, year)
                print(f"  {uat['siruta']}: {len(nodes)} linii, paginat", file=sys.stderr)
            out[uat["siruta"]] = totals(nodes)
        print(
            f"  {category}: {min(start + BATCH, len(uats))} of {len(uats)}",
            file=sys.stderr,
        )
    return out


# How far above the country's own median spending per inhabitant a filing may sit before it
# is treated as a filing rather than a budget. Twenty is not a round number chosen to catch
# a known culprit: the gap in the data is wide and empty, with the worst three at 72×, 191×
# and 391× the median and the next authority at 10×.
SUSPECT_MULTIPLE = 20


def quarantine(rows: list[dict]) -> list[dict]:
    """Set aside the filings that cannot be budgets, measured against the data's own middle.

    Three of Bucharest's sectors report sums that are not municipal spending — Sector 1
    files 441 mld lei against 225 000 inhabitants, close to a tenth of Romania's GDP for
    one sector, and its lines repeat the same classification code hundreds of times. The
    same figures come back from the API's own county aggregation, so this is the source and
    not the query. Left in, they would be 80% of "what Romanian communes spend" and every
    per-capita or self-financing figure computed from the national total would be wrong.

    The test is a ratio against the median rather than a list of names, because naming the
    three would quietly pass the fourth when it appears. What is excluded is named in the
    file's limitations either way, so the exclusion is visible rather than tidy.
    """
    per_capita = [
        (r["spendingRon"] / r["population"], r)
        for r in rows
        if (r.get("population") or 0) > 0 and r["spendingRon"] > 0
    ]
    if not per_capita:
        return []
    ordered = sorted(value for value, _ in per_capita)
    median = ordered[len(ordered) // 2]
    suspects = []
    for value, row in per_capita:
        if value <= SUSPECT_MULTIPLE * median:
            continue
        row["suspect"] = True
        suspects.append(
            {
                "siruta": row["siruta"],
                "name": row["name"],
                "reportedSpendingRon": row["spendingRon"],
                "perInhabitantRon": round(value, 2),
                "timesMedian": round(value / median, 1),
            }
        )
    return sorted(suspects, key=lambda s: -s["timesMedian"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=YEAR)
    args = parser.parse_args()

    uats = roster()
    if len(uats) < 3000:
        raise SystemExit(f"only {len(uats)} UATs came back; refusing to write a partial roster")

    revenue = fetch(uats, "vn", args.year)
    spending = fetch(uats, "ch", args.year)

    rows = []
    for uat in sorted(uats, key=lambda u: u["siruta"]):
        total_revenue, own_revenue = revenue.get(uat["siruta"], (0.0, 0.0))
        total_spend, _ = spending.get(uat["siruta"], (0.0, 0.0))
        if total_revenue == 0 and total_spend == 0:
            continue
        rows.append(
            {
                "siruta": uat["siruta"],
                # County councils file under their county's letter code rather than a SIRUTA
                # number. They are kept — a county council's spending is local spending, and
                # dropping it would understate the total by a tenth — but they are labelled,
                # because the map joins on numeric SIRUTA and would never match them anyway.
                "level": "county" if not uat["siruta"].isdigit() else "uat",
                "name": uat["name"],
                "county": uat["county"],
                "population": uat["population"],
                "revenueRon": round(total_revenue, 2),
                "ownRevenueRon": round(own_revenue, 2),
                "spendingRon": round(total_spend, 2),
                # The share of its own budget the place raises itself. The number the
                # self-financing question is really about, before any tax is changed.
                "ownShare": round(own_revenue / total_revenue, 4) if total_revenue else None,
            }
        )

    suspects = quarantine(rows)
    rows = [r for r in rows if not r.get("suspect")]
    reporting = len(rows)
    with_own = [r for r in rows if r["ownShare"] is not None]
    median_own = sorted(r["ownShare"] for r in with_own)[len(with_own) // 2] if with_own else None

    document = {
        "$schema": "../schema/buget-uat.schema.json",
        "id": f"buget-uat-{args.year}",
        "title": f"Veniturile și cheltuielile fiecărei UAT, execuție {args.year}",
        "publisher": "transparenta.eu",
        "period": str(args.year),
        "currency": "RON",
        "provenance": {
            "source": "transparenta-eu-graphql",
            "locator": (
                f"{API}, aggregatedLineItems, account_category vn și ch, "
                f"report_type PRINCIPAL_AGGREGATED, anul {args.year}, pe uat_ids"
            ),
            "confidence": "verbatim",
            "note": (
                "Sumele sunt execuția bugetară raportată de fiecare ordonator principal, "
                "preluate ca atare. Împărțirea în venituri proprii și transferuri este a "
                "acestui import, după capitolele din clasificația veniturilor."
            ),
        },
        "assumptions": {
            "transferPrefixes": list(TRANSFER_PREFIXES),
            "suspectMultipleOfMedian": SUSPECT_MULTIPLE,
        },
        # Kept in the file rather than dropped silently. An exclusion nobody can see is a
        # number nobody can check.
        "excluded": suspects,
        "summary": {
            "uatsReporting": reporting,
            "revenueRon": round(sum(r["revenueRon"] for r in rows), 2),
            "ownRevenueRon": round(sum(r["ownRevenueRon"] for r in rows), 2),
            "spendingRon": round(sum(r["spendingRon"] for r in rows), 2),
            "medianOwnShare": median_own,
        },
        "uats": rows,
        "limitations": [
            {
                "id": "venituri-proprii-dupa-capitol",
                "severity": "material",
                "text": (
                    "Ce se numește „venit propriu” este o alegere făcută aici, pe capitole de "
                    "clasificație: cotele defalcate din impozitul pe venit, sumele defalcate din "
                    "TVA, subvențiile și banii europeni sunt scoase, restul rămâne. Un cititor "
                    "care mută un capitol schimbă cifra — de aceea lista e publicată în fișier."
                ),
            },
            {
                "id": "consiliile-judetene-in-total",
                "severity": "note",
                "text": (
                    "Consiliile județene depun fără cod SIRUTA, sub codul de județ, și sunt "
                    "păstrate în total cu „level”: „county”. Cheltuiala lor este tot "
                    "cheltuială locală; harta, care se leagă pe SIRUTA numeric, nu le atinge."
                ),
            },
            {
                "id": "executie-nu-buget",
                "severity": "note",
                "text": (
                    "Este execuția, adică ce s-a încasat și s-a plătit efectiv, nu bugetul "
                    "aprobat. Un an cu o investiție mare arată o cheltuială mare care nu se "
                    "repetă."
                ),
            },
            {
                "id": "raportari-imposibile-scoase",
                "severity": "blocking",
                "text": (
                    "Trei sectoare ale Bucureștiului raportează sume care nu pot fi cheltuieli "
                    "de primărie — Sectorul 1 depune 441 de miliarde de lei la 225 000 de "
                    "locuitori, de 391 de ori mediana pe cap de locuitor a țării, cu aceleași "
                    "coduri de clasificație repetate de sute de ori. Aceleași cifre vin și din "
                    "agregarea pe județ a API-ului, deci problema e în sursă, nu în întrebare. "
                    "Sunt scoase din total și numite în „excluded”, fiindcă altfel ar fi 80% "
                    "din ce cheltuiesc primăriile din România."
                ),
            },
            {
                "id": "sectoarele-bucurestiului",
                "severity": "note",
                "text": (
                    "Bucureștiul raportează separat pe sectoare și pe municipiu. Restul sumelor "
                    "sunt lăsate așa cum sunt depuse, fiecare cu SIRUTA lui."
                ),
            },
        ],
    }

    out = ROOT / "data" / f"buget-uat-{args.year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{reporting} UAT-uri, {document['summary']['spendingRon'] / 1e9:.2f} mld lei cheltuiți")
    if median_own is not None:
        print(f"mediana veniturilor proprii: {median_own * 100:.1f}% din buget")
    print(f"Wrote {out.relative_to(ROOT.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
