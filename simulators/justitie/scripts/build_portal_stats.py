"""What the case files say about workload, case types and termene.

`build_incarcatura.py` answers the workload question from CSM's annual aggregates: one row per
court per year, already averaged. This answers it from the case files themselves, which the
courts publish and `import_portal.py` collects — so the unit is a case rather than a court-year,
and questions the aggregates cannot reach become answerable. How many days a court leaves
between two termene. How many termene a case has behind it. Which institutions appear as
parties, and in what role.

The hard part is not the arithmetic. It is knowing which of those questions a snapshot is
allowed to answer.

The portal is not an archive: it holds cases that are still live plus those recently closed, and
drops them as courts archive them. So a snapshot of old cases is a *survival sample* — the cases
visible from 2023 are visible because they are slow. Any statistic that reads like a duration is
therefore biased upward by an amount that grows with the age of the cohort, and grows fastest
exactly where a reform argument would want to quote it.

Two rules follow, and they are what most of this file is:

  1. Anything time-shaped — the gap between consecutive termene, the days to a first hearing,
     the time to a resolution — is computed only over a recent registration cohort, where
     little has yet been archived and the survival sample is still close to the whole. The
     cohort is named in the output, and `--cohort-months` moves it, because the right width is
     an argument about archiving practice rather than a constant.

  2. Within that cohort, duration is estimated rather than averaged. A recent cohort is not
     truncated but it is *censored*: some of its cases are still running, and averaging the
     finished ones understates by dropping every slow case still in progress. Kaplan-Meier uses
     both, and refuses to answer past its own follow-up instead of extrapolating.

An earlier version of this file said duration could not be computed at all. That was too strong.
The per-case ingredients are all present — registration date, and a pronouncement on the last
termen — and what makes a naive duration wrong is the cohort it is averaged over, not the
absence of data. `gradientArhivare` publishes the size of that error rather than only warning
about it: the naive median rises from 56 days for the newest cohort to 584 for a four-year-old
one at the same court, which is the shape of what has been archived and not of any court
becoming ten times slower.

What survives those rules is still most of what was asked for. Stock per court and per panel,
the mix of case types, the interval between termene, the stage a case is at, the age of what is
pending — all of them are properties of the visible set, and the visible set is what the courts
publish.

The appeal rate needed a third rule, because the obvious way to compute it is wrong. `caiAtac`
looks like the field for it and is not: it records the appeal that brought a case to the court
it is at, so counting it per level says a court of appeal hears appeals. The rate that was
actually wanted comes from the case number, which survives the move upward, and it comes out as
a floor rather than a rate. Both are explained where they are computed.

Usage:
    uv run --with pyarrow --with pandas python scripts/build_portal_stats.py \
        --input data/portal
    uv run --with pyarrow --with pandas python scripts/build_portal_stats.py --release latest
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "portal-stats.json"
REPO = "CristianNichifor/romania-reforms"

# The court level, read off the Institutie enum. Order matters: TribunalulComercial and
# TribunalulpentruminoriSifamilie both start with "Tribunalul" and are specialised first-instance
# courts rather than ordinary tribunale, so they are matched before the general prefix.
LEVELS = (
    ("CurteadeApel", "curte de apel"),
    ("TribunalulComercial", "tribunal specializat"),
    ("Tribunalulpentruminori", "tribunal specializat"),
    ("Tribunalul", "tribunal"),
    ("Judecatoria", "judecătorie"),
)

# Aging buckets for pending cases, in days. The 365 and 547 edges are the ones CSM's own E02
# indicator uses ("stocul de dosare mai vechi de 1 an / 1 an și 6 luni"), so the shape of this
# distribution can be argued against the indicator the courts are already measured on.
AGE_BUCKETS = ((0, 90), (90, 180), (180, 365), (365, 547), (547, None))


def level_of(institutie: str) -> str:
    for prefix, name in LEVELS:
        if institutie.startswith(prefix):
            return name
    return "necunoscut"


def normalise_solutie(text: str) -> str:
    """Fold a disposition string into a comparable key.

    ECRIS holds "Admite cererea" and "admite cererea" as different strings, and counting them
    apart splits the commonest outcome in the file across two rows. Case and whitespace are the
    only things folded — the vocabulary is not otherwise regularised, because mapping "Amână
    cauza" and "Termen preschimbat" onto a common scheme is a judgement about procedure and does
    not belong in a loader.
    """
    return re.sub(r"\s+", " ", text.strip()).casefold()


# The charge text carries its own statutory reference — "furtul calificat (art.229 NCP)",
# "verificare măsuri preventive (art.207 NCPP)", "traficul de droguri (Legea 143/2000 art. 2)" —
# so the free text yields a structured key.
#
# The code matters more than the article. NCP is the penal code, so an NCP reference is an
# offence someone is accused of. NCPP is the code of criminal *procedure*, so an NCPP reference
# is a step in the machinery: confirming a prosecutor's discontinuance, reviewing preventive
# detention, ruling on conditional release. Counting them together produces a "top charges"
# chart whose leading entries are not charges at all, and which says criminal courts mostly try
# people for "confirmation of a decision not to prosecute".
#
# Special laws are a third bucket rather than being forced into either. Some carry offences
# (143/2000 is drug trafficking and drug use, 217/2003 breach of a protection order) and some
# carry procedure (302/2004 recognition of foreign judgments, 254/2013 sentence execution), and
# deciding which is which is a reading of each statute rather than something a parser should
# assume. Without this bucket every drug case is simply invisible: a first pass that recognised
# only NCP and NCPP left 27% unparsed and no drug offence anywhere in the top charges.
CHARGE_ARTICLE = re.compile(
    # "art.229", optionally followed by alin./ind./lit. qualifiers, then the code. The qualifier
    # group has to allow letters because "art.315 lit. c NCPP" puts one between the two.
    r"art\.?\s*(\d+)"
    r"(?:\s*(?:alin|ind|lit)\.?[\s\d.,()a-z]*)?"
    r"\s*(NCPP|NCP|C\.?p\.?p\.?|CPP|CP|C\.pen)",
    re.I,
)

# "Legea 143/2000", "L217/2003", "Legea 302/2004". The year disambiguates: several statutes share
# a number.
CHARGE_LAW = re.compile(r"\b(?:Legea|Lege|L)\s*\.?\s*(\d{1,4})\s*/\s*(\d{4})", re.I)

# Which special laws carry offences rather than procedure. Deliberately short and explicit: an
# entry here is a claim about what a statute is for, and guessing from the number would put
# sentence-execution complaints in a chart of crimes.
OFFENCE_LAWS = {
    "143/2000": "trafic și consum de droguri",
    "217/2003": "ordin de protecție",
    "286/2009": "cod penal",
}


def parse_charge(text: str) -> tuple:
    """Return (code, article) from a case's obiect, or (None, None) when it carries neither.

    The code is "NCP"/"NCPP" for the two codes, or "L<number>/<year>" for a special law. The
    article is the one printed beside it, or None where a law is cited without one.
    """
    body = text or ""
    found = CHARGE_ARTICLE.search(body)
    if found:
        code = found.group(2).upper().replace(".", "").replace("C.PEN", "CP")
        code = {"CPP": "NCPP", "CP": "NCP"}.get(code, code)
        return (code, int(found.group(1)))
    law = CHARGE_LAW.search(body)
    if law:
        article = re.search(r"art\.?\s*(\d+)", body, re.I)
        return (f"L{law.group(1)}/{law.group(2)}", int(article.group(1)) if article else None)
    return (None, None)


# An ancillary file is not another dispute. ECRIS numbers incidental proceedings by suffixing
# the parent — 1019/1752/2012/a1 belongs to 1019/1752/2012 — and 8% of case numbers carry one.
# Counting them separately inflated the dispute count for 1,414 of 13,312 identities at a single
# court, which is exactly the population a "who litigates most" figure is about.
ANCILLARY = re.compile(r"/a\d+$")

# How a party stands in the case. Grouped because the raw vocabulary has dozens of values and
# because the groups mean opposite things: an identity appearing 124 times as Pârât is being
# pursued, and one appearing 56 times as Parte vătămată is a victim. A single "cases per person"
# count merges all three into a number that reads as litigiousness.
ROLE_GROUPS = {
    "initiaza": {
        "reclamant",
        "petent",
        "contestator",
        "creditor",
        "apelant",
        "recurent",
        "petiţionar",
        "petitionar",
        "revizuent",
    },
    "raspunde": {"pârât", "parat", "intimat", "debitor", "chemat în garanţie"},
    "vatamat": {"parte vătămată", "parte vatamata", "parte civilă", "parte civila", "victimă"},
    "acuzat": {"inculpat", "suspect", "condamnat", "făptuitor", "faptuitor"},
}

# Objects that are debt recovery run at volume. An identity filing these in bulk is a business
# whatever its name folded to — the classifier fails closed toward "natural person", so the top
# of any repeat-filer list is companies it declined to name.
RECOVERY_OBJECTS = (
    "cerere de valoare redusă",
    "valoare redusa",
    "validare poprire",
    "ordonanţă de plată",
    "ordonanta de plata",
    "somaţie de plată",
    "somatie de plata",
    "pretenţii",
    "pretentii",
)

# Above this many disputes, mostly initiating and mostly debt recovery, the behaviour is
# institutional. Deliberately blunt: it flags a pattern, it does not name anyone, and the output
# reports how much of the total those identities carry rather than who they are.
INSTITUTIONAL_MIN_DISPUTES = 20
INSTITUTIONAL_RECOVERY_SHARE = 0.6


def role_group(calitate: str) -> str:
    folded = re.sub(r"\s+", " ", (calitate or "").strip()).casefold()
    for group, members in ROLE_GROUPS.items():
        if folded in members:
            return group
    return "altul"


def hearing_court(dosare, sedinte):
    """Which court held each hearing.

    The importer writes `institutie` onto the child tables now, and where it is present this is
    a column lookup. Where it is not — anything crawled before that — the court has to be
    recovered from the case, and the obvious way to do it is wrong at a scale worth naming:
    **11,2% of visible cases exist at more than one court**, 468.792 of 4.173.750, because a case
    keeps its number when it goes up. Mapping a number to "its" court then means mapping it to
    whichever court happened to be last in the file.

    So the hearing is assigned by date instead. A case is registered afresh at each court that
    takes it, and a hearing held on a given day belongs to the court that had the file that day —
    the one whose registration is the most recent at or before it. A hearing that predates every
    registration falls back to the earliest court, which is the only defensible reading of a date
    that should not exist.

    The consequence is that every hearing belongs to exactly one court, so per-court figures sum
    to the national total. The earlier reading — every hearing of every case a court ever touched
    — counted an escalated case's whole history at both courts, and two courts' panel counts
    could not be added.
    """
    import pandas as pd  # noqa: PLC0415

    if "institutie" in sedinte.columns:
        return sedinte.institutie

    # Only the ambiguous cases need the dated merge, and they are the minority. A case at one
    # court has one answer, and asking `merge_asof` for it means sorting eleven million hearings
    # and grouping four million case numbers to rediscover what a dictionary already knows.
    # Splitting the two costs one `value_counts` and takes the merge down to a ninth of its
    # input. It does not move the process peak, which is the four parquet tables held in memory
    # at once — 28 million rows of mostly strings — and that is the number to attack if this ever
    # has to run somewhere smaller than a workstation.
    per_case = dosare.numar.value_counts()
    settled = dosare[dosare.numar.map(per_case) == 1]
    single = dict(zip(settled.numar, settled.institutie, strict=False))
    resolved = sedinte.dosar_numar.map(single)

    ambiguous = sedinte.index[resolved.isna()]
    if not len(ambiguous):
        return resolved

    contested = set(sedinte.loc[ambiguous, "dosar_numar"])
    stages = (
        dosare[dosare.numar.isin(contested)][["numar", "institutie", "registered"]]
        .dropna(subset=["registered"])
        .rename(columns={"numar": "dosar_numar", "institutie": "court"})
        .sort_values("registered")
    )
    left = sedinte.loc[ambiguous, ["dosar_numar", "when"]].reset_index().sort_values("when")
    # `merge_asof` refuses keys whose two sides differ in dtype, and both keys differ here for
    # reasons that have nothing to do with the data: parquet hands back StringDtype where a
    # constructed frame hands back object, and `to_datetime` picks a second or a microsecond
    # resolution depending on which strings it was given. Both sides are strings and both are
    # timestamps; saying so is cheaper than a MergeError that only fires on one of the inputs.
    stages["dosar_numar"] = stages.dosar_numar.astype("string")
    left["dosar_numar"] = left.dosar_numar.astype("string")
    stages["registered"] = stages.registered.astype("datetime64[ns]")
    left["when"] = left["when"].astype("datetime64[ns]")
    merged = pd.merge_asof(
        left, stages, left_on="when", right_on="registered", by="dosar_numar", direction="backward"
    )
    earliest = stages.groupby("dosar_numar", sort=False).court.first()
    merged["court"] = merged.court.fillna(merged.dosar_numar.map(earliest))
    return resolved.fillna(merged.set_index("index").court)


def percentiles(series, points=(0.25, 0.5, 0.75)) -> dict:
    if series.empty:
        return {}
    quantiles = series.quantile(list(points))
    return {f"p{int(point * 100)}": round(float(quantiles[point]), 1) for point in points}


def kaplan_meier(durations, observed, marks=(90, 180, 365)) -> dict:
    """Resolution curve for a cohort in which some cases have not finished.

    Needed because the obvious alternatives are both wrong in a known direction. Averaging the
    cases that *have* a pronouncement throws away every slow case that is still running and
    understates. Treating "still open at the crawl date" as a duration understates differently,
    by pretending an unfinished case finished today. A case still open after 200 days is not a
    200-day case; it is a case that took *at least* 200 days, and that is exactly the
    information a survival estimator uses instead of discarding.

    `durations` is days from registration to pronouncement for resolved cases, and days from
    registration to the crawl date for the rest. `observed` says which is which.

    Implemented here rather than by adding lifelines: it is fifteen lines, the repository has no
    scientific stack beyond pandas, and a dependency that exists to compute a product of
    (1 - d/n) is not worth the lockfile.
    """
    pairs = sorted(zip(durations, observed, strict=True))
    total = len(pairs)
    if not total:
        return {}
    survival = 1.0
    at_risk = total
    curve = {}
    index = 0
    events = 0
    while index < len(pairs):
        time = pairs[index][0]
        deaths = 0
        same = 0
        while index < len(pairs) and pairs[index][0] == time:
            deaths += 1 if pairs[index][1] else 0
            same += 1
            index += 1
        if deaths and at_risk:
            survival *= 1 - deaths / at_risk
            events += deaths
        at_risk -= same
        curve[time] = survival
    times = sorted(curve)

    def survival_at(day: int) -> float:
        current = 1.0
        for time in times:
            if time > day:
                break
            current = curve[time]
        return current

    # The median is the first day the curve crosses one half. Absent when it never does, which
    # is the honest answer for a cohort where most cases are still running: "more than the
    # follow-up" rather than a number invented by extrapolation.
    median = next((time for time in times if curve[time] <= 0.5), None)

    # A Kaplan-Meier curve says nothing past its longest observation, and asking it anyway is
    # how a five-day sample came back claiming 100% of cases resolve within a year: beyond the
    # last observation nobody is at risk, the curve goes flat, and `1 - S` reports that flat
    # value as if it had been measured. Marks past the follow-up are null, not extrapolated.
    follow_up = times[-1] if times else 0
    return {
        "dosare": total,
        "solutionate": events,
        "inCurs": total - events,
        "urmarireZile": follow_up,
        "medianaZile": median,
        "rezolvatePana": {
            f"zi{day}": (round(1 - survival_at(day), 4) if day <= follow_up else None)
            for day in marks
        },
    }


def load(input_dir: Path):
    import pandas as pd  # noqa: PLC0415

    def read(prefix: str):
        files = sorted(glob.glob(str(input_dir / f"{prefix}-*.parquet")))
        if not files:
            raise SystemExit(f"no {prefix}-*.parquet under {input_dir}")
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    dosare = read("dosare")
    # Shards are disjoint by court, but a backfill re-run overlapping an earlier one is not, and
    # the daily workflow deliberately re-crawls a two-month window. Deduplicating on the case
    # number is what makes those overlaps free rather than double-counted.
    dosare = dosare.drop_duplicates(subset=["institutie", "numar"], keep="last")
    return dosare, read("sedinte"), read("parti"), read("cai_atac")


def fetch_release(tag: str, into: Path) -> None:
    resolved = tag
    if tag == "latest":
        listing = subprocess.run(
            ["gh", "release", "list", "--repo", REPO, "--limit", "50"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        tags = [line.split("\t")[-1].strip() for line in listing.splitlines()]
        portal = sorted(t for t in tags if t.startswith("portal-"))
        if not portal:
            raise SystemExit("no portal-* release found")
        resolved = portal[-1]
    print(f"fetching release {resolved}")
    subprocess.run(
        ["gh", "release", "download", resolved, "--repo", REPO, "--dir", str(into), "--clobber"],
        check=True,
    )


def build(dosare, sedinte, parti, cai_atac, cohort_months: int, crawled_at: str) -> dict:
    import pandas as pd  # noqa: PLC0415

    dosare = dosare.copy()
    dosare["level"] = dosare.institutie.map(level_of)
    dosare["registered"] = pd.to_datetime(dosare.data, errors="coerce")
    now = pd.Timestamp(crawled_at)

    sedinte = sedinte.copy()
    sedinte["when"] = pd.to_datetime(sedinte.data, errors="coerce")
    sedinte = sedinte.dropna(subset=["when"])

    # The court a hearing belongs to. See `hearing_court`: where the child table does not carry
    # it, it is recovered from which court had the file on the day, not from the case number —
    # 11,2% of cases sit at more than one court, and a number-to-court map picks one of them at
    # random. `institutieDinFisier` in the output says which of the two routes was taken.
    hearings_carry_court = "institutie" in sedinte.columns
    sedinte = sedinte.assign(court=hearing_court(dosare, sedinte))
    sedinte = sedinte.dropna(subset=["court"])
    sedinte = sedinte.assign(level=sedinte.court.map(level_of))

    # ---- stock per court -------------------------------------------------------------------
    panels_by_level = (
        sedinte.assign(complet=sedinte.complet.replace("", pd.NA))
        .dropna(subset=["complet", "level"])
        .groupby("level")
        .complet.nunique()
    )

    panels_by_court = (
        sedinte.assign(complet=sedinte.complet.replace("", pd.NA))
        .dropna(subset=["complet"])
        .groupby("court")
        .complet.nunique()
    )

    courts = []
    for institutie, group in dosare.groupby("institutie"):
        panels = int(panels_by_court.get(institutie, 0))
        courts.append(
            {
                "institutie": institutie,
                "level": level_of(institutie),
                "dosare": int(len(group)),
                "sectii": int(group.departament.replace("", pd.NA).dropna().nunique()),
                "completuri": int(panels),
                # Only meaningful where a panel was actually observed sitting; a court whose
                # visible cases have no hearing yet gets null rather than a division by zero.
                "dosarePerComplet": round(len(group) / panels, 1) if panels else None,
            }
        )
    courts.sort(key=lambda row: -row["dosare"])

    levels = []
    for name, group in dosare.groupby("level"):
        panels = int(panels_by_level.get(name, 0))
        levels.append(
            {
                "level": name,
                "instante": int(group.institutie.nunique()),
                "dosare": int(len(group)),
                "completuri": panels,
                "dosarePerComplet": round(len(group) / panels, 1) if panels else None,
            }
        )
    levels.sort(key=lambda row: -row["dosare"])

    # ---- case types ------------------------------------------------------------------------
    total = len(dosare)
    case_types = []
    for categorie, group in dosare.groupby(dosare.categorie_caz.replace("", "necunoscut")):
        by_level = {name: int(count) for name, count in group.level.value_counts().items()}
        case_types.append(
            {
                "categorie": str(categorie),
                "dosare": int(len(group)),
                "share": round(len(group) / total, 4),
                "byLevel": by_level,
            }
        )
    case_types.sort(key=lambda row: -row["dosare"])

    # ---- termene ---------------------------------------------------------------------------
    # The cohort restriction. Intervals are observed for any case still on the portal, and old
    # cases are on the portal because they were slow, so the unrestricted distribution measures
    # slowness twice. Cases registered inside the cohort have had almost no chance to be
    # archived, which is what makes their intervals close to the intervals of all cases filed
    # then — not identical, since the very fastest may already be gone, but close.
    cohort_start = now - pd.DateOffset(months=cohort_months)
    cohort = set(dosare[dosare.registered >= cohort_start].numar)
    in_cohort = sedinte[sedinte.dosar_numar.isin(cohort)].sort_values(["dosar_numar", "when"])
    gaps = in_cohort.groupby("dosar_numar").when.diff().dt.days.dropna()
    gaps = gaps[gaps >= 0]
    gap_level = in_cohort.loc[gaps.index].level

    termene_by_level = []
    for name, group in gaps.groupby(gap_level):
        termene_by_level.append(
            {"level": str(name), "intervale": int(len(group)), **percentiles(group)}
        )
    termene_by_level.sort(key=lambda row: -row["intervale"])

    counts = in_cohort.groupby("dosar_numar").size()
    termene = {
        "cohortMonths": cohort_months,
        "cohortFrom": cohort_start.date().isoformat(),
        "dosareInCohort": int(len(cohort)),
        "dosareCuTermene": int(len(counts)),
        "intervalZileByLevel": termene_by_level,
        "termenePerDosar": percentiles(counts) if not counts.empty else {},
    }

    # ---- how long a case takes -------------------------------------------------------------
    # Resolution is the last pronouncement recorded on any of a case's termene. 98-100% of
    # visible cases carry one, so this is the observable event; a case without one is running.
    # Two things about dataPronuntare that its name does not warn about, both established by
    # looking at the values rather than trusting the field.
    #
    # It is not always in the past. The column runs to 2027 in a snapshot taken in 2026, because
    # a deferred pronouncement carries the date it is deferred *to*. A future date is a schedule,
    # not a delivery, and counting it as a resolution marks unfinished cases finished.
    #
    # And it is not always after registration. `dosar.data` is the date the case was registered
    # at *this* court, while `sedinte` carries the whole file's history — so a case that arrived
    # on appeal has pronouncements from the stage below it, dated before it got here. In the
    # five-day sample 552 of 1,916 resolved cases had one, a median of a day before registration
    # and one 559 days before. Dropping them by filtering on a non-negative duration is not
    # neutral: it removes precisely the cases that moved between courts.
    #
    # So resolution means the last pronouncement that was actually delivered, during this
    # court's handling of the case: at or after registration here, at or before the crawl.
    sedinte["pronuntat"] = pd.to_datetime(sedinte.data_pronuntare, errors="coerce")
    delivered = sedinte.dropna(subset=["pronuntat"]).copy()
    # to_datetime around the map because an empty frame, or one whose cases are all absent from
    # the mapping, yields a float64 column of NaN — and comparing that to a timestamp raises
    # rather than producing an empty selection.
    delivered["inregistrat"] = pd.to_datetime(
        delivered.dosar_numar.map(dosare.set_index("numar").registered.to_dict()),
        errors="coerce",
    )
    delivered = delivered[
        (delivered.pronuntat <= now) & (delivered.pronuntat >= delivered.inregistrat)
    ]
    resolved_at = delivered.groupby("dosar_numar").pronuntat.max()

    lifecycle = dosare[["numar", "level", "registered", "categorie_caz"]].copy()
    # Coerced for the same reason as `inregistrat` above: when no pronouncement survives the
    # delivered-and-after-registration filter, the mapping is empty and the column comes back as
    # float64 NaN, which then refuses a Timestamp in the fillna below.
    lifecycle["resolved"] = pd.to_datetime(
        lifecycle.numar.map(resolved_at.to_dict()), errors="coerce"
    )
    lifecycle["observed"] = lifecycle.resolved.notna()
    # Days to the pronouncement, or days to the crawl date for a case still running. The second
    # is not a duration, it is a floor, and kaplan_meier is what knows the difference.
    lifecycle["days"] = (lifecycle.resolved.fillna(now) - lifecycle.registered).dt.days
    lifecycle = lifecycle[lifecycle.days >= 0]

    # Cohorts recent enough that archiving has not yet removed their fast cases. Measured at
    # Judecătoria Jibou: for cases filed in March 2026 the oldest surviving pronouncement is
    # 5 March 2026, the week they were filed, so nothing has left yet.
    fresh = lifecycle[lifecycle.registered >= cohort_start]
    durata_by_level = []
    for name, group in fresh.groupby("level"):
        estimate = kaplan_meier(group.days.tolist(), group.observed.tolist())
        if estimate:
            durata_by_level.append({"level": str(name), **estimate})
    durata_by_level.sort(key=lambda row: -row["dosare"])

    durata_by_type = []
    for name, group in fresh.groupby(fresh.categorie_caz.replace("", "necunoscut")):
        if len(group) < 200:
            continue  # too few to say anything, and a median from 30 cases invites quotation
        estimate = kaplan_meier(group.days.tolist(), group.observed.tolist())
        if estimate:
            durata_by_type.append({"categorie": str(name), **estimate})
    durata_by_type.sort(key=lambda row: -row["dosare"])

    # The archiving gradient, published rather than hidden. Taking the naive median of resolved
    # cases per registration year produces a curve that rises steeply the further back you look
    # — 56 days for 2026 against 584 for 2022 at Jibou. No court changed that much. It is the
    # shape of what has been archived, and it is the reason `durata` is restricted to a cohort.
    # Kept in the output because it is also the only public evidence of archiving practice.
    gradient = []
    closed = lifecycle[lifecycle.observed]
    for year, group in closed.groupby(closed.registered.dt.year):
        if len(group) < 100:
            continue
        gradient.append(
            {
                "anInregistrare": int(year),
                "dosareVizibileSolutionate": int(len(group)),
                "medianaNaivaZile": round(float(group.days.median()), 1),
            }
        )
    gradient.sort(key=lambda row: row["anInregistrare"])

    # ---- how long before anything happens --------------------------------------------------
    first_hearing = sedinte.groupby("dosar_numar").when.min()
    # .to_dict() rather than mapping the Series directly: pandas takes the result dtype from the
    # mapping, and mapping an *empty* datetime Series casts to float64 and raises. A court whose
    # cases have no hearing yet is an ordinary state, not an error.
    wait = fresh.assign(
        first=pd.to_datetime(fresh.numar.map(first_hearing.to_dict()), errors="coerce")
    )
    wait = wait.dropna(subset=["first"])
    wait["zile"] = (wait["first"] - wait.registered).dt.days
    wait = wait[wait.zile >= 0]
    primul_termen = [
        {"level": str(name), "dosare": int(len(group)), **percentiles(group.zile)}
        for name, group in wait.groupby("level")
    ]
    primul_termen.sort(key=lambda row: -row["dosare"])

    # ---- hearings that move nothing --------------------------------------------------------
    # An adjournment is a sitting that consumed a slot and advanced the case by one date. The
    # share of them is an efficiency measure CSM does not publish, and unlike a duration it is a
    # property of hearings, so a survival sample distorts it far less.
    # Three different acts, which a single "am[âaă]n|preschimb" pattern collapses into one
    # number and makes unquotable:
    #
    #   Amână cauza          the hearing happened and the case was put over to another date
    #   Amână pronunţarea    the hearing finished and the judgment was deferred — the court has
    #                        heard the case, which is not the same as not reaching it
    #   Termen preschimbat   the date itself was moved, often before anyone sat
    #
    # Only the first is an adjournment in the sense a workload argument means. They are counted
    # apart, and `cotaFaraProgres` is the union, so a reader can take either.
    dispositions = sedinte.solutie.replace("", None).dropna().map(normalise_solutie)
    deferred_judgment = dispositions.str.contains(r"am[âaă]n[ăa]?\s+pronun", regex=True, na=False)
    rescheduled = dispositions.str.contains(r"preschimb", regex=True, na=False)
    adjourned = dispositions.str.contains(r"am[âaă]n", regex=True, na=False) & ~deferred_judgment
    total_dispositions = len(dispositions)

    def share(mask) -> float | None:
        return round(float(mask.mean()), 4) if total_dispositions else None

    amanari = {
        "termeneCuSolutie": int(total_dispositions),
        "amanareCauza": int(adjourned.sum()),
        "amanarePronuntare": int(deferred_judgment.sum()),
        "termenPreschimbat": int(rescheduled.sum()),
        "cotaAmanareCauza": share(adjourned),
        "cotaFaraProgres": share(adjourned | deferred_judgment | rescheduled),
    }

    # ---- what the criminal courts are actually handling ------------------------------------
    penal = dosare[dosare.is_penal].copy()
    parsed = penal.obiect.fillna("").map(parse_charge)
    penal["cod"] = [row[0] for row in parsed]
    penal["articol"] = [row[1] for row in parsed]

    offences = []
    grouped = penal.dropna(subset=["cod"]).groupby(["cod", penal.articol.fillna(-1)])
    for (code, article), group in grouped:
        offences.append(
            {
                "cod": str(code),
                # -1 stands in for a law cited without an article, which groupby cannot carry as
                # a null key. It goes back to null on the way out.
                "articol": None if article == -1 else int(article),
                "dosare": int(len(group)),
                # The commonest wording, not the longest. Clerks append the related articles to
                # the charge — "furtul calificat (art.229 NCP) art.32 alin.1 rap. la art.228" —
                # so the longest string is reliably the messiest one, while the mode is the
                # plain name of the offence.
                "denumire": (
                    group.obiect.replace("", pd.NA).dropna().mode().iat[0]
                    if group.obiect.replace("", pd.NA).notna().any()
                    else ""
                ),
            }
        )
    offences.sort(key=lambda row: -row["dosare"])

    by_code = penal.cod.value_counts(dropna=False)
    special = {code for code in by_code.index if isinstance(code, str) and code.startswith("L")}
    penal_summary = {
        "dosarePenale": int(len(penal)),
        "cuArticol": int(penal.cod.notna().sum()),
        "peCod": {
            ("neidentificat" if pd.isna(code) else str(code)): int(count)
            for code, count in by_code.items()
        },
        # The headline. A criminal docket is mostly procedure, and this says how much.
        "cotaProcedurala": (
            round(int(by_code.get("NCPP", 0)) / len(penal), 4) if len(penal) else None
        ),
        "infractiuni": [row for row in offences if row["cod"] == "NCP"][:40],
        "proceduri": [row for row in offences if row["cod"] == "NCPP"][:20],
        # Kept whole rather than split into offence and procedure: see OFFENCE_LAWS. The named
        # ones are the statutes whose character has actually been checked.
        "legiSpeciale": [row for row in offences if row["cod"] in special][:20],
        "legiCunoscute": OFFENCE_LAWS,
    }

    # ---- how concentrated the docket is ----------------------------------------------------
    # What this is not: a list of people who use the courts a lot. Three things stop that being
    # sayable from this source, and all three are in the limitations.
    #
    #   * The hash identifies a *name*, not a person. Folding is deliberate — it merges the two
    #     encodings of ŞTEFAN — and it therefore merges every Popescu Ion in the country. There
    #     is no CNP and no date of birth to separate them, so a repeat count is an upper bound.
    #   * The classifier fails closed, so companies it could not confidently name are counted
    #     here as natural persons. The largest identity at one judecătorie filed 1,183 small
    #     claims; that is a debt collector, not a litigious neighbour.
    #   * Appearing often is not doing anything. The third-largest identity was a defendant 124
    #     times and the eighth was an injured party 56 times.
    #
    # What it is: the shape of who brings the work. That question survives all three objections,
    # because it does not need to know who anyone is — only that a small number of filing
    # identities account for a large share of first-instance civil business, nearly all of it
    # debt recovery. Nothing per-identity is published; the tail is bucketed and only counts of
    # identities leave this function.
    persons = parti[parti.nume_hash.notna()].copy()
    concentrare = {}
    if len(persons):
        persons["dispute"] = persons.dosar_numar.str.replace(ANCILLARY, "", regex=True)
        persons["grup"] = persons.calitate.map(role_group)
        objects = dosare.set_index("numar").obiect.to_dict()
        persons["obiect"] = persons.dosar_numar.map(objects).fillna("")

        disputes = persons.groupby("nume_hash").dispute.nunique()
        buckets = pd.cut(
            disputes, [0, 1, 2, 4, 9, float("inf")], labels=["1", "2", "3-4", "5-9", "10+"]
        )
        counts = buckets.value_counts().sort_index()

        initiating = persons[persons.grup == "initiaza"]
        by_filer = initiating.groupby("nume_hash").dispute.nunique().sort_values(ascending=False)
        filed_total = int(by_filer.sum())

        def top_share(fraction: float) -> float | None:
            if not filed_total:
                return None
            take = max(int(len(by_filer) * fraction), 1)
            return round(float(by_filer.head(take).sum()) / filed_total, 4)

        recovery = initiating.obiect.str.casefold().str.contains(
            "|".join(re.escape(term) for term in RECOVERY_OBJECTS), regex=True, na=False
        )
        share_recovery = initiating.assign(rec=recovery).groupby("nume_hash").rec.mean()
        institutional = set(by_filer[by_filer >= INSTITUTIONAL_MIN_DISPUTES].index) & set(
            share_recovery[share_recovery >= INSTITUTIONAL_RECOVERY_SHARE].index
        )

        concentrare = {
            "identitati": int(disputes.size),
            "dosareAncilare": int(persons.dosar_numar.str.contains(ANCILLARY, regex=True).sum()),
            "distributie": [
                {
                    "disputeDeLaPanaLa": str(label),
                    "identitati": int(value),
                    "cota": round(int(value) / int(disputes.size), 4),
                }
                for label, value in counts.items()
            ],
            "peGrupDeCalitate": {
                str(group): int(rows.nume_hash.nunique()) for group, rows in persons.groupby("grup")
            },
            "cotaTopFilerilor": {
                "top1la_suta": top_share(0.01),
                "top5la_suta": top_share(0.05),
            },
            # Counts, never members. A behavioural flag on an identity is still a statement
            # about an identity, and the number of them plus the share they carry is the whole
            # finding.
            "comportamentInstitutional": {
                "identitati": len(institutional),
                "dispute": int(by_filer[list(institutional)].sum()) if institutional else 0,
                "cotaDinCereri": (
                    round(float(by_filer[list(institutional)].sum()) / filed_total, 4)
                    if institutional and filed_total
                    else None
                ),
                "pragDisputa": INSTITUTIONAL_MIN_DISPUTES,
                "pragRecuperare": INSTITUTIONAL_RECOVERY_SHARE,
            },
        }

    # ---- stages ----------------------------------------------------------------------------
    # What `caiAtac` actually is, established by looking rather than by reading the field name.
    # Among cases carrying one, the case's own stadiuProcesual is overwhelmingly Apel, Recurs or
    # Contestaţie — and at judecătorii, where 99.8% of cases are Fond, only 0.7% carry one. The
    # list therefore describes the appeal that *brought the case to this court*, not appeals
    # lodged against its decision. Counting it per level and calling the result an appeal rate
    # would produce "73% at curtea de apel", which is close to a tautology: a case at a court of
    # appeal is usually an appeal.
    #
    # So the stage distribution is reported directly, from stadiuProcesual, where it means what
    # it says.
    stages = []
    for name, group in dosare.groupby("level"):
        counts = group.stadiu_procesual.replace("", "necunoscut").value_counts()
        stages.append(
            {
                "level": name,
                "dosare": int(len(group)),
                "stadii": {str(k): int(v) for k, v in counts.head(8).items()},
            }
        )
    stages.sort(key=lambda row: -row["dosare"])

    # ---- appeals, by following the case number upward --------------------------------------
    # The unique case number survives the move between courts — 10408/333/2026 is the same file
    # at Judecătoria Vaslui (Fond) and at Tribunalul Vaslui (Contestaţie). So the rate that was
    # actually wanted is recoverable: of the first-instance cases, how many reappear higher up.
    #
    # It is a floor, not a rate, and for two reasons. Both stages have to be inside the crawl
    # window, and an appeal is filed months after the case is registered, so a narrow window
    # sees almost none of them. And both have to still be visible, which the survival curve does
    # not guarantee. `bazaComparabila` records how much of the first-instance set was actually
    # in a position to be matched.
    rank = {"judecătorie": 1, "tribunal": 2, "tribunal specializat": 2, "curte de apel": 3}
    dosare["rank"] = dosare.level.map(rank)
    higher = (
        dosare[dosare.stadiu_procesual.replace("", "necunoscut") != "Fond"]
        .groupby("numar")["rank"]
        .max()
    )
    fond = dosare[dosare.stadiu_procesual == "Fond"]
    appeals = []
    for name, group in fond.groupby("level"):
        own = rank.get(name, 0)
        matched = group.numar.map(higher)
        escalated = int((matched > own).sum())
        appeals.append(
            {
                "level": name,
                "dosareFond": int(len(group)),
                "reganiteLaOInstantaSuperioara": escalated,
                "shareMinima": round(escalated / len(group), 4) if len(group) else None,
            }
        )
    appeals.sort(key=lambda row: -row["dosareFond"])

    # ---- aging of what is pending ----------------------------------------------------------
    # "Pending" here means no disposition recorded on any termen. That is the portal's view, not
    # the court's register: a case closed on paper but not yet replicated reads as pending.
    decided = set(sedinte[sedinte.solutie.replace("", pd.NA).notna()].dosar_numar)
    pending = dosare[~dosare.numar.isin(decided)]
    age_days = (now - pending.registered).dt.days
    aging = []
    for low, high in AGE_BUCKETS:
        mask = age_days >= low if high is None else (age_days >= low) & (age_days < high)
        aging.append(
            {
                "from": low,
                "to": high,
                "dosare": int(mask.sum()),
                "share": round(float(mask.sum()) / len(pending), 4) if len(pending) else None,
            }
        )

    # ---- who litigates ---------------------------------------------------------------------
    # Legal persons only — natural persons never carry a name out of the importer. Grouped on
    # the folded name so one institution spelled two ways counts once.
    named = parti[parti.nume.notna()]
    litiganti = []
    for fold, group in named.groupby("nume_fold"):
        calitati = group.calitate.replace("", "necunoscut").value_counts().head(4)
        roles = {str(k): int(v) for k, v in calitati.items()}
        litiganti.append(
            {
                "nume": str(group.nume.mode().iat[0]),
                "numeFold": str(fold),
                "aparitii": int(len(group)),
                "dosare": int(group.dosar_numar.nunique()),
                "calitati": roles,
            }
        )
    litiganti.sort(key=lambda row: -row["aparitii"])

    # ---- disposition vocabulary ------------------------------------------------------------
    solutii_raw = sedinte.solutie.replace("", None).dropna()
    solutii = []
    for key, group in solutii_raw.groupby(solutii_raw.map(normalise_solutie)):
        solutii.append(
            {"solutie": str(group.mode().iat[0]), "key": str(key), "termene": int(len(group))}
        )
    solutii.sort(key=lambda row: -row["termene"])

    return {
        "snapshot": {
            "crawledAt": crawled_at,
            "institutieDinFisier": bool(hearings_carry_court),
            "instante": int(dosare.institutie.nunique()),
            "dosare": int(total),
            "sedinte": int(len(sedinte)),
            "parti": int(len(parti)),
            "caiAtac": int(len(cai_atac)),
            "registeredFrom": str(dosare.registered.min().date()),
            "registeredTo": str(dosare.registered.max().date()),
        },
        "levels": levels,
        "courts": courts,
        "caseTypes": case_types,
        "termene": termene,
        "durata": {
            "cohortMonths": cohort_months,
            "cohortFrom": cohort_start.date().isoformat(),
            "byLevel": durata_by_level,
            "byCategorie": durata_by_type,
        },
        "primulTermen": primul_termen,
        "amanari": amanari,
        "penal": penal_summary,
        "concentrare": concentrare,
        "gradientArhivare": gradient,
        "stadii": stages,
        "caleDeAtacDeclarata": appeals,
        "vechimeDosarePeRol": aging,
        "litiganti": litiganti[:200],
        "solutii": solutii[:50],
    }


LIMITATIONS = [
    {
        "id": "portalul-nu-e-arhiva",
        "text": (
            "Portalul ține dosarele aflate încă pe rol și pe cele închise recent, iar instanțele "
            "le scot pe măsură ce le arhivează. La Tribunalul Timiș, din martie 2019 mai sunt "
            "vizibile nouă dosare, din martie 2023 sunt 732. Ce se vede din anii vechi este deci "
            "un eșantion de supraviețuire: dosarele vechi sunt vizibile tocmai pentru că au "
            "durat. Orice cifră care seamănă cu o durată este umflată, cu atât mai mult cu cât "
            "cohorta e mai veche."
        ),
        "severity": "blocking",
        "affects": ["termene", "vechimeDosarePeRol", "incarcatura"],
    },
    {
        "id": "nu-se-calculeaza-durata",
        "text": (
            "Din acest motiv fișierul nu conține durata medie de soluționare, rata de "
            "soluționare sau timpul până la prima hotărâre. Ele cer ca dosarul închis repede să "
            "fie încă în date, iar el nu este. Se pot calcula abia după ce se acumulează "
            "suficiente instantanee zilnice pentru a urmări dosarele intrând și ieșind."
        ),
        "severity": "blocking",
        "affects": ["termene"],
    },
    {
        "id": "termenele-sunt-pe-cohorta",
        "text": (
            "Intervalele dintre termene se calculează doar pentru dosarele înregistrate în "
            "cohorta recentă declarată în `termene.cohortFrom`, unde aproape nimic nu a apucat "
            "să fie arhivat. Rămâne o distorsiune: dosarele cele mai rapide din cohortă pot fi "
            "deja plecate. Este mai mică decât pe toată perioada, nu absentă."
        ),
        "severity": "material",
        "affects": ["termene"],
    },
    {
        "id": "fara-nume-de-judecatori",
        "text": (
            "Serviciul web nu publică numele judecătorilor, ci doar codul completului, iar "
            "codurile diferă ca format între instanțe. Încărcătura se poate raporta pe complet, "
            "nu pe judecător, iar completurile nu se pot compara între instanțe."
        ),
        "severity": "material",
        "affects": ["incarcatura", "levels", "courts"],
    },
    {
        "id": "partile-persoane-fizice-sunt-anonimizate",
        "text": (
            "Persoanele fizice sunt reduse la un hash înainte de scrierea datelor, iar în "
            "dosarele penale nu se publică niciun nume. Lista de litiganți conține deci numai "
            "persoane juridice, care nu intră sub incidența RGPD."
        ),
        "severity": "note",
        "affects": ["litiganti"],
    },
    {
        "id": "identitatea-institutiilor-e-doar-partial-rezolvata",
        "text": (
            "Numele se grupează după forma fără diacritice, ceea ce unește „AGENŢIA” cu "
            "„AGENTIA”, dar nu unește prescurtările cu formele desfășurate. O instituție scrisă "
            "și „CASA DE PENSII SECTORIALĂ A M.A.I.” apare încă separat de forma întreagă, deci "
            "aparițiile sunt un prag de jos."
        ),
        "severity": "material",
        "affects": ["litiganti"],
    },
    {
        "id": "caile-de-atac-din-dosar-nu-sunt-rata-de-atac",
        "text": (
            "Lista `caiAtac` din serviciul web descrie calea de atac prin care dosarul a ajuns "
            "la instanța respectivă, nu contestațiile împotriva hotărârii ei: printre dosarele "
            "care o poartă, stadiul propriu este covârșitor Apel, Recurs sau Contestație, iar la "
            "judecătorii, unde 99,8% din dosare sunt în Fond, doar 0,7% o poartă. Raportarea ei "
            "pe instanță ar da „73% la curtea de apel”, ceea ce este aproape o tautologie. "
            "Câmpul de dată al acestei liste este gol în toate înregistrările citite."
        ),
        "severity": "material",
        "affects": ["caleDeAtacDeclarata", "stadii"],
    },
    {
        "id": "rata-de-atac-e-un-prag-de-jos",
        "text": (
            "Numărul unic de dosar se păstrează când cauza urcă, deci atacul se poate urmări "
            "legând același număr la o instanță superioară. Rezultatul este un prag de jos: "
            "ambele stadii trebuie să fie în fereastra colectată și ambele trebuie să fie încă "
            "vizibile pe portal. O fereastră scurtă nu prinde apelurile, fiindcă ele se "
            "declară la luni după înregistrarea fondului."
        ),
        "severity": "material",
        "affects": ["caleDeAtacDeclarata"],
    },
    {
        "id": "hashul-identifica-un-nume-nu-o-persoana",
        "text": (
            "Persoanele fizice sunt reduse la un hash al numelui, iar numele este normalizat "
            "intenționat, ca „ŞTEFAN” și „STEFAN” să fie același lucru. Consecința este că toți "
            "cei care poartă același nume primesc același hash: nu există CNP și nici dată de "
            "naștere care să îi despartă. Numărul de dosare pe identitate este deci un prag de "
            "sus, nu un număr de persoane."
        ),
        "severity": "blocking",
        "affects": ["concentrare"],
    },
    {
        "id": "aparitiile-dese-nu-inseamna-abuz",
        "text": (
            "A apărea des nu înseamnă a face ceva. La o singură judecătorie, a treia identitate "
            "ca mărime era pârât în 124 de cauze de fond funciar, iar a opta era parte vătămată "
            "în 56. O listă a „celor cu multe dosare” pune victima și pârâtul lângă reclamant. "
            "De aceea cifrele sunt împărțite pe grup de calitate și nu se publică nimic pe "
            "identitate."
        ),
        "severity": "blocking",
        "affects": ["concentrare"],
    },
    {
        "id": "persoanele-juridice-ajung-in-galeata-fizica",
        "text": (
            "Clasificatorul de părți greșește în siguranță: ce nu e sigur persoană juridică e "
            "tratat ca persoană fizică și anonimizat. Așa că cele mai mari identități „fizice” "
            "sunt firme pe care nu le-a putut numi — cea mai mare de la o judecătorie a depus "
            "1.183 de cereri de valoare redusă. Steagul de comportament instituțional măsoară "
            "tiparul, nu numele."
        ),
        "severity": "material",
        "affects": ["concentrare"],
    },
    {
        "id": "pe-rol-inseamna-fara-solutie-in-portal",
        "text": (
            "„Pe rol” înseamnă aici că niciun termen din portal nu poartă soluție. Replicarea "
            "din ECRIS se face nocturn, deci un dosar închis și nereplicat încă apare pe rol."
        ),
        "severity": "note",
        "affects": ["vechimeDosarePeRol"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None, help="directory of parquet parts")
    parser.add_argument("--release", default=None, help="release tag, or 'latest'")
    parser.add_argument(
        "--cohort-months", type=int, default=12, help="registration window for interval stats"
    )
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

        dosare, sedinte, parti, cai_atac = load(input_dir)
        coverage = sorted(input_dir.glob("coverage*.json"))
        crawled_at = datetime.now().isoformat(timespec="seconds")
        complete = None
        if coverage:
            report = json.loads(coverage[-1].read_text(encoding="utf-8"))
            crawled_at = report.get("crawledAt", crawled_at)
            complete = report.get("complete")

        body = build(dosare, sedinte, parti, cai_atac, args.cohort_months, crawled_at)

    body["snapshot"]["coverageComplete"] = complete
    document = {
        "$schema": "../schema/portal-stats.schema.json",
        "id": "portal-stats",
        "title": "Încărcătură, tipuri de cauze și termene, din dosarele publicate de instanțe",
        "publisher": "Ministerul Justiției — portal.just.ro (ECRIS)",
        "period": f"{body['snapshot']['registeredFrom']} — {body['snapshot']['registeredTo']}",
        "provenance": {
            "source": "portal-just-ro",
            "locator": (
                f"serviciul web portalquery.just.ro/Query.asmx, instantaneu "
                f"{body['snapshot']['crawledAt']}, {body['snapshot']['instante']} instanțe"
            ),
            "confidence": "derived",
            "note": (
                "Agregat din dosarele individuale colectate de import_portal.py. Nu conține "
                "durate de soluționare — vezi limitarea nu-se-calculeaza-durata."
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
        f"{snapshot['dosare']} dosare from {snapshot['instante']} instanțe -> {out.name}"
        f" ({out.stat().st_size / 1000:.0f} kB)"
    )
    print(f"  termene cohort: {body['termene']['dosareCuTermene']} dosare with hearings")
    if complete is False:
        print("  coverage reports the crawl was incomplete", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
