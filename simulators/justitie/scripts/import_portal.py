"""Case-level workload from the courts' own portal, instead of CSM's annual averages.

Every workload number in this simulator so far — `build_incarcatura.py`, `import_eficienta.py` —
comes from CSM aggregates: one row per court per year, already averaged by the body whose
performance the average describes. That is the only public source for the shape of the docket,
and it cannot answer the questions the reform argument actually turns on. How long is a termen,
in days, and does it differ between a judecătorie and a curte de apel? How many termene does a
case take before a solution? Where does the delay sit — in getting the first hearing, or in the
intervals after it?

portal.just.ro answers all three, because it publishes the case file itself. The Ministry
documents a SOAP service at http://portalquery.just.ro/query.asmx returning, per dosar, the list
of parties, the list of termene with their solutions, and the list of appeals. This script reads
it.

Two properties of that source govern everything below, and both were measured rather than
assumed.

**The portal is not an archive.** It holds cases that are still live plus those recently closed;
resolved cases fall off as courts archive them. Counting the cases registered in March of each
year that are still visible today, at Tribunalul Timiş:

    2018     8      2022    125
    2019     9      2023    732
    2020    11      2024   1000  (truncated at the service cap)
    2021    44      2025   1000  (truncated)

That is a survival curve, not a retention cutoff. It has one consequence that matters more than
any other in this file: **a single snapshot cannot measure duration.** Ask a snapshot how long a
2019 case took and it answers using the nine cases from 2019 slow enough to still be pending —
every case that finished on time has been archived and is invisible. The answer will be stable
across reruns and wildly wrong, which is the worst kind of wrong. So this script does not compute
durations. It writes dated snapshots, and duration becomes answerable only once enough snapshots
have accumulated to watch cases enter and leave. Starting the series is the point; the data for
any day not yet crawled is gone for good.

**The service truncates silently at 1000 rows.** The Ministry documents the cap ("lista rezultată
la o interogare va conţine maxim 1000 dosare") but the response carries no total and no
continuation token, so a full page is indistinguishable from a coincidentally-exact one, and a
capped response has to be thrown away rather than partially kept. Any response of exactly 1000 is
therefore treated as truncated. A crawl that silently lost rows would understate exactly the
busiest courts, which are the ones the reform is about.

Because a capped fetch is wasted work, the crawler sizes each window from the density of the one
before it rather than bisecting blindly — see `crawl_court`. Courts differ by three orders of
magnitude between a Bucharest tribunal and a rural judecătorie, and by a similar factor between
2024 and 2018 at the same court, so no fixed window is right for long.

One caveat on the query itself. The Ministry's documentation states that at least one of
`numarDosar`, `obiectDosar` or `numeParte` must be supplied. The service does not enforce this —
institution plus period returns results — and that undocumented behaviour is what makes a
systematic crawl possible at all. If it is ever enforced, this crawl stops working and the
documented path is `CautareSedinte`, which takes institution plus hearing date and needs no such
parameter; it yields case numbers per hearing day, which can then be fetched individually. That
fallback costs roughly one call per case instead of one per thousand, so it is not implemented
here, but it is the reason this is a recoverable dependency rather than a fatal one.

On names, see `classify_party` and `PENAL_CATEGORIES` below. The short version: the portal states
its own lawful basis is the courts' legal obligation, and justifies publishing names on the
ground that the data is "adecvate, pertinente și neexcesive [...] iar procesul este pe rol" — a
justification that is explicitly bounded to the life of the case. A permanent mirror of those
names is a different purpose with no basis of its own, and it would defeat the removal route the
portal directs people to. Legal persons are outside the GDPR entirely and are kept in full, which
is also where the interesting findings are: which institutions litigate, against whom, and how
often. Natural persons are reduced to a salted hash before anything is written to disk.

That covers the structured fields, which are anonymised by construction. It does not cover
`solutieSumar`, and this is the one place where the file is safe only because of how it is
invoked. The summary is prose a clerk typed, and prose names people: over 1,480 non-criminal
summaries from one month of three courts, 3.6% contain a name-shaped string the classifier reads
as a natural person. There is no reliable way to redact that with a word list. So `--no-summaries`
is mandatory for anything published, and .github/workflows/portal-snapshot.yml passes it; the
field is kept available for local analysis, on a machine that is not publishing, because the
disposition text is genuinely useful and destroying it here would only push someone to re-crawl.

Usage:
    export PORTAL_HASH_SALT=...            # required; keep secret, keep stable
    uv run --with pyarrow python scripts/import_portal.py --courts TribunalulTIMIS --months 3
    uv run --with pyarrow python scripts/import_portal.py --all --since 2023-01-01 --no-summaries
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "portal"
WSDL_NS = "portalquery.just.ro"
ENDPOINT = "http://portalquery.just.ro/Query.asmx"

# Documented by the Ministry on portal.just.ro/SitePages/acces.aspx and confirmed by probe.
RESULT_CAP = 1000

# Politeness. This is a single state-run ASP.NET 3.5 service with no second endpoint; getting the
# crawler blocked ends the project. Measured latency runs 0.1-12s per call depending on result
# size, so the delay is a small share of total time and there is no reason to shave it.
DELAY_SECONDS = 0.5
MAX_RETRIES = 4
TIMEOUT_SECONDS = 240

# The window is bisected on time rather than on whole days, so a court that registers more than
# 1000 cases in one day is still resolvable. Below this the window is treated as irreducible and
# the truncation is reported instead of silently kept.
MIN_WINDOW = timedelta(minutes=1)

# What each call aims to return. Below RESULT_CAP with enough margin that a court whose filing
# rate jumps — the Monday after a holiday, a bulk registration — does not overshoot and cost a
# discarded fetch. Raising it toward 1000 saves calls until it doesn't, and a capped response is
# worth two ordinary ones because the rows are thrown away.
TARGET_ROWS = 600

# Where a court starts before anything is known about it, and the widest window the walker will
# ask for.
#
# Narrow, and this is the whole trick. The two ways of being wrong do not cost the same: a window
# that is too small returns rows and wastes a little time, while a window that is too big caps and
# every row it fetched is discarded. Starting at a year and shrinking cost ten capped fetches on
# one Bucharest month — 30 calls where blind bisection took 22. Starting at three days and growing
# pays a handful of cheap probes instead, and a quiet court reaches the ceiling in three steps
# because empty windows grow eightfold.
#
# The ceiling stops a court with three surviving cases from asking for a whole decade in one call
# and losing the ability to report which part of it failed.
INITIAL_WINDOW = timedelta(days=3)
EMPTY_GROWTH = 8
MAX_WINDOW = timedelta(days=366 * 4)


# --------------------------------------------------------------------------------------------
# Party classification
# --------------------------------------------------------------------------------------------

# Markers that identify a party as a legal person. GDPR Recital 14 puts legal persons outside the
# Regulation, so these names are kept verbatim — they carry the findings this simulator wants
# (which ministries, agencies, banks and municipalities appear, in what role, how often).
#
# Matching is on a diacritic-folded, uppercased name, against whole words. Every token here has
# to be one that cannot occur inside a Romanian personal name, because a false "legal" publishes
# somebody's name while a false "natural" only over-anonymises a company. Those errors are not
# symmetric, so the list is deliberately short of obvious candidates:
#
#   ROMANIA   is a given name ("IONESCU MARIA-ROMANIA"), so it appears only in LEGAL_PERSON_PHRASES
#   RA IF II  are two-letter tokens that collide with initials in ECRIS name strings
#   ROMAN     is a common surname and is not a marker at all
#
# The dotted abbreviations survive because `fold` keeps "." as a word character.
LEGAL_PERSON_MARKERS = frozenset(
    """
    SRL SA SNC SCS SCA PFA NFP ONG IFN
    SOCIETATEA COMPANIA REGIA INTREPRINDEREA INTREPRINDERE COOPERATIVA
    MINISTERUL AGENTIA AUTORITATEA ADMINISTRATIA DIRECTIA
    INSPECTORATUL INSPECTIA OFICIUL SECRETARIATUL CANCELARIA GUVERNUL PARLAMENTUL
    PRIMARIA MUNICIPIUL ORASUL COMUNA JUDETUL SECTORUL CONSILIUL PREFECTUL PREFECTURA
    INSTITUTUL INSTITUTIA CENTRUL CASELOR SPITALUL POLICLINICA
    SCOALA LICEUL COLEGIUL UNIVERSITATEA GRADINITA
    ASOCIATIA FUNDATIA FEDERATIA SINDICATUL UNIUNEA PATRONATUL
    BANCA BRD BCR RAIFFEISEN UNICREDIT
    ASIGURARI ASIGURARE LEASING FACTORING RECUPERARI
    CABINETUL BIROUL NOTARIAL EXECUTORUL
    ANAF DGRFP AJFP CNAS CASMB ISJ IPJ ITM APIA AFIR ANRE ANCOM ANPC
    ELECTRICA ENEL ENGIE DISTRIGAZ HIDROELECTRICA TRANSELECTRICA TRANSGAZ ROMGAZ PETROM
    ORANGE VODAFONE TELEKOM
    SC. S.C. S.R.L. S.A. P.F.A. I.I. I.F.
    """.split()
)

# Multi-word markers. Two kinds: suffixes ECRIS appends to a company mid-restructuring, and
# phrases whose individual words are too name-like to be listed above.
LEGAL_PERSON_PHRASES = (
    "IN INSOLVENTA",
    "IN FALIMENT",
    "IN REORGANIZARE",
    "IN LICHIDARE",
    "PRIN LICHIDATOR",
    "PRIN ADMINISTRATOR JUDICIAR",
    "STATUL ROMAN",
    "ROMANIA PRIN",
    "CASA DE",
    "CASA NATIONALA",
    "CASA JUDETEANA",
    "CAMERA DE COMERT",
    # Bare "SC" is omitted from the word list because it collides with initials; as a prefix
    # followed by a space it is unambiguously the company abbreviation.
    "SC ",
)

# Case categories where party names are dropped outright rather than hashed. GDPR Art. 10 limits
# processing of data relating to criminal offences to processing under official authority or
# authorised by law; a public statistics site has neither, and no hashing scheme cures a
# prohibition on processing. The list is matched case-insensitively as a substring of
# `categorieCaz`, which is a controlled vocabulary in ECRIS but not a stable enum.
PENAL_CATEGORIES = ("penal", "minori si familie/penal", "executare penala")

_DIACRITIC_MAP = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaissttAAISSTT")


def fold(name: str) -> str:
    """Uppercase and strip diacritics, including the two Unicode encodings of ș and ț."""
    folded = name.translate(_DIACRITIC_MAP)
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.upper()


def classify_party(name: str) -> str:
    """Return "legal" or "natural" for a party name.

    Fails closed: a name that is not confidently a legal person is classified natural and will be
    hashed. The cost of a false "natural" is a company needlessly anonymised; the cost of a false
    "legal" is publishing someone's name. Those are not symmetric.
    """
    folded = fold(name)
    if any(phrase in folded for phrase in LEGAL_PERSON_PHRASES):
        return "legal"
    words = set(re.split(r"[^A-Z0-9.]+", folded)) - {""}
    if words & LEGAL_PERSON_MARKERS:
        return "legal"
    return "natural"


def hash_name(name: str, salt: str) -> str:
    """Salted digest of a folded party name.

    Folded first so that "ŞTEFAN" and "STEFAN" — ECRIS holds both — collapse to one identity.
    Salted because a bare hash of a name is reversible against any list of Romanian names, which
    is to say against the electoral roll. The salt must be secret and must stay constant, or the
    same person gets a new identifier every crawl and the panel structure is lost.
    """
    return hashlib.blake2b(f"{salt}\x00{fold(name)}".encode(), digest_size=16).hexdigest()


# --------------------------------------------------------------------------------------------
# SOAP transport
# --------------------------------------------------------------------------------------------


class PortalError(RuntimeError):
    pass


def _envelope(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<soap:Body>{body}</soap:Body></soap:Envelope>"
    ).encode()


def call(body: str, action: str) -> str:
    """POST one SOAP call, retrying on transport errors with exponential backoff."""
    request = urllib.request.Request(
        ENDPOINT,
        data=_envelope(body),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{WSDL_NS}/{action}",
            # An honest agent string. The service is public and the crawl is not hiding; if the
            # Ministry wants to rate-limit or contact whoever is doing this, they should be able
            # to tell it apart from a browser.
            "User-Agent": (
                "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms) "
                "statistical research crawler"
            ),
        },
    )
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(2**attempt)
    raise PortalError(f"{action} failed after {MAX_RETRIES} attempts: {last!r}")


# XML 1.0 forbids most control characters, and ECRIS free text contains them — clerks paste from
# Word, and the service re-emits the result as numeric character references without checking. A
# single `&#4;` inside one solutieSumar makes the whole response unparseable, which cost the first
# probe run most of one month of Tribunalul Bucureşti. The characters carry no information, so
# they are dropped rather than escaped.
_BAD_CHAR_REF = re.compile(r"&#(?:x([0-9a-fA-F]+)|([0-9]+));")
_BAD_RAW_CHAR = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _is_valid_xml_char(code: int) -> bool:
    return (
        code in (0x9, 0xA, 0xD)
        or 0x20 <= code <= 0xD7FF
        or 0xE000 <= code <= 0xFFFD
        or 0x10000 <= code <= 0x10FFFF
    )


def sanitize_xml(text: str) -> str:
    """Drop character references and raw bytes that XML 1.0 does not permit."""

    def replace(match: re.Match) -> str:
        hex_digits, decimal_digits = match.group(1), match.group(2)
        try:
            code = int(hex_digits, 16) if hex_digits else int(decimal_digits)
        except ValueError:
            return ""
        return match.group(0) if _is_valid_xml_char(code) else ""

    return _BAD_RAW_CHAR.sub("", _BAD_CHAR_REF.sub(replace, text))


def _text(element, tag: str) -> str:
    found = element.find(f"{{{WSDL_NS}}}{tag}")
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def search_dosare(institutie: str, start: datetime, stop: datetime) -> list:
    """One CautareDosare call over a registration-date window. Returns raw <Dosar> elements."""
    body = (
        f'<CautareDosare xmlns="{WSDL_NS}">'
        f"<institutie>{institutie}</institutie>"
        f"<dataStart>{start.isoformat(timespec='seconds')}</dataStart>"
        f"<dataStop>{stop.isoformat(timespec='seconds')}</dataStop>"
        f"</CautareDosare>"
    )
    xml = call(body, "CautareDosare")
    try:
        root = ElementTree.fromstring(sanitize_xml(xml))
    except ElementTree.ParseError as exc:
        raise PortalError(f"unparseable response for {institutie} {start}..{stop}: {exc}") from exc
    fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
    if fault is not None:
        detail = fault.findtext("faultstring")
        raise PortalError(f"SOAP fault for {institutie} {start}..{stop}: {detail}")
    return root.findall(f".//{{{WSDL_NS}}}Dosar")


# --------------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------------


@dataclass
class Tables:
    dosare: list = field(default_factory=list)
    sedinte: list = field(default_factory=list)
    parti: list = field(default_factory=list)
    cai_atac: list = field(default_factory=list)


def extract(dosar, salt: str, tables: Tables, keep_summaries: bool) -> None:
    """Flatten one <Dosar> into the four tables, anonymising as it goes.

    Party names never reach `tables` in raw form unless the party is a legal person in a
    non-criminal case. There is deliberately no option to keep them: a flag that disables the
    anonymisation is a flag that will eventually be set.
    """
    numar = _text(dosar, "numar")
    institutie = _text(dosar, "institutie")
    categorie = _text(dosar, "categorieCaz")
    is_penal = any(marker in categorie.casefold() for marker in PENAL_CATEGORIES)

    parti = dosar.findall(f"{{{WSDL_NS}}}parti/{{{WSDL_NS}}}DosarParte")
    tables.dosare.append(
        {
            "numar": numar,
            "numar_vechi": _text(dosar, "numarVechi"),
            "data": _text(dosar, "data"),
            "institutie": institutie,
            "departament": _text(dosar, "departament"),
            "categorie_caz": categorie,
            "stadiu_procesual": _text(dosar, "stadiuProcesual"),
            "obiect": _text(dosar, "obiect"),
            "data_modificare": _text(dosar, "dataModificare"),
            "n_parti": len(parti),
            "is_penal": is_penal,
        }
    )

    for parte in parti:
        nume = _text(parte, "nume")
        if not nume:
            continue
        tip = classify_party(nume)
        publishable = tip == "legal" and not is_penal
        tables.parti.append(
            {
                "dosar_numar": numar,
                "institutie": institutie,
                "tip": tip,
                # Kept only for legal persons outside criminal cases. Everyone else is a hash.
                "nume": nume if publishable else None,
                # ECRIS holds the same institution under several spellings — "MINISTERUL
                # FINANŢELOR" and "MINISTERUL FINANTELOR" are separate strings, as are the two
                # encodings of ș and ț. Counting on the raw name splits one ministry into two
                # rows and understates both. This is the column to group by; `nume` is for
                # display. It is not full entity resolution — that needs a hand-kept alias
                # table, because "CASA DE PENSII SECTORIALĂ A M.A.I." folds to something else
                # again — but it removes the error that is purely an encoding artefact.
                "nume_fold": fold(nume) if publishable else None,
                "nume_hash": None if publishable else hash_name(nume, salt),
                "calitate": _text(parte, "calitateParte"),
            }
        )

    for sedinta in dosar.findall(f"{{{WSDL_NS}}}sedinte/{{{WSDL_NS}}}DosarSedinta"):
        summary = _text(sedinta, "solutieSumar")
        tables.sedinte.append(
            {
                "dosar_numar": numar,
                "institutie": institutie,
                "complet": _text(sedinta, "complet"),
                "data": _text(sedinta, "data"),
                "ora": _text(sedinta, "ora"),
                "solutie": _text(sedinta, "solutie"),
                # The free-text summary is most of the payload by bytes and the only place an
                # unredacted name can hide in a criminal case. Dropped there, optional elsewhere.
                "solutie_sumar": (summary if keep_summaries and not is_penal else None),
                "data_pronuntare": _text(sedinta, "dataPronuntare"),
                "document_sedinta": _text(sedinta, "documentSedinta"),
                "numar_document": _text(sedinta, "numarDocument"),
                "data_document": _text(sedinta, "dataDocument"),
            }
        )

    for cale in dosar.findall(f"{{{WSDL_NS}}}caiAtac/{{{WSDL_NS}}}DosarCaleAtac"):
        declaratoare = _text(cale, "parteDeclaratoare")
        tip = classify_party(declaratoare) if declaratoare else "natural"
        publishable = tip == "legal" and not is_penal
        tables.cai_atac.append(
            {
                "dosar_numar": numar,
                "institutie": institutie,
                "parte_tip": tip,
                "parte_nume": declaratoare if publishable else None,
                "parte_hash": (
                    None if publishable or not declaratoare else hash_name(declaratoare, salt)
                ),
                "tip_cale_atac": _text(cale, "tipCaleAtac"),
                "data": _text(cale, "data"),
            }
        )


# --------------------------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------------------------


@dataclass
class CrawlStats:
    calls: int = 0
    dosare: int = 0
    truncated_windows: list = field(default_factory=list)
    failed_windows: list = field(default_factory=list)
    caps_hit: int = 0


def next_window(rows: int, span: timedelta) -> timedelta:
    """Choose the next window from what the last one returned.

    The service gives no total and no cursor, so the only signal about how busy a court is is how
    many rows the previous window produced. Rows per day from that window, projected at
    TARGET_ROWS, is the width that should land just under the cap next time.
    """
    days = max(span.total_seconds() / 86400, 1 / 24)
    if not rows:
        # Nothing here. Reach further rather than stepping through empty years one at a time —
        # this is most of the pre-2023 range, where a court has single-digit surviving cases.
        return min(span * EMPTY_GROWTH, MAX_WINDOW)
    density = rows / days
    wanted = timedelta(days=TARGET_ROWS / density)
    # Growth is damped to twice the current width. Filing rates are not smooth — a window
    # covering a weekend returns almost nothing, which projects to a window several times too
    # wide, which caps and throws its rows away. Undamped, a busy court oscillates between
    # windows that are too small and fetches that are discarded. Shrinking is left undamped
    # because shrinking too far only costs an extra cheap call.
    return max(MIN_WINDOW, min(wanted, span * 2, MAX_WINDOW))


def crawl_court(
    institutie: str,
    since: datetime,
    until: datetime,
    salt: str,
    tables: Tables,
    stats: CrawlStats,
    keep_summaries: bool,
    seen: set,
) -> None:
    """Walk one court's registrations, sizing each window from the density of the last.

    This replaces a fixed month window with blind bisection, which was correct but wasteful in
    both directions. On a busy court a capped month was split in half, both halves refetched,
    and often split again — 22 calls for one Bucharest month, every capped response thrown away
    because a truncated result cannot be told apart from a complete one row by row. On the quiet
    pre-2023 years it walked month by month through courts holding eight surviving cases a year.

    Sizing from observed density fixes both: after any successful window the crawler knows this
    court's rows per day and picks a width that should land near TARGET_ROWS, so a busy court
    gets short windows and a quiet one gets long ones without either being discovered by trial
    and error. Bisection survives only as the recovery path when a window still caps.
    """
    cursor = since
    window = INITIAL_WINDOW
    while cursor < until:
        stop = min(cursor + window, until)
        stats.calls += 1
        found = search_dosare(institutie, cursor, stop)
        time.sleep(DELAY_SECONDS)
        span = stop - cursor

        if len(found) >= RESULT_CAP:
            stats.caps_hit += 1
            if span > MIN_WINDOW:
                # Discard and retry the same start narrower. A quarter rather than a half: the
                # overshoot is at least 1000 against a target of 600, so halving would often cap
                # again and cost a second wasted fetch.
                window = max(span / 4, MIN_WINDOW)
                continue
            # Irreducible: more than RESULT_CAP cases share the smallest window we will ask for.
            # The rows we did get are kept — a partial window beats a hole — and the loss is
            # recorded so the coverage report can name the court and the interval.
            stats.truncated_windows.append(
                {"institutie": institutie, "start": cursor.isoformat(), "stop": stop.isoformat()}
            )

        for dosar in found:
            numar = _text(dosar, "numar")
            key = (institutie, numar)
            if key in seen:
                continue
            seen.add(key)
            stats.dosare += 1
            extract(dosar, salt, tables, keep_summaries)

        window = next_window(len(found), span)
        cursor = stop + timedelta(seconds=1)


def load_courts() -> list:
    """The 246 `Institutie` enum values, read from the live WSDL so the list cannot drift."""
    with urllib.request.urlopen(f"{ENDPOINT}?wsdl", timeout=TIMEOUT_SECONDS) as response:
        wsdl = response.read().decode("utf-8", "replace")
    block = re.search(r'<s:simpleType name="Institutie">(.*?)</s:simpleType>', wsdl, re.S)
    if not block:
        raise PortalError("Institutie enum not found in WSDL")
    return re.findall(r'value="([^"]+)"', block.group(1))


def court_weights() -> dict:
    """How much work each court is, for splitting the crawl evenly.

    CSM's published volume of activity, which is the only per-court measure of size available
    before the crawl that is about to measure it. It does not have to be accurate — it has to
    rank courts, and a court with ten times the volume takes roughly ten times the calls.

    Absent rather than fatal: this file is in the repository, but a crawl that can reach the
    portal and not its own checkout should still run, one shard at a time if it must.
    """
    path = ROOT / "data" / "instante-localizate-2025.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        _shard_key(court["name"]): court.get("volume") or 0 for court in document.get("courts", [])
    }


def _shard_key(name: str) -> str:
    """Fold a court name to compare the CSM register against the portal's enum."""
    folded = name.translate(str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaissttAAISSTT"))
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return re.sub(r"[^A-Za-z0-9]", "", folded).upper()


def shard_courts(courts: list, shard: int, shards: int, weights: dict | None = None) -> list:
    """Split the court list into `shards` parts of similar total size, and return one.

    The previous rule was round-robin, on the stated ground that the enum runs roughly from
    largest court to smallest and contiguous slices would put every Bucureşti tribunal on one
    runner. The premise is right; the remedy does not follow from it. Round-robin over a *sorted*
    list hands shard 0 the largest court of every group of twelve and shard 11 the smallest, so
    the imbalance it was meant to prevent is reproduced in miniature, twenty times over.

    Measured on the 2026-09-05 snapshot, the twelve shards carried between 237.400 and 428.061 of
    CSM volume — a spread of 1,80× — and the two heaviest were the two that hit the six-hour
    ceiling and returned nothing, twice, on the two longest backfills attempted. That is what
    lost forty-one courts from the published snapshot.

    So the split is by weight: courts are placed largest first into whichever part is currently
    lightest, which is the standard greedy bound and brings the spread to within a few percent.
    Same number of runners and the same load on the portal — only the tail gets shorter.

    A court the register does not name takes the median weight rather than zero. Zero would treat
    every unmatched court as free, which is how a newly-added court would quietly rebuild the
    imbalance this exists to remove.
    """
    if shards <= 1:
        return list(courts)

    weights = weights if weights is not None else court_weights()
    known = sorted(value for value in weights.values() if value > 0)
    default = known[len(known) // 2] if known else 1

    def weigh(court: str) -> int:
        return weights.get(_shard_key(court), default)

    # Sorted by weight descending, then by name, so every runner computes the same assignment
    # from the same inputs without communicating.
    ordered = sorted(courts, key=lambda court: (-weigh(court), court))
    parts: list[list] = [[] for _ in range(shards)]
    totals = [0] * shards
    for court in ordered:
        lightest = min(range(shards), key=lambda index: (totals[index], index))
        parts[lightest].append(court)
        totals[lightest] += weigh(court)
    # Restored to enum order within the part: the crawl's own progress output reads better, and
    # nothing downstream depends on the order.
    position = {court: index for index, court in enumerate(courts)}
    return sorted(parts[shard], key=lambda court: position[court])


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------


def write_tables(tables: Tables, stamp: str, out_dir: Path) -> dict:
    import pyarrow  # noqa: PLC0415
    import pyarrow.parquet as parquet  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, rows in (
        ("dosare", tables.dosare),
        ("sedinte", tables.sedinte),
        ("parti", tables.parti),
        ("cai_atac", tables.cai_atac),
    ):
        path = out_dir / f"{name}-{stamp}.parquet"
        table = pyarrow.Table.from_pylist(rows) if rows else pyarrow.table({})
        parquet.write_table(table, path, compression="zstd", compression_level=9)
        sizes[name] = {"rows": len(rows), "bytes": path.stat().st_size}
    return sizes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--courts", nargs="*", help="Institutie enum values; default is a probe set"
    )
    parser.add_argument("--all", action="store_true", help="every court in the WSDL enum")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD registration date floor")
    parser.add_argument(
        "--months", type=int, default=1, help="months back from today if no --since"
    )
    parser.add_argument("--no-summaries", action="store_true", help="drop solutieSumar free text")
    parser.add_argument("--out", default=None, help="output directory")
    parser.add_argument("--shard", type=int, default=0, help="0-based shard index of --shards")
    parser.add_argument("--shards", type=int, default=1, help="total shards to split courts into")
    args = parser.parse_args()

    if not 0 <= args.shard < args.shards:
        parser.error(f"--shard must be in [0, {args.shards})")

    salt = os.environ.get("PORTAL_HASH_SALT")
    if not salt:
        print(
            "PORTAL_HASH_SALT is not set. Natural-person names are hashed with it, so an unset\n"
            "salt would either publish names or produce identifiers that change every run.\n"
            "Set it to a secret value and keep that value constant across crawls.",
            file=sys.stderr,
        )
        return 2

    until = datetime.now().replace(microsecond=0)
    if args.since:
        since = datetime.fromisoformat(args.since)
    else:
        since = until - timedelta(days=31 * args.months)

    if args.all:
        courts = load_courts()
    elif args.courts:
        courts = args.courts
    else:
        # One large, one mid, one small — enough to size a national crawl from.
        courts = ["TribunalulBUCURESTI", "TribunalulTIMIS", "JudecatoriaJIBOU"]

    # Split by weight rather than by position — see `shard_courts` for why round-robin over a
    # size-ordered enum reproduced the imbalance it was meant to prevent, and what that cost.
    if args.shards > 1:
        courts = shard_courts(courts, args.shard, args.shards)
        if not courts:
            print(f"shard {args.shard}/{args.shards} is empty", file=sys.stderr)
            return 0

    out_dir = Path(args.out) if args.out else OUT_DIR
    # Sharded runs write beside each other rather than over each other, so the parts can be
    # collected from parallel runners and concatenated without a rename step.
    stamp = until.date().isoformat()
    if args.shards > 1:
        stamp = f"{stamp}-part{args.shard:02d}of{args.shards:02d}"
    tables = Tables()
    report = {
        "crawledAt": until.isoformat(),
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "resultCap": RESULT_CAP,
        "courts": {},
        "note": (
            "Snapshot of cases visible on portal.just.ro at crawledAt. The portal drops cases as "
            "courts archive them, so this is a survival sample of past years, not a census. Do "
            "not compute case duration from a single snapshot."
        ),
    }

    started = time.time()
    for index, court in enumerate(courts, start=1):
        stats = CrawlStats()
        seen: set = set()
        try:
            crawl_court(court, since, until, salt, tables, stats, not args.no_summaries, seen)
        except PortalError as exc:
            # Recorded, not merely printed. A window that failed is a hole in the snapshot, and a
            # coverage report that omits it describes a crawl that did not happen.
            stats.failed_windows.append(
                {"start": since.isoformat(), "stop": until.isoformat(), "error": str(exc)}
            )
            print(f"  ! {court}: {exc}", file=sys.stderr)
        report["courts"][court] = {
            "calls": stats.calls,
            "dosare": stats.dosare,
            "capsHit": stats.caps_hit,
            "irreducibleTruncations": stats.truncated_windows,
            "failedWindows": stats.failed_windows,
        }
        print(
            f"[{index}/{len(courts)}] {court}: {stats.dosare} dosare, "
            f"{stats.calls} calls, {stats.caps_hit} caps"
            + (f", {len(stats.truncated_windows)} TRUNCATED" if stats.truncated_windows else "")
            + (f", {len(stats.failed_windows)} FAILED" if stats.failed_windows else "")
        )

    report["elapsedSeconds"] = round(time.time() - started, 1)
    report["totals"] = {
        "dosare": len(tables.dosare),
        "sedinte": len(tables.sedinte),
        "parti": len(tables.parti),
        "caiAtac": len(tables.cai_atac),
        "calls": sum(court["calls"] for court in report["courts"].values()),
    }
    report["parties"] = {
        "legalNamed": sum(1 for row in tables.parti if row["nume"]),
        "hashed": sum(1 for row in tables.parti if row["nume_hash"]),
        "penalCases": sum(1 for row in tables.dosare if row["is_penal"]),
    }
    report["files"] = write_tables(tables, stamp, out_dir)

    bytes_total = sum(entry["bytes"] for entry in report["files"].values())
    report["bytesPerDosar"] = round(bytes_total / max(len(tables.dosare), 1), 1)

    print(
        f"\n{report['totals']['dosare']} dosare, {report['totals']['calls']} calls, "
        f"{report['elapsedSeconds']}s, {bytes_total / 1e6:.2f} MB parquet "
        f"({report['bytesPerDosar']} B/dosar)"
    )
    print(
        f"parties: {report['parties']['legalNamed']} legal kept, "
        f"{report['parties']['hashed']} hashed, {report['parties']['penalCases']} penal cases"
    )

    incomplete = {
        court: entry
        for court, entry in report["courts"].items()
        if entry["failedWindows"] or entry["irreducibleTruncations"]
    }
    report["complete"] = not incomplete
    (out_dir / f"coverage-{stamp}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if incomplete:
        # Non-zero so a scheduled crawl cannot quietly publish a snapshot with holes in it.
        # The parquet is still written: a partial day is worth keeping as long as the report
        # beside it says which courts are short and why.
        names = ", ".join(incomplete)
        print(f"\nINCOMPLETE for {len(incomplete)} court(s): {names}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
