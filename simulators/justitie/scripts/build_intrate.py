"""Cases filed per court, which no published source states.

CSM's Anexa 1 prints two numbers for each court: `Volum` and `Cauze soluţionate`. In CSM's
methodology the first is the *volum de activitate* — the stock carried in from previous years
plus everything filed during it — so neither column is the count of new cases. That count is
what `incarcatura-noua.json` needs and does not have, and it is the one thing the case files
give directly: every dosar carries its registration date.

This began as an audit and stopped being one on inspection, which is worth recording because the
reasoning is the useful part. The plan was to count registrations per court from the portal and
set them against CSM's `Volum`, treating any excess as proof the published figure was too low —
the portal being a survival sample, its count can only ever be a floor, so an excess would have
been conclusive and a shortfall merely inconclusive. That test cannot fire. Filings are a
component of volum rather than a competing estimate of it, so the portal count sits below the
published one by construction and the comparison would confirm nothing.

What replaces it is smaller and honest. Filings per court are published here as a measurement in
their own right, and set beside CSM's volume as a ratio rather than a verdict: `intratePerVolum`
is a lower bound on how much of a court's year is new work rather than inherited backlog. The
level is a floor. The *shape* — which courts carry which share of the national total — is the
more robust half, because a survivorship factor that applies broadly cancels in a ratio of
shares, and `divergentaCota` is where a court whose filings and whose published volume disagree
about its size becomes visible.

The join is by name, and it lands 237 of CSM's 241 courts without help. The residue is not noise
and is reported rather than dropped: the Înalta Curte is not on the portal at all, three
tribunale were renamed between the two vocabularies, and four judecătorii exist on the portal but
not in the annex because they are the suspended ones.

Usage:
    uv run --with pyarrow --with pandas python scripts/build_intrate.py --input data/portal
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "intrate-portal.json"
CSM = ROOT / "data" / "instante-2025.json"

# Courts the two vocabularies name differently. Kept as a table rather than solved by fuzzy
# matching: three entries are cheaper to read than a similarity threshold, and a threshold that
# silently marries the wrong two courts is worse than a miss, which at least gets reported.
#
# The specialised tribunals were "Tribunalul Comercial X" and are "Tribunalul Specializat X" in
# the report; the portal enum still carries the old name.
ALIASES = {
    "TRIBUNALULSPECIALIZATARGES": "TRIBUNALULCOMERCIALARGES",
    "TRIBUNALULSPECIALIZATCLUJ": "TRIBUNALULCOMERCIALCLUJ",
    "TRIBUNALULSPECIALIZATMURES": "TRIBUNALULCOMERCIALMURES",
}

_DIACRITICS = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaissttAAISSTT")


def key(name: str) -> str:
    """Collapse a court name to a join key.

    "Judecătoria ADJUD" and the enum's "JudecatoriaADJUD" have to meet somewhere, so everything
    that differs between the two vocabularies goes: diacritics in both encodings, spaces, case.
    """
    folded = name.translate(_DIACRITICS)
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    collapsed = re.sub(r"[^A-Za-z0-9]", "", folded).upper()
    return ALIASES.get(collapsed, collapsed)


def compare(csm: dict, portal: dict) -> tuple[list, list, dict]:
    """Join the two vocabularies and derive the per-court and per-tier rows.

    Split out of `main` so it can be exercised without parquet: the arithmetic here is where a
    wrong answer would be invisible, and the file reading is where it would be obvious.

    `portal` must already carry a zero for every crawled court that filed nothing, because a
    court missing from this mapping is treated as a failed name match and reported as such.
    """
    # National totals over the matched set only. Dividing a matched court's filings by a national
    # total that included unmatched courts would make every share slightly too small, and the
    # error would land hardest on the tiers with the most unmatched courts.
    matched_keys = sorted(set(csm) & set(portal))
    portal_total = sum(portal[k] for k in matched_keys)
    csm_total = sum(csm[k]["volume"] for k in matched_keys)

    courts = []
    for k in matched_keys:
        record, count = csm[k], portal[k]
        share_portal = count / portal_total if portal_total else None
        share_csm = record["volume"] / csm_total if csm_total else None
        courts.append(
            {
                "name": record["name"],
                "tier": record["tier"],
                "intrate": count,
                "volumCsm": record["volume"],
                "solutionateCsm": record["resolved"],
                "intratePerVolum": round(count / record["volume"], 4) if record["volume"] else None,
                "cotaIntrate": round(share_portal, 6) if share_portal is not None else None,
                "cotaVolum": round(share_csm, 6) if share_csm is not None else None,
                # Positive: the court files a larger share of the national total than its share
                # of published volume. Negative: the other way. Zero would mean the two
                # vocabularies agree about how big this court is relative to the rest.
                "divergentaCota": (
                    round(share_portal - share_csm, 6)
                    if share_portal is not None and share_csm is not None
                    else None
                ),
            }
        )
    courts.sort(key=lambda row: -row["intrate"])

    tiers = []
    for tier in sorted({row["tier"] for row in courts}):
        rows = [row for row in courts if row["tier"] == tier]
        intrate = sum(row["intrate"] for row in rows)
        volum = sum(row["volumCsm"] for row in rows)
        tiers.append(
            {
                "tier": tier,
                "instante": len(rows),
                "intrate": intrate,
                "volumCsm": volum,
                "intratePerVolum": round(intrate / volum, 4) if volum else None,
            }
        )
    totals = {
        "pereche": len(matched_keys),
        "intrate": portal_total,
        "volum": csm_total,
    }
    return courts, tiers, totals


def main() -> int:
    import pandas as pd  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="directory of dosare-*.parquet")
    parser.add_argument("--year", type=int, default=2025, help="calendar year to compare")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    files = sorted(glob.glob(str(Path(args.input) / "dosare-*.parquet")))
    if not files:
        raise SystemExit(f"no dosare-*.parquet under {args.input}")
    dosare = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    dosare = dosare.drop_duplicates(subset=["institutie", "numar"], keep="last")
    dosare["registered"] = pd.to_datetime(dosare.data, errors="coerce")
    dosare = dosare.dropna(subset=["registered"])

    csm_document = json.loads(CSM.read_text(encoding="utf-8"))
    csm = {key(court["name"]): court for court in csm_document["courts"]}

    # Two different sets, and conflating them is a bug that reads as a data problem. `crawled` is
    # every court the crawl visited; `portal` is what each filed in the compared year. A court
    # that filed nothing is still crawled, and must join with a zero — otherwise it drops out
    # and is indistinguishable from a court whose name failed to match, which is how Tribunalul
    # Militar Timişoara first appeared in the unmatched list.
    # Read from the coverage report when one is present, because it lists every court the crawl
    # visited — including those that returned nothing, which the parquet cannot show. Falling
    # back to the parquet keeps the script usable on a bare directory of parts, at the cost of
    # under-reporting the crawled set by exactly the silent courts.
    coverage = sorted(Path(args.input).glob("coverage*.json"))
    crawled_names = set()
    for report in coverage:
        crawled_names |= set(json.loads(report.read_text(encoding="utf-8")).get("courts", {}))
    if not crawled_names:
        crawled_names = set(dosare.institutie.unique())
    crawled = {key(name) for name in crawled_names}
    filed = dosare[dosare.registered.dt.year == args.year]
    by_court = filed.groupby("institutie").size()
    counts = {key(name): int(count) for name, count in by_court.items()}
    portal = {name: counts.get(name, 0) for name in crawled}

    courts, tiers, totals = compare(csm, portal)

    unmatched_csm = sorted(set(csm) - set(portal))
    unmatched_portal = sorted(set(portal) - set(csm))
    document = {
        "$schema": "../schema/intrate-portal.schema.json",
        "id": "intrate-portal",
        "title": f"Cauze intrate pe instanță în {args.year}, măsurate din dosarele publicate",
        "publisher": "Ministerul Justiției — portal.just.ro (ECRIS), față de CSM Anexa 1",
        "period": str(args.year),
        "provenance": {
            "source": "portal-just-ro",
            "locator": (
                f"dosare înregistrate în {args.year}, numărate pe instanță din serviciul web "
                f"portalquery.just.ro; volumul comparat vine din instante-{args.year}.json"
            ),
            "confidence": "derived",
            "note": (
                "Volumul CSM este stoc plus intrate, deci nu este aceeași mărime cu numărul de "
                "cauze intrate. Raportul dintre ele este un prag de jos, nu o cotă."
            ),
        },
        "an": args.year,
        "acoperire": {
            "instanteCsm": len(csm),
            "instanteCrawlate": len(portal),
            "acoperireDinRaport": bool(coverage),
            "instantePereche": totals["pereche"],
            "intrateTotal": totals["intrate"],
            "volumCsmTotal": totals["volum"],
            "doarInCsm": [csm[k]["name"] for k in unmatched_csm],
            "doarInPortal": unmatched_portal,
        },
        "tiers": tiers,
        "courts": courts,
        "limitations": [
            {
                "id": "volumul-csm-nu-e-cauze-intrate",
                "text": (
                    "Coloana „Volum” din Anexa 1 este volumul de activitate — stocul rămas din "
                    "anii anteriori plus cauzele intrate în cursul anului. Cauzele intrate nu "
                    "sunt publicate separat. Raportul intrate/volum de aici nu este deci o "
                    "verificare a cifrei CSM, ci o măsură a cât din anul unei instanțe este "
                    "muncă nouă, și este un prag de jos."
                ),
                "severity": "blocking",
                "affects": ["intratePerVolum", "tiers"],
            },
            {
                "id": "intrarile-sunt-un-prag-de-jos",
                "text": (
                    "Portalul scoate dosarele pe măsură ce instanțele le arhivează, deci "
                    "cauzele intrate într-un an trecut și deja arhivate nu se mai văd. Numărul "
                    "de intrate este un prag de jos, cu atât mai depărtat de realitate cu cât "
                    "anul comparat e mai vechi."
                ),
                "severity": "blocking",
                "affects": ["intrate", "cotaIntrate", "intratePerVolum"],
            },
            {
                "id": "cotele-sunt-mai-robuste-decat-nivelurile",
                "text": (
                    "Dacă arhivarea scoate aproximativ aceeași proporție de dosare la toate "
                    "instanțele, factorul se simplifică într-un raport de cote, iar "
                    "`divergentaCota` rămâne interpretabilă chiar acolo unde nivelul nu este. "
                    "Presupunerea nu este verificată: o instanță care arhivează mai repede "
                    "decât altele va părea mai mică decât este."
                ),
                "severity": "material",
                "affects": ["cotaIntrate", "divergentaCota"],
            },
            {
                "id": "instantele-nepereche-sunt-raportate",
                "text": (
                    "Înalta Curte nu este pe portal. Cele patru judecătorii care apar doar pe "
                    "portal sunt cele suspendate, pe care anexa nu le cuprinde. Trei tribunale "
                    "specializate poartă în portal numele vechi, „comercial”, și sunt legate "
                    "printr-un tabel de trei intrări, nu prin potrivire aproximativă."
                ),
                "severity": "note",
                "affects": ["acoperire"],
            },
            {
                "id": "un-singur-an-si-aici",
                "text": (
                    "Comparația este pe un singur an, la fel ca la instante-2025. Volumul unei "
                    "instanțe variază de la an la an, iar o divergență într-un an nu este o "
                    "tendință."
                ),
                "severity": "material",
                "affects": ["courts", "tiers"],
            },
        ],
    }

    out = Path(args.out) if args.out else OUT
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"{totals['intrate']:,} cauze intrate in {args.year} across {totals['pereche']} matched "
        f"instante -> {out.name}"
    )
    for tier in tiers:
        print(
            f"  {tier['tier']:14} {tier['instante']:>4} instante  "
            f"{tier['intrate']:>9,} intrate  {tier['intratePerVolum']} of CSM volume"
        )
    if unmatched_csm:
        print(f"  unmatched in CSM: {', '.join(csm[k]['name'] for k in unmatched_csm)}")
    if unmatched_portal:
        print(f"  unmatched in portal: {', '.join(unmatched_portal)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
