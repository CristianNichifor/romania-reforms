"""Every court's own figures, in a shape that can be added back up.

`portal-stats.json` answers "how does the system work" for the whole country and by tier. The
question it cannot answer is "how does it work *here*" — which court, which county, which of the
42 courts the reform would leave standing. That needs the same statistics per court, and the
naive way to publish them is to write out the same summary 240 times.

**That does not work, and the reason is the whole design of this file.** A median is not
additive. Two courts whose median case runs 120 days do not make a county whose median case runs
120 days, and there is no weighting that fixes it — the median of a union is not a function of
the medians of its parts. Percentiles per court would let a reader read one court and nothing
else: no county, no appeal circumscription, and above all no proposed court, since a proposed
court is a set of existing ones that has never had a statistic of its own.

So nothing here is a percentile. Every field is either a count or a histogram, and both add.
Ask for Timiș and the browser sums fifteen courts bin by bin and takes the quantile from the
sum, which is the quantile of the pooled distribution rather than an average of quantiles.

Three consequences worth stating plainly, because they are the cost:

  * **Quantiles come back quantised.** The interval histogram is exact to the day up to a week
    and to a fortnight beyond three months, so a median interval reads 28 days rather than 27.
    The bin edges are published in the file; a reader can see the grain.
  * **Durations become a life table rather than Kaplan-Meier.** Per court and per bin the file
    carries how many cases were resolved and how many were still running, which is exactly what
    the actuarial estimator consumes. It agrees with Kaplan-Meier to the width of a bin and
    disagrees more where many cases are censored inside one bin — so the bins are narrow early,
    where the events are, and widen later, where they are not.
  * **A court that matched no published name still gets its numbers**, with a null county. It is
    reported rather than dropped: four judecătorii exist on the portal and not in the CSM annex
    because they are suspended, and silently losing them would make every county share slightly
    wrong in a way nothing would show.

The join to a county runs through `instante-localizate-2025.json`, whose names come from the CSM
annex, by the same folded key `build_intrate.py` uses. That is deliberate reuse: two spellings of
"Judecătoria ADJUD" have to meet in exactly one place, and a second normaliser would be a second
set of near-misses.

Usage:
    uv run --with pyarrow --with pandas python scripts/build_portal_instante.py --input data/portal
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_intrate import key  # noqa: E402
from build_portal_stats import (  # noqa: E402
    AGE_BUCKETS,
    fetch_release,
    hearing_court,
    level_of,
    load,
    normalise_solutie,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "portal-instante.json"
LOCATED = ROOT / "data" / "instante-localizate-2025.json"
MANIFEST = ROOT.parent / "administrativ" / "web" / "public" / "data" / "manifest.json"

# Bin edges, in days. The last bin of each is open-ended: a case that took longer than the last
# edge lands in it, and no upper bound is invented for a tail nobody measured.
#
# Both are fine where the mass is and coarse where it is not. Half of all intervals between two
# hearings fall under a month, so the first month is resolved to the day for a week and to the
# week after that; a fortnight's grain past three months costs nothing a reader would notice.
TERMEN_BINS = (0, 1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 28, 35, 42, 56, 70, 84, 112, 140, 182, 273, 365)

# Duration is weekly for three months and four-weekly to a year. The cohort is twelve months, so
# nothing can be observed past 365 days and an edge beyond that would be an empty promise.
DURATA_BINS = (
    0, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84,
    98, 112, 140, 168, 196, 224, 252, 280, 308, 336, 364,
)  # fmt: skip


# Below this ratio of portal cases to CSM's published annual volume, a court is treated as not
# measured rather than as quiet.
#
# The threshold is not a judgement call, because the distribution is bimodal with nothing in the
# middle. A court crawled properly holds between one and two and a quarter years of CSM volume —
# the snapshot spans three and a half years and the portal is a survival sample, so a ratio above
# one is what a working crawl looks like. The tenth percentile is 0,008 and the twenty-fifth is
# 1,259: two orders of magnitude of empty space, and every court below it turned out to belong to
# one of two shards that returned 2.825 rows where their siblings returned 470.000.
#
# Publishing those courts unflagged would state that Judecătoria Oltenița heard 69 cases in three
# and a half years. The number is real — it is what the crawl returned — and it is not a fact
# about the court.
TRUNCATED_BELOW = 0.25


def histogram(values, edges: tuple[int, ...]) -> list[int]:
    """Counts per bin, last bin open-ended. Values below the first edge are dropped."""
    counts = [0] * len(edges)
    for value in values:
        index = bisect.bisect_right(edges, value) - 1
        if index >= 0:
            counts[index] += 1
    return counts


def bin_index(series, edges: tuple[int, ...]):
    """Vectorised `histogram`: the bin each value falls in, as a column.

    Two hundred and forty per-court `histogram` calls over eleven million rows is a minute of
    Python; one `searchsorted` and a groupby is a second. Same edges, same answer — the scalar
    version stays because it is what the tests read.
    """
    import numpy as np  # noqa: PLC0415

    return np.searchsorted(np.asarray(edges), series.to_numpy(), side="right") - 1


def counts_by_court(frame, court_column: str, bins_column: str, width: int) -> dict[str, list[int]]:
    """A histogram per court, from a frame already carrying a court and a bin index."""
    grouped = frame.groupby([court_column, bins_column]).size()
    out: dict[str, list[int]] = {}
    for (court, index), value in grouped.items():
        if index < 0:
            continue
        row = out.setdefault(str(court), [0] * width)
        row[int(index)] = int(value)
    return out


def located_counties() -> tuple[dict[str, dict], list[str]]:
    """County, seat and published volume per court, keyed as `build_intrate` joins on."""
    document = json.loads(LOCATED.read_text(encoding="utf-8"))
    table: dict[str, dict] = {}
    for court in document["courts"]:
        table[key(court["name"])] = {
            "nume": court["name"],
            "judet": court.get("county"),
            "siruta": court.get("siruta"),
            "punct": court.get("point"),
            "volum": court.get("volume"),
        }
    return table, [court["name"] for court in document["courts"]]


def build(dosare, sedinte, cohort_months: int, crawled_at: str) -> dict:
    import pandas as pd  # noqa: PLC0415

    dosare = dosare.copy()
    dosare["level"] = dosare.institutie.map(level_of)
    dosare["registered"] = pd.to_datetime(dosare.data, errors="coerce")
    now = pd.Timestamp(crawled_at)
    cohort_start = now - pd.DateOffset(months=cohort_months)

    sedinte = sedinte.copy()
    sedinte["when"] = pd.to_datetime(sedinte.data, errors="coerce")
    sedinte = sedinte.dropna(subset=["when"])

    # Which court a hearing belongs to. Shared with the national builder rather than reimplemented
    # here, and the reason is the number in its docstring: 11,2% of visible cases sit at more than
    # one court, so a case-number-to-court map assigns a tenth of the country's hearings to
    # whichever court happened to be last in the file. `hearing_court` assigns by date instead —
    # the court that had the file the day the hearing was held. Every hearing then belongs to
    # exactly one court, which is what lets these figures be added up.
    hearings_carry_court = "institutie" in sedinte.columns
    sedinte = sedinte.assign(court=hearing_court(dosare, sedinte))
    sedinte = sedinte.dropna(subset=["court"])

    # ---- panels and sections, per court -----------------------------------------------------
    panels = (
        sedinte.assign(complet=sedinte.complet.replace("", pd.NA))
        .dropna(subset=["complet"])
        .groupby("court")
        .complet.nunique()
    )
    sections = (
        dosare.assign(departament=dosare.departament.replace("", pd.NA))
        .dropna(subset=["departament"])
        .groupby("institutie")
        .departament.nunique()
    )
    stock = dosare.groupby("institutie").size()
    penal_stock = dosare[dosare.is_penal].groupby("institutie").size()

    # ---- case types, per court --------------------------------------------------------------
    by_type = dosare.groupby(
        ["institutie", dosare.categorie_caz.replace("", "necunoscut")]
    ).size()
    types_per_court: dict[str, dict[str, int]] = {}
    for (court, categorie), value in by_type.items():
        types_per_court.setdefault(str(court), {})[str(categorie)] = int(value)

    # ---- adjournments, per court ------------------------------------------------------------
    # The three acts stay apart for the same reason as in the national file: only the first is an
    # adjournment in the sense a workload argument means, and a court that defers many judgments
    # is a court that is hearing cases.
    with_disposition = sedinte[sedinte.solutie.replace("", pd.NA).notna()].copy()
    normalised = with_disposition.solutie.map(normalise_solutie)
    with_disposition["deferred"] = normalised.str.contains(
        r"am[âaă]n[ăa]?\s+pronun", regex=True, na=False
    )
    with_disposition["rescheduled"] = normalised.str.contains(r"preschimb", regex=True, na=False)
    with_disposition["adjourned"] = (
        normalised.str.contains(r"am[âaă]n", regex=True, na=False) & ~with_disposition.deferred
    )
    adjournments = with_disposition.groupby("court")[
        ["adjourned", "deferred", "rescheduled"]
    ].sum()
    dispositions_total = with_disposition.groupby("court").size()

    # ---- intervals between hearings, per court ----------------------------------------------
    cohort = set(dosare[dosare.registered >= cohort_start].numar)
    in_cohort = sedinte[sedinte.dosar_numar.isin(cohort)].sort_values(["dosar_numar", "when"])
    gaps = in_cohort.groupby("dosar_numar").when.diff().dt.days
    intervals = in_cohort.assign(zile=gaps).dropna(subset=["zile"])
    intervals = intervals[intervals.zile >= 0]
    intervals = intervals.assign(bin=bin_index(intervals.zile, TERMEN_BINS))
    interval_hist = counts_by_court(intervals, "court", "bin", len(TERMEN_BINS))

    # ---- resolution, per court --------------------------------------------------------------
    # Same definition as the national file, and for the same two reasons: a pronouncement dated
    # after the crawl is a schedule rather than a delivery, and one dated before registration
    # belongs to the stage below. Filtering on a non-negative duration alone would drop exactly
    # the cases that moved between courts.
    sedinte["pronuntat"] = pd.to_datetime(sedinte.data_pronuntare, errors="coerce")
    delivered = sedinte.dropna(subset=["pronuntat"]).copy()
    delivered["inregistrat"] = pd.to_datetime(
        delivered.dosar_numar.map(dosare.set_index("numar").registered.to_dict()), errors="coerce"
    )
    delivered = delivered[
        (delivered.pronuntat <= now) & (delivered.pronuntat >= delivered.inregistrat)
    ]
    resolved_at = delivered.groupby("dosar_numar").pronuntat.max()

    lifecycle = dosare[["numar", "institutie", "registered"]].copy()
    lifecycle["resolved"] = pd.to_datetime(
        lifecycle.numar.map(resolved_at.to_dict()), errors="coerce"
    )
    lifecycle["observed"] = lifecycle.resolved.notna()
    lifecycle["zile"] = (lifecycle.resolved.fillna(now) - lifecycle.registered).dt.days
    lifecycle = lifecycle[lifecycle.zile >= 0]

    fresh = lifecycle[lifecycle.registered >= cohort_start].copy()
    fresh["bin"] = bin_index(fresh.zile, DURATA_BINS)
    events = counts_by_court(fresh[fresh.observed], "institutie", "bin", len(DURATA_BINS))
    censored = counts_by_court(fresh[~fresh.observed], "institutie", "bin", len(DURATA_BINS))
    cohort_size = fresh.groupby("institutie").size()
    follow_up = fresh.groupby("institutie").zile.max()

    # ---- wait to the first hearing, per court -----------------------------------------------
    first_hearing = sedinte.groupby("dosar_numar").when.min()
    wait = fresh.assign(
        first=pd.to_datetime(fresh.numar.map(first_hearing.to_dict()), errors="coerce")
    ).dropna(subset=["first"])
    wait = wait.assign(zile=(wait["first"] - wait.registered).dt.days)
    wait = wait[wait.zile >= 0]
    wait = wait.assign(bin=bin_index(wait.zile, TERMEN_BINS))
    wait_hist = counts_by_court(wait, "institutie", "bin", len(TERMEN_BINS))

    # ---- aging of what is pending, per court ------------------------------------------------
    decided = set(sedinte[sedinte.solutie.replace("", pd.NA).notna()].dosar_numar)
    pending = dosare[~dosare.numar.isin(decided)].copy()
    pending["age"] = (now - pending.registered).dt.days
    edges = tuple(low for low, _ in AGE_BUCKETS)
    pending = pending.assign(bin=bin_index(pending.age, edges))
    aging_hist = counts_by_court(pending, "institutie", "bin", len(edges))

    # ---- assembly ---------------------------------------------------------------------------
    located, _ = located_counties()
    zero_termene = [0] * len(TERMEN_BINS)
    zero_durata = [0] * len(DURATA_BINS)
    zero_aging = [0] * len(AGE_BUCKETS)

    courts = []
    unmatched = []
    unmeasured: list[str] = []
    for institutie in sorted(stock.index, key=lambda name: -int(stock[name])):
        place = located.get(key(str(institutie)))
        if place is None:
            unmatched.append(str(institutie))
        panels_here = int(panels.get(institutie, 0))
        adjourned_here = adjournments.loc[institutie] if institutie in adjournments.index else None
        volume = (place or {}).get("volum")
        ratio = round(int(stock[institutie]) / volume, 4) if volume else None
        truncated = ratio is not None and ratio < TRUNCATED_BELOW
        if truncated:
            unmeasured.append(str(institutie))
        courts.append(
            {
                "institutie": str(institutie),
                "nume": place["nume"] if place else None,
                "level": level_of(str(institutie)),
                "judet": place["judet"] if place else None,
                "siruta": place["siruta"] if place else None,
                "acoperire": {
                    "volumCsm": volume,
                    "raportFataDeVolum": ratio,
                    # True means the crawl did not finish this court, so every figure in this row
                    # is a fragment. Kept rather than blanked: the row still has to exist, or a
                    # county total would silently be a sum over fewer courts than it names.
                    "trunchiat": truncated,
                },
                "dosare": int(stock[institutie]),
                "dosarePenale": int(penal_stock.get(institutie, 0)),
                "sectii": int(sections.get(institutie, 0)),
                "completuri": panels_here,
                "peCategorie": types_per_court.get(str(institutie), {}),
                "amanari": {
                    "termeneCuSolutie": int(dispositions_total.get(institutie, 0)),
                    "amanareCauza": int(adjourned_here.adjourned) if adjourned_here is not None else 0,
                    "amanarePronuntare": int(adjourned_here.deferred) if adjourned_here is not None else 0,
                    "termenPreschimbat": int(adjourned_here.rescheduled) if adjourned_here is not None else 0,
                },
                "peRol": aging_hist.get(str(institutie), zero_aging),
                "primulTermen": wait_hist.get(str(institutie), zero_termene),
                "intervalTermene": interval_hist.get(str(institutie), zero_termene),
                "durata": {
                    "dosare": int(cohort_size.get(institutie, 0)),
                    # `urmarireZile` is the longest a case in this court's cohort has been
                    # watched. The survival curve must not be drawn past it — that is where a
                    # resolution share stops being a measurement and becomes a projection.
                    "urmarireZile": int(follow_up.get(institutie, 0) or 0),
                    "evenimente": events.get(str(institutie), zero_durata),
                    "cenzurate": censored.get(str(institutie), zero_durata),
                },
            }
        )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        "snapshot": {
            "crawledAt": crawled_at,
            "instante": len(courts),
            "dosare": int(len(dosare)),
            "institutieDinFisier": bool(hearings_carry_court),
            "cohortMonths": cohort_months,
            "cohortFrom": cohort_start.date().isoformat(),
            "faraJudet": len(unmatched),
            "instanteTrunchiate": len(unmeasured),
            "pragTrunchiere": TRUNCATED_BELOW,
        },
        "praguriZile": {
            "termene": list(TERMEN_BINS),
            "durata": list(DURATA_BINS),
            "peRol": list(edges),
        },
        "judete": dict(sorted(manifest.get("countyNames", {}).items())),
        "instante": courts,
        "faraPotrivireDeNume": unmatched,
        "instanteTrunchiate": sorted(unmeasured),
    }


LIMITATIONS = [
    {
        "id": "cuantilele-vin-din-histograme",
        "text": (
            "Nimic aici nu este o cuantilă gata calculată, fiindcă o mediană nu se adună: două "
            "instanțe cu mediana de 120 de zile nu fac un județ cu mediana de 120 de zile. "
            "Fișierul poartă histograme, iar cuantila se ia din suma lor — ceea ce dă cuantila "
            "distribuției reunite, nu o medie de cuantile. Prețul este granulația: pragurile "
            "sunt tipărite în `praguriZile`, iar o mediană cade pe marginea de bin, nu pe zi."
        ),
        "severity": "material",
        "affects": ["primulTermen", "intervalTermene", "durata"],
    },
    {
        "id": "durata-e-tabel-de-mortalitate-nu-kaplan-meier",
        "text": (
            "Durata se publică pe bin: câte dosare s-au soluționat în fiecare interval și câte "
            "erau încă în curs. Estimatorul care iese este cel actuarial, nu Kaplan-Meier. Cele "
            "două coincid până la lățimea binului și se despart acolo unde multe dosare sunt "
            "cenzurate în același bin, de aceea binurile sunt înguste la început, unde se "
            "întâmplă evenimentele, și late la sfârșit, unde nu."
        ),
        "severity": "material",
        "affects": ["durata"],
    },
    {
        "id": "instantele-nepotrivite-nu-au-judet",
        "text": (
            "Instanțele al căror nume nu se regăsește în anexa CSM primesc `judet: null` și sunt "
            "listate în `faraPotrivireDeNume`. Sunt păstrate cu cifrele lor: patru judecătorii "
            "există pe portal și nu în anexă fiindcă sunt suspendate, iar a le arunca ar strica "
            "puțin fiecare cotă pe județ, fără ca nimic să arate asta."
        ),
        "severity": "note",
        "affects": ["instante"],
    },
    {
        "id": "instantele-trunchiate-sunt-marcate-nu-sterse",
        "text": (
            "O instanță pe care colectarea nu a terminat-o poartă `acoperire.trunchiat: true` și "
            "este numărată în `snapshot.instanteTrunchiate`. Rândul rămâne, cu cifrele lui, "
            "fiindcă a-l șterge ar face ca un total pe județ să fie o sumă peste mai puține "
            "instanțe decât numește, fără ca nimic să arate asta. Pragul nu este o judecată: "
            "raportul dintre dosarele de pe portal și volumul publicat de CSM are p10 la 0,008 și "
            "p25 la 1,259 — două ordine de mărime de gol între o instanță colectată și una nu. "
            "Orice cifră a unei instanțe marcate este un fragment, nu o măsurătoare."
        ),
        "severity": "blocking",
        "affects": ["instante", "dosare"],
    },
    {
        "id": "portalul-nu-e-arhiva",
        "text": (
            "Ca și în `portal-stats`: portalul ține dosarele de pe rol și pe cele închise recent, "
            "iar instanțele le scot pe măsură ce le arhivează. De aceea durata și termenele se "
            "calculează numai pe cohorta recentă declarată în `snapshot.cohortFrom`, iar "
            "numărul de dosare al unei instanțe este un prag de jos."
        ),
        "severity": "blocking",
        "affects": ["dosare", "peRol", "durata"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None, help="directory of parquet parts")
    parser.add_argument("--release", default=None, help="release tag, or 'latest'")
    parser.add_argument("--cohort-months", type=int, default=12)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if not args.input and not args.release:
        parser.error("one of --input or --release is required")

    with tempfile.TemporaryDirectory() as temporary:
        if args.release:
            input_dir = Path(temporary)
            fetch_release(args.release, input_dir)
        else:
            input_dir = Path(args.input)

        dosare, sedinte, _parti, _cai_atac = load(input_dir)
        coverage = sorted(input_dir.glob("coverage*.json"))
        crawled_at = datetime.now().isoformat(timespec="seconds")
        if coverage:
            report = json.loads(coverage[-1].read_text(encoding="utf-8"))
            crawled_at = report.get("crawledAt", crawled_at)

        body = build(dosare, sedinte, args.cohort_months, crawled_at)

    document = {
        "$schema": "../schema/portal-instante.schema.json",
        "id": "portal-instante",
        "title": "Cifrele fiecărei instanțe, în formă care se poate aduna",
        "publisher": "Ministerul Justiției — portal.just.ro (ECRIS)",
        "period": f"{body['snapshot']['cohortFrom']} — {body['snapshot']['crawledAt'][:10]}",
        "provenance": {
            "source": "portal-just-ro",
            "locator": (
                f"serviciul web portalquery.just.ro/Query.asmx, instantaneu "
                f"{body['snapshot']['crawledAt']}, {body['snapshot']['instante']} instanțe; "
                f"județul prin numele tipărit în instante-localizate-2025"
            ),
            "confidence": "derived",
            "note": (
                "Numai numărători și histograme, ca orice selecție de instanțe — județ, "
                "circumscripție, instanță propusă — să se poată însuma."
            ),
        },
        **body,
        "limitations": LIMITATIONS,
    }

    out = Path(args.out) if args.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    snapshot = body["snapshot"]
    print(
        f"{snapshot['instante']} instanțe -> {out.name} ({out.stat().st_size / 1000:.0f} kB)"
    )
    if snapshot["faraJudet"]:
        print(f"  {snapshot['faraJudet']} without a county: {', '.join(body['faraPotrivireDeNume'])}")
    if snapshot["instanteTrunchiate"]:
        print(
            f"  {snapshot['instanteTrunchiate']} courts the crawl did not finish, flagged"
            f" trunchiat: {', '.join(body['instanteTrunchiate'][:6])}…",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
