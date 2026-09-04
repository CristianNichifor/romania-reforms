"""What building land is *asked* for, per locality — the measurement the grid never had.

`build_multiplu_piata.py` calibrates the notaries' floor against the market for extravilan
arable and states, in its own docstring, that it cannot do the same for curți-construcții: 68%
of this simulator's land value, on under 3% of its surface, and no source in the Legea 17/2014
register prices it. Every estimate of how far the grid sits below the market therefore rests on
farmland and is silently extrapolated to house plots, which is the weakest joint in the whole
argument.

Listing sites are the only broad source of asking prices for building land in Romania. This
reads one of them, slowly, through `politete.py`, and turns it into a per-locality statistic.

**Why Storia and not the larger portal.** imobiliare.ro's robots.txt disallows every search
parameter there is — `land-classification`, `lot-size`, `min-price`, `price-sqm`, `pagina`,
`location` — which is precisely the set of URLs that would enumerate land offers. Their search
is closed to crawlers by their own rules, and there is no reading of that file under which this
importer could be written. Storia's robots.txt disallows an internal endpoint, some ad slots
and the map view, and otherwise says `Allow: /`; it publishes a sitemap, which is a document
whose entire purpose is to be crawled. So the choice of source here is a consequence of what
the two sites asked for.

**The crawl is the sitemap, not a search.** `sitemap_locations_0.xml` enumerates 11 492
canonical result pages, 1 423 of them land-for-sale, and those are addresses Storia publishes
in order to have them fetched. Reduced to one page per county-and-town — the neighbourhood
pages beneath a town are a subset of it — that is about seven hundred requests, one every five
seconds, which is an overnight job and not a spike.

**One request per locality, not one per offer.** The pages are server-rendered and carry their
own data in `__NEXT_DATA__`, so a single fetch yields up to thirty-six offers with price, area
and price per square metre already in euro — the same unit the notaries' grid publishes. Going
on to fetch each offer would multiply the traffic by thirty for fields this does not use.

**What is written down is a statistic, not a copy.** Per locality: how many offers, the median
and quartiles of the asking price per square metre, the median parcel. No titles, no
descriptions, no photographs, no sellers, no offer identifiers. The distinction matters both
ways — a dataset of aggregate asking prices is a fair-dealing research output, and a mirror of
somebody's listings is not.

**Three things in the raw data will produce a wrong answer if taken at face value**, and each
is handled here rather than downstream:

* **Placeholder prices.** Offers priced at 17 or 20 EUR in total, coming out at 0,01 EUR/m²,
  are "price on request" wearing a number. Anything under `MIN_EUR_PER_M2` is dropped.
* **The same parcel, listed twice.** A promoted offer reappears in the organic results with a
  different id, so deduplication is on the parcel — price, area and title — and not on the id.
* **A median over three offers is not a price.** Localities below `MIN_OFFERS` are kept in the
  file with their count and without a median, so the thin ones are visible rather than
  silently averaged in with Cluj.

**And the ceiling on what this can prove.** These are asking prices, not transactions. The
Legea 17/2014 comparison already showed that asking and paid agree at the median for farmland
and disagree about the spread, which is a reason to expect the same here and no reason to
assume it. A listing is also selected: land worth advertising is not the average hectare.

Not wired into CI. It reads a third party's website; a build should not, and the pages are
cached under `sources/` — which is not committed, because that would be a mirror.

Usage:
    uv run python simulators/impozit-teren/scripts/import_anunturi_teren.py --budget 20
    uv run python simulators/impozit-teren/scripts/import_anunturi_teren.py --budget 800
    uv run python simulators/impozit-teren/scripts/import_anunturi_teren.py --county cj
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import politete  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = "https://www.storia.ro/sitemap_locations_0.xml"
BASE = "https://www.storia.ro/ro/rezultate/vanzare/teren/"

# Below this, a price per square metre is a placeholder rather than an offer. Two of the
# thirteen offers on the first page read during development were priced at 17 and 20 EUR for a
# whole parcel — "preț la cerere" with a number in the box so the form would submit.
MIN_EUR_PER_M2 = 1.0

# Under this many usable offers a median is one person's asking price. The locality is kept,
# with its count and a null median, so thinness is visible instead of averaged away.
MIN_OFFERS = 5

# Storia's own page size. Localities with more than this need paging; most have far fewer.
PER_PAGE = 36

# The slug each county appears under, against the two-letter code the rest of the project uses.
COUNTY_SLUG = {
    "alba": "AB", "arad": "AR", "arges": "AG", "bacau": "BC", "bihor": "BH",
    "bistrita-nasaud": "BN", "botosani": "BT", "braila": "BR", "brasov": "BV",
    "bucuresti": "B", "buzau": "BZ", "calarasi": "CL", "caras-severin": "CS", "cluj": "CJ",
    "constanta": "CT", "covasna": "CV", "dambovita": "DB", "dolj": "DJ", "galati": "GL",
    "giurgiu": "GR", "gorj": "GJ", "harghita": "HR", "hunedoara": "HD", "ialomita": "IL",
    "iasi": "IS", "ilfov": "IF", "maramures": "MM", "mehedinti": "MH", "mures": "MS",
    "neamt": "NT", "olt": "OT", "prahova": "PH", "salaj": "SJ", "satu-mare": "SM",
    "sibiu": "SB", "suceava": "SV", "teleorman": "TR", "timis": "TM", "tulcea": "TL",
    "valcea": "VL", "vaslui": "VS", "vrancea": "VN",
}


def fold(name: str) -> str:
    """A locality name reduced to what two sources can agree on: letters, no diacritics.

    The grid prints ALEȘD, the URL says `alesd`, and the listing says "Aleşd" with whichever
    cedilla its author's keyboard produced. Everything else in this repository joins on SIRUTA
    for exactly this reason; here there is no SIRUTA to join on until the name is matched, so
    the fold is the join and its failures are counted and reported.
    """
    decomposed = unicodedata.normalize("NFD", name.lower())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", stripped)


def localities() -> dict[str, dict[str, str]]:
    """Every county's localities from the built value datasets, keyed by folded name."""
    index: dict[str, dict[str, str]] = {}
    for path in sorted((ROOT / "data").glob("valoare-teren-*.json")):
        if "nationala" in path.name:
            continue
        county = re.search(r"valoare-teren-([a-z]{1,2})-", path.name).group(1).upper()
        document = json.loads(path.read_text(encoding="utf-8"))
        for locality in document["localities"]:
            index.setdefault(county, {})[fold(locality["name"])] = {
                "siruta": locality["siruta"],
                "name": locality["name"],
            }
    return index


def towns(sitemap: str) -> list[tuple[str, str, str]]:
    """(county slug, town slug, url), one per town, from the sitemap Storia publishes.

    Neighbourhood pages are folded into their town: a search for Oradea already contains
    Nufărul, so fetching both would double the traffic and double-count the offers.
    """
    found: dict[tuple[str, str], str] = {}
    for url in re.findall(r"(?<=<loc>)[^<]+", sitemap):
        if not url.startswith(BASE):
            continue
        parts = [p for p in url[len(BASE) :].split("/") if p]
        if len(parts) < 2:
            continue
        county, town = parts[0], parts[1]
        found.setdefault((county, town), f"{BASE}{county}/{town}")
    return sorted((county, town, url) for (county, town), url in found.items())


def offers(page: str) -> tuple[list[dict], int]:
    """The land offers embedded in one result page, and how many the page says there are.

    Read out of `__NEXT_DATA__` rather than out of the markup: the numbers are already typed
    and already in euro there, and a parse of the rendered HTML would break on a class rename.
    """
    found = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not found:
        return [], 0
    try:
        document = json.loads(found.group(1))
        ads = document["props"]["pageProps"]["data"]["searchAds"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return [], 0
    total = (ads.get("pagination") or {}).get("totalItems") or 0
    out = []
    for item in ads.get("items") or []:
        if item.get("estate") != "TERRAIN" or item.get("transaction") != "SELL":
            continue
        price = item.get("pricePerSquareMeter") or {}
        if price.get("currency") != "EUR" or not price.get("value"):
            continue
        out.append(
            {
                "eurPerM2": float(price["value"]),
                "areaM2": item.get("areaInSquareMeters"),
                "private": bool(item.get("isPrivateOwner")),
                # The parcel, for deduplication. Not stored in the output — a promoted offer
                # reappears organically under a different id, so the id cannot do this job.
                "key": (
                    round(float(price["value"]), 2),
                    item.get("areaInSquareMeters"),
                    (item.get("title") or "").strip().lower(),
                ),
            }
        )
    return out, total


def summarise(rows: list[dict]) -> dict:
    """Quartiles of the asking price per square metre, or nothing if there are too few."""
    unique = {row["key"]: row for row in rows}.values()
    usable = sorted(r["eurPerM2"] for r in unique if r["eurPerM2"] >= MIN_EUR_PER_M2)
    areas = sorted(r["areaM2"] for r in unique if r.get("areaM2"))
    private = [r["private"] for r in unique]
    summary = {
        "offers": len(unique),
        "usableOffers": len(usable),
        "droppedBelowFloor": len(unique) - len(usable),
        "askedEurPerM2": None,
        "medianAreaM2": round(statistics.median(areas)) if areas else None,
        "privateShare": round(sum(private) / len(private), 3) if private else None,
    }
    if len(usable) >= MIN_OFFERS:
        quartiles = statistics.quantiles(usable, n=4)
        summary["askedEurPerM2"] = {
            "p25": round(quartiles[0], 2),
            "median": round(statistics.median(usable), 2),
            "p75": round(quartiles[2], 2),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=20, help="live requests this run may make")
    parser.add_argument("--delay", type=float, default=politete.DEFAULT_DELAY)
    parser.add_argument("--county", help="one county slug, e.g. cluj")
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()

    fetcher = politete.Politete(
        cache=ROOT / "sources" / "storia", delay=args.delay, budget=args.budget
    )
    index = localities()

    sitemap = fetcher.get(SITEMAP)
    wanted = towns(sitemap)
    if args.county:
        wanted = [t for t in wanted if t[0] == args.county]
    print(f"{len(wanted)} town pages in the sitemap", file=sys.stderr)

    rows = []
    unmatched: list[str] = []
    truncated: list[str] = []
    stopped = None
    for county_slug, town_slug, url in wanted:
        county = COUNTY_SLUG.get(county_slug)
        if not county:
            continue
        known = index.get(county, {}).get(fold(town_slug))
        if not known:
            unmatched.append(f"{county_slug}/{town_slug}")
            continue
        try:
            page = fetcher.get(url)
        except politete.BudgetSpent as spent:
            stopped = str(spent)
            break
        except politete.Disallowed as no:
            stopped = str(no)
            break
        found, total = offers(page)
        if not found:
            continue
        # Paging is not walked. A locality with more offers than one page holds is recorded as
        # truncated rather than quietly summarised from its first thirty-six, because the first
        # page is sorted by relevance and is not a sample.
        if total > PER_PAGE:
            truncated.append(known["siruta"])
        summary = summarise(found)
        rows.append(
            {
                "siruta": known["siruta"],
                "name": known["name"],
                "county": county,
                "totalOffersReported": total,
                "truncated": total > PER_PAGE,
                **summary,
            }
        )
        print(
            f"  {county} {known['name']}: {summary['usableOffers']}/{summary['offers']} offers"
            + (
                f", median {summary['askedEurPerM2']['median']} EUR/m2"
                if summary["askedEurPerM2"]
                else ", too few for a median"
            ),
            file=sys.stderr,
        )

    priced = [r for r in rows if r["askedEurPerM2"]]
    medians = sorted(r["askedEurPerM2"]["median"] for r in priced)

    document = {
        "$schema": "../schema/anunturi-teren.schema.json",
        "id": f"anunturi-teren-{args.year}",
        "title": f"Prețul cerut pentru teren, pe localități, anunțuri {args.year}",
        "publisher": "storia.ro",
        "period": str(args.year),
        "currency": "EUR",
        "provenance": {
            "source": "storia-ro-rezultate-vanzare-teren",
            "locator": (
                f"{SITEMAP} → paginile {BASE}<județ>/<localitate>, datele din "
                "__NEXT_DATA__, props.pageProps.data.searchAds.items, câmpul "
                "pricePerSquareMeter"
            ),
            "confidence": "derived",
            "note": (
                "Prețurile sunt cele cerute în anunțuri, preluate în euro pe metru pătrat așa "
                "cum le publică site-ul. Cuartilele sunt calculate aici, pe anunțuri unice, "
                "după eliminarea celor sub pragul de preț. Nu se păstrează niciun anunț: "
                "fișierul conține statistici pe localitate, nu conținutul sursei."
            ),
        },
        "assumptions": {
            "minEurPerM2": MIN_EUR_PER_M2,
            "minOffers": MIN_OFFERS,
            "perPage": PER_PAGE,
            "delaySeconds": args.delay,
            "note": (
                "O pagină pe localitate, fără paginare: localitățile cu mai multe anunțuri "
                "decât încape într-o pagină sunt marcate „truncated”, pentru că prima pagină e "
                "sortată după relevanță și nu e un eșantion."
            ),
        },
        "summary": {
            "localities": len(rows),
            "localitiesWithMedian": len(priced),
            "truncatedLocalities": len(truncated),
            "unmatchedTownPages": len(unmatched),
            "medianOfMediansEurPerM2": round(statistics.median(medians), 2) if medians else None,
            "crawl": fetcher.report(),
            "stoppedBecause": stopped,
        },
        "localities": rows,
        "limitations": [
            {
                "id": "pret-cerut-nu-pret-platit",
                "severity": "blocking",
                "text": (
                    "Sunt prețuri cerute, nu prețuri plătite. Pe teren agricol, unde ambele se "
                    "cunosc, mediana cerută și mediana plătită ies aproape egale, dar "
                    "distribuțiile nu — deci acesta e un motiv de a le aștepta apropiate, nu de "
                    "a le presupune identice."
                ),
                "affects": ["anunturi-teren", "multiplu-piata"],
            },
            {
                "id": "anunturile-sunt-selectate",
                "severity": "blocking",
                "text": (
                    "Terenul care merită scos la vânzare pe un portal nu este hectarul mediu. "
                    "Anunțurile se concentrează în jurul orașelor mari și în comunele unde se "
                    "parcelează, adică exact acolo unde prețul crește cel mai repede, deci "
                    "mediana de aici este a pieței active, nu a fondului funciar."
                ),
                "affects": ["anunturi-teren"],
            },
            {
                "id": "o-singura-pagina",
                "severity": "material",
                "text": (
                    "Se citește o singură pagină de rezultate pe localitate. Localitățile cu "
                    "mai multe anunțuri decât încape sunt marcate „truncated”: pentru ele "
                    "mediana e calculată pe primele rezultate, sortate după relevanță, nu pe "
                    "toate. Sunt numărate în „summary”."
                ),
                "affects": ["anunturi-teren"],
            },
            {
                "id": "legatura-se-face-pe-nume",
                "severity": "material",
                "text": (
                    "Portalul nu publică SIRUTA, deci legătura cu restul proiectului se face pe "
                    "numele localității, redus la litere fără diacritice, în interiorul "
                    "județului. Paginile care nu s-au potrivit sunt numărate în „summary”; o "
                    "potrivire greșită între două localități cu același nume în județe diferite "
                    "nu este posibilă, dar între două omonime din același județ ar fi."
                ),
                "affects": ["anunturi-teren"],
            },
            {
                "id": "intravilan-si-extravilan-la-un-loc",
                "severity": "material",
                "text": (
                    "Anunțurile nu spun consecvent dacă terenul e intravilan sau extravilan, "
                    "deci mediana amestecă parcele de casă cu tarlale. Suprafața mediană, "
                    "publicată alături, e cel mai bun indiciu: o localitate cu mediana de sute "
                    "de metri pătrați vinde loturi de casă, una cu mii vinde teren agricol."
                ),
                "affects": ["anunturi-teren", "multiplu-piata"],
            },
            {
                "id": "o-singura-sursa",
                "severity": "note",
                "text": (
                    "Un singur portal. imobiliare.ro, cel mai mare, interzice prin robots.txt "
                    "exact parametrii de căutare care ar enumera terenurile, deci nu poate fi "
                    "citit; ce se vede aici este cota de piață a unui singur site, care "
                    "diferă de la județ la județ."
                ),
                "affects": ["anunturi-teren"],
            },
        ],
    }

    out = ROOT / "data" / f"anunturi-teren-{args.year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{fetcher.report()}")
    if stopped:
        print(f"stopped: {stopped}")
    print(
        f"{len(rows)} localități, {len(priced)} cu mediană, "
        f"{len(truncated)} trunchiate, {len(unmatched)} pagini nepotrivite"
    )
    if medians:
        print(f"mediana medianelor: {statistics.median(medians):.2f} EUR/m2")
    print(f"Wrote {out.relative_to(ROOT.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
