"""What a square metre of Romanian land is officially worth, read out of the notaries' grids.

Romania does not tax land on its value. The Fiscal Code taxes it on surface area times a
coefficient that depends on rank of locality and zone letter, and a hectare of Bucharest and a
hectare of Botoșani differ by a table, not by a market. A land value tax needs the thing the
Fiscal Code does not use: what the land is actually worth, per place.

That number exists, and the state already relies on it. Every year each Chamber of Public
Notaries publishes a *studiu de piață* fixing minimum orientative values used as the floor for
notary fees and transfer tax. It is the only valuation of Romanian land that is official,
national, published, and granular below the commune.

**These grids publish land directly, so nothing has to be inferred from building prices.**
That was worth checking before building on it: an earlier plan for this simulator assumed the
studies carried a construction-cost table, so that land could be recovered as a residual —
property price minus depreciated building. They do not. "Costuri de construcție" appears in
these documents only in prose, never as a grid. It does not matter, because the residual was
only ever a way to reach a number the studies print outright.

What Bacău's study prints, per village, in EURO/m²:

    CC   curți construcții        the residential plot — the one a land tax lands on
    V+L  vii și livezi            A    arabil
    P+F  pășuni și fânețe         TS   terenuri cu destinație specială
    TAPA + NP  under water, unproductive

and separately, per commune, the same categories for *extravilan* land. Towns are not listed
by village but as a matrix of category against zone letter, because a town's land value varies
across the town and a village's does not.

**The grid is a floor, not a market.** Its purpose is to stop a sale being declared below a
defensible minimum, so it sits under the transaction price by a margin that is neither
published nor constant between counties. Every number this importer produces inherits that,
and it travels with the data as a blocking limitation rather than a footnote: these values
rank places against each other far better than they measure any of them.

**Two granularities, deliberately kept apart.** Villages carry intravilan values of their own;
extravilan values are printed once per commune and apply to all its villages. Flattening the
two would silently invent per-village precision the document does not have, so extravilan is
attached to the commune and villages point at it.

The self-check is the study's own bookkeeping. Each annex opens with the roster of localities
in that court's circumscription, and the rural table numbers its communes from 1. So the
parse is checked twice against the document: every commune the roster names must appear in
the table, and the numbering must run without a gap. A first version silently lost communes
whose name wrapped across a line break; the roster check caught it as a named list rather
than as a total that happened to look plausible.

Usage:
    uv run python simulators/impozit-teren/scripts/import_ghid.py --chamber bacau
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forest_price import county_price  # noqa: E402
from pypdf import PdfReader  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.unnpr.ro/"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"

# The categories the studies use, longest token first so "P+F" is not eaten by "F", and
# "TAPA SI NP" is matched before "TS". Order here is the order the tables print them in.
CATEGORIES: list[tuple[str, str]] = [
    ("CC", "curti constructii"),
    ("V+L", "vii si livezi"),
    ("P+F", "pasuni si fanete"),
    ("TAPA SI NP", "terenuri sub ape si neproductive"),
    ("TS", "terenuri cu destinatie speciala"),
    ("A", "arabil"),
]
# Extravilan is printed as a bare header row of codes, in this order, in Bacău's study.
EXTRAVILAN_CODES = ["A", "V+L", "P+F", "CC", "AP", "DR", "NP"]

# Decimals are commas throughout these documents and thousands are grouped with a dot, as
# in the 5.500 EUR/ha of the forestry table. A space is NOT a thousands separator here, and
# treating it as one read Bacău's "256 123 48 35" as the single number 256123 — which lost
# the CC row of the county's largest city, because three values are not four zones.
NUMBER = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
# A dash marks a zone the locality does not have. Dărmănești has no zone D, and reading
# that as a missing row dropped its whole grid; reading it as zero would have invented
# free land. It is recorded as absent.
DASH = "-–—"
CELL = re.compile(rf"^(?:{NUMBER}|[{DASH}])$")


@dataclass(frozen=True)
class Study:
    """One chamber's land study, and the counties it speaks for."""

    key: str
    chamber: str
    counties: list[str]
    year: int
    path: str
    title: str
    # Chambers price in different currencies — CNP Bacău in euro, CNP Alba Iulia in lei — so
    # the unit belongs to the study rather than to the repository.
    currency: str = "EUR"
    # Which reader the document needs. "bacau" parses flattened text; "alba" reads real
    # tables, because that chamber's grids use merged cells and a merge is invisible once a
    # PDF has been flattened to lines.
    dialect: str = "bacau"
    # Where the document lives. Thirteen chambers publish through unnpr.ro and one — București
    # — publishes only on its own server, which is why this is a field rather than a constant.
    base: str = BASE


STUDIES: dict[str, Study] = {
    "mures": Study(
        key="unnpr-terenuri-mures-2026", chamber="CNP Târgu Mureș", counties=["MS"], year=2026,
        path=(
            "files/expertize2026/CNPTarguMures/"
            "28_03_2026_STUDIU_JUDETUL_MURES_PT_2026_republicare_compressed_(4)_16_03_2026.pdf"
        ),
        title="Studiu de piață — terenuri, județul Mureș, 2026",
        currency="RON", dialect="targumures",
    ),
    "harghita": Study(
        key="unnpr-terenuri-harghita-2026", chamber="CNP Târgu Mureș", counties=["HR"], year=2026,
        path=(
            "files/expertize2026/CNPTarguMures/"
            "28_03_2026_STUDIU_JUDETUL_HARGHITA_PT_2026_republicare_compressed_(1)_16_03_2026.pdf"
        ),
        title="Studiu de piață — terenuri, județul Harghita, 2026",
        currency="RON", dialect="targumures",
    ),
    "bistrita": Study(
        key="unnpr-terenuri-bistrita-2026", chamber="CNP Cluj", counties=["BN"], year=2026,
        path="files/expertize2026/CNPCluj/Studiu_Piata_Imobiliara_CNP_BN_2026.pdf",
        title="Studiu de piață — terenuri, județul Bistrița-Năsăud, 2026",
        currency="RON", dialect="cluj",
    ),
    "maramures": Study(
        key="unnpr-terenuri-maramures-2026", chamber="CNP Cluj", counties=["MM"], year=2026,
        path="files/expertize2026/CNPCluj/Studiu_Piata_Imobiliara_CNP_MM_2026.pdf",
        title="Studiu de piață — terenuri, județul Maramureș, 2026",
        currency="RON", dialect="cluj",
    ),
    "salaj": Study(
        key="unnpr-terenuri-salaj-2026", chamber="CNP Cluj", counties=["SJ"], year=2026,
        path="files/expertize2026/CNPCluj/Studiu_Piata_Imobiliara_CNP_SJ_2026.pdf",
        title="Studiu de piață — terenuri, județul Sălaj, 2026",
        currency="RON", dialect="cluj",
    ),
    "timis": Study(
        key="unnpr-terenuri-timis-2026", chamber="CNP Timișoara", counties=["TM"], year=2026,
        # Five annex files, one per court circumscription; the reader finds its own siblings.
        path="files/expertize2026/CNPTimisoara/Anexe_Timisoara_2026.pdf",
        title="Studiu de piață — terenuri, județul Timiș, 2026",
        currency="EUR", dialect="timisoara",
    ),
    "cluj": Study(
        key="unnpr-terenuri-cluj-2026", chamber="CNP Cluj", counties=["CJ"], year=2026,
        path="files/expertize2026/CNPCluj/Studiu_Piata_Imobiliara_CNP_CJ_2026.pdf",
        title="Studiu de piață — terenuri, județul Cluj, 2026",
        currency="RON", dialect="cluj",
    ),
    "bihor": Study(
        key="unnpr-terenuri-bihor-2026", chamber="CNP Oradea", counties=["BH"], year=2026,
        # The reader finds its own siblings: this county is five annexes, one per court
        # circumscription, and the revised edition of each supersedes the original.
        path=(
            "files/expertize2026/CNPOradea/"
            "STUDIUL_DE_PIATA_BIHOR_2026_Partea_scrisa_Revizuita_final.pdf"
        ),
        title="Studiu de piață — terenuri, județul Bihor, 2026",
        currency="RON", dialect="bihor",
    ),
    "satumare": Study(
        key="unnpr-terenuri-satu-mare-2026", chamber="CNP Oradea", counties=["SM"], year=2026,
        path="files/expertize2026/CNPOradea/Studiu_de_piata_Satu_Mare_2026.pdf",
        title="Studiu de piață — terenuri, județul Satu Mare, 2026",
        currency="RON", dialect="satumare",
    ),
    "hunedoara": Study(
        key="unnpr-terenuri-hunedoara-2026", chamber="CNP Alba Iulia", counties=["HD"], year=2026,
        path="files/expertize2026/CNPAlbaIulia/Hunedoara_2026.pdf",
        title="Studiu de piață — terenuri, județul Hunedoara, 2026",
        currency="RON", dialect="hunedoara",
    ),
    "dambovita": Study(
        key="unnpr-terenuri-dambovita-2025", chamber="CNP Ploiești", counties=["DB"], year=2025,
        path="files/expertize2025/CNPPloiesti/Matrice_Dambovita_2025.pdf",
        title="Studiu de piață — terenuri, județul Dâmbovița, 2025",
        currency="EUR", dialect="matrice",
    ),
    "buzau": Study(
        key="unnpr-terenuri-buzau-2025", chamber="CNP Ploiești", counties=["BZ"], year=2025,
        path="files/expertize2025/CNPPloiesti/Matrice_Buzau_2025.pdf",
        title="Studiu de piață — terenuri, județul Buzău, 2025",
        currency="EUR", dialect="matrice",
    ),
    "vrancea": Study(
        key="unnpr-terenuri-vrancea-2025", chamber="CNP Galați", counties=["VN"], year=2025,
        path="files/expertize2025/CNPGalati/EXPERTIZE_TERENURI_VRANCEA_2025.pdf",
        title="Studiu de piață — terenuri, județul Vrancea, 2025",
        currency="EUR", dialect="vrancea",
    ),
    "prahova": Study(
        key="unnpr-terenuri-prahova-2025", chamber="CNP Ploiești", counties=["PH"], year=2025,
        path="files/expertize2025/CNPPloiesti/Matrice_Prahova_2025.pdf",
        title="Studiu de piață — terenuri, județul Prahova, 2025",
        currency="EUR", dialect="ploiesti",
    ),
    "constanta": Study(
        key="unnpr-terenuri-constanta-2026", chamber="CNP Constanța", counties=["CT"], year=2026,
        path="files/expertize2026/CNPConstanta/studiu_de_piata_constanta_si_tulcea_2026.pdf",
        title="Studiu de piață — terenuri, județul Constanța, 2026",
        currency="EUR", dialect="constanta",
    ),
    "tulcea": Study(
        key="unnpr-terenuri-tulcea-2026", chamber="CNP Constanța", counties=["TL"], year=2026,
        path="files/expertize2026/CNPConstanta/studiu_de_piata_constanta_si_tulcea_2026.pdf",
        title="Studiu de piață — terenuri, județul Tulcea, 2026",
        currency="EUR", dialect="constanta",
    ),
    "sibiu": Study(
        key="unnpr-terenuri-sibiu-2026", chamber="CNP Alba Iulia", counties=["SB"], year=2026,
        path="files/expertize2026/CNPAlbaIulia/Sibiu_2026.pdf",
        title="Studiu de piață — terenuri, județul Sibiu, 2026",
        currency="RON", dialect="sibiu",
    ),
    "iasi": Study(
        key="unnpr-terenuri-iasi-2026",
        chamber="CNP Iași",
        counties=["IS"],
        year=2026,
        path="files/expertize2026/CNPIasi/studiu_de_piata_Iasi_2026.pdf",
        title="Studiu de piață — terenuri, județul Iași, 2026",
        currency="EUR",
        dialect="iasi",
    ),
    # Vaslui is Iași's chamber and — this is the whole reason it is cheap — Iași's layout.
    # The same reader, pointed at a different file.
    # The only chamber that does not publish through unnpr.ro. Its own server carries studies
    # for all six of its counties; this repository previously recorded that it published
    # nothing, which was a statement about the index rather than about the chamber.
    "bucuresti": Study(
        key="cnpb-terenuri-bucuresti-2026",
        chamber="CNP București",
        counties=["B"],
        year=2026,
        path="2026/2026_B_Teren.pdf",
        base="https://srv.cnpb.ro/",
        title="Studiu de piață — terenuri, Municipiul București, 2026",
        currency="EUR",
        dialect="bucuresti",
    ),
    "arad": Study(
        key="unnpr-terenuri-arad-2026", chamber="CNP Timișoara", counties=["AR"], year=2026,
        path="files/expertize2026/CNPTimisoara/Anexe_Arad_2026.pdf",
        title="Studiu de piață — terenuri, județul Arad, 2026",
        currency="EUR", dialect="arad",
    ),
    "valcea": Study(
        key="unnpr-terenuri-valcea-2024", chamber="CNP Pitești", counties=["VL"], year=2024,
        path="files/expertize2024/CNPPitesti/STUDIU_PIATA_2024_JUD_VALCEA.pdf",
        title="Studiu de piață — terenuri, județul Vâlcea, 2024",
        currency="RON", dialect="valcea",
    ),
    "arges": Study(
        key="unnpr-terenuri-arges-2026", chamber="CNP Pitești", counties=["AG"], year=2026,
        path="files/expertize2026/CNPPitesti/Studiu_de_Piata_CNP_Pitesti_2026.pdf",
        title="Studiu de piață — terenuri, județul Argeș, 2026",
        currency="RON", dialect="arges",
    ),
    "braila": Study(
        key="unnpr-terenuri-braila-2025", chamber="CNP Galați", counties=["BR"], year=2025,
        path="files/expertize2025/CNPGalati/braila_2025.pdf",
        title="Studiu de piață — terenuri, județul Brăila, 2025",
        currency="RON", dialect="braila",
    ),
    "dolj": Study(
        key="unnpr-terenuri-dolj-2026", chamber="CNP Craiova", counties=["DJ"],
        year=2026,
        path="files/expertize2026/CNPCraiova/studiu_de_piata_dolj_gorj_olt_mehedinti_2026.pdf",
        title="Studiu de piață — terenuri, județul Dolj, 2026",
        currency="RON", dialect="dolj",
    ),
    "gorj": Study(
        key="unnpr-terenuri-gorj-2026", chamber="CNP Craiova", counties=["GJ"],
        year=2026,
        path="files/expertize2026/CNPCraiova/studiu_de_piata_dolj_gorj_olt_mehedinti_2026.pdf",
        title="Studiu de piață — terenuri, județul Gorj, 2026",
        currency="RON", dialect="gorj",
    ),
    "mehedinti": Study(
        key="unnpr-terenuri-mehedinti-2026", chamber="CNP Craiova", counties=["MH"],
        year=2026,
        path="files/expertize2026/CNPCraiova/studiu_de_piata_dolj_gorj_olt_mehedinti_2026.pdf",
        title="Studiu de piață — terenuri, județul Mehedinți, 2026",
        currency="RON", dialect="mehedinti",
    ),
    "olt": Study(
        key="unnpr-terenuri-olt-2026", chamber="CNP Craiova", counties=["OT"],
        year=2026,
        path="files/expertize2026/CNPCraiova/studiu_de_piata_dolj_gorj_olt_mehedinti_2026.pdf",
        title="Studiu de piață — terenuri, județul Olt, 2026",
        currency="RON", dialect="olt",
    ),
    "galati": Study(
        key="unnpr-terenuri-galati-2026", chamber="CNP Galați", counties=["GL"], year=2026,
        path="files/expertize2026/CNPGalati/studiu_de_piata_CNP_Galati_2026.pdf",
        title="Studiu de piață — terenuri, județul Galați, 2026",
        currency="RON", dialect="galati",
    ),
    "carasseverin": Study(
        key="unnpr-terenuri-caras-severin-2026", chamber="CNP Timișoara", counties=["CS"],
        year=2026,
        path="files/expertize2026/CNPTimisoara/Anexe_Caras_Severin_2026.pdf",
        title="Studiu de piață — terenuri, județul Caraș-Severin, 2026",
        currency="EUR", dialect="carasseverin",
    ),
    "brasov": Study(
        key="unnpr-terenuri-brasov-2026", chamber="CNP Brașov", counties=["BV"], year=2026,
        path="files/expertize2026/CNPBrasov/STUDIU_JUD_BRASOV_COVASNA_PT_2026_final.pdf",
        title="Studiu de piață — terenuri, județul Brașov, 2026",
        currency="RON", dialect="brasov",
    ),
    "covasna": Study(
        key="unnpr-terenuri-covasna-2026", chamber="CNP Brașov", counties=["CV"], year=2026,
        path="files/expertize2026/CNPBrasov/STUDIU_JUD_BRASOV_COVASNA_PT_2026_final.pdf",
        title="Studiu de piață — terenuri, județul Covasna, 2026",
        currency="RON", dialect="covasna",
    ),
    "suceava": Study(
        key="unnpr-terenuri-suceava-2026",
        chamber="CNP Suceava",
        counties=["SV"],
        year=2026,
        path="files/expertize2026/CNPSuceava/Expertiza_SV_2026.pdf",
        title="Studiu de piață — terenuri, județul Suceava, 2026",
        currency="RON",
        dialect="suceava",
    ),
    "botosani": Study(
        key="unnpr-terenuri-botosani-2026",
        chamber="CNP Suceava",
        counties=["BT"],
        year=2026,
        path="files/expertize2026/CNPSuceava/Expertiza_BT_ 2026.pdf",
        title="Studiu de piață — terenuri, județul Botoșani, 2026",
        currency="RON",
        dialect="suceava",
    ),
    "teleorman": Study(
        key="cnpb-terenuri-teleorman-2026",
        chamber="CNP București",
        counties=["TR"],
        year=2026,
        path="2026/2026-CL-GR-IL-TR.pdf",
        base="https://srv.cnpb.ro/",
        title="Studiu de piață — terenuri, județul Teleorman, 2026",
        currency="EUR",
        dialect="teleorman",
    ),
    "ialomita": Study(
        key="cnpb-terenuri-ialomita-2026",
        chamber="CNP București",
        counties=["IL"],
        year=2026,
        path="2026/2026-CL-GR-IL-TR.pdf",
        base="https://srv.cnpb.ro/",
        title="Studiu de piață — terenuri, județul Ialomița, 2026",
        currency="EUR",
        dialect="ialomita",
    ),
    "giurgiu": Study(
        key="cnpb-terenuri-giurgiu-2026",
        chamber="CNP București",
        counties=["GR"],
        year=2026,
        path="2026/2026-CL-GR-IL-TR.pdf",
        base="https://srv.cnpb.ro/",
        title="Studiu de piață — terenuri, județul Giurgiu, 2026",
        currency="EUR",
        dialect="giurgiu",
    ),
    "calarasi": Study(
        key="cnpb-terenuri-calarasi-2026",
        chamber="CNP București",
        counties=["CL"],
        year=2026,
        path="2026/2026-CL-GR-IL-TR.pdf",
        base="https://srv.cnpb.ro/",
        title="Studiu de piață — terenuri, județul Călărași, 2026",
        currency="EUR",
        dialect="calarasi",
    ),
    "ilfov": Study(
        key="cnpb-terenuri-ilfov-2026",
        chamber="CNP București",
        counties=["IF"],
        year=2026,
        path="2026/2026_IF.pdf",
        base="https://srv.cnpb.ro/",
        title="Studiu de piață — terenuri, județul Ilfov, 2026",
        currency="EUR",
        dialect="ilfov",
    ),
    "vaslui": Study(
        key="unnpr-terenuri-vaslui-2026",
        chamber="CNP Iași",
        counties=["VS"],
        year=2026,
        path="files/expertize2026/CNPIasi/studiu_de_piata_Vaslui_2026 .pdf",
        title="Studiu de piață — terenuri, județul Vaslui, 2026",
        # Same chamber as Iași, entirely different document: Vaslui prices communes by class
        # and lists the classes in a sentence. Nothing of Iași's reader applies.
        currency="RON",
        dialect="vaslui",
    ),
    "alba": Study(
        key="unnpr-terenuri-alba-2026",
        chamber="CNP Alba Iulia",
        counties=["AB"],
        year=2026,
        path="files/expertize2026/CNPAlbaIulia/ALBA_2026.pdf",
        title="Studiu de piață — terenuri, județul Alba, 2026",
        currency="RON",
        dialect="alba",
    ),
    "bacau": Study(
        key="unnpr-terenuri-bacau-2026",
        chamber="CNP Bacău",
        counties=["BC"],
        year=2026,
        path="files/expertize2026/CNPBacau/Studiu_de_piata_Terenuri_Bacau_2026.pdf",
        title="Studiu de piață — terenuri, județul Bacău, 2026",
    ),
    "neamt": Study(
        key="unnpr-terenuri-neamt-2026",
        chamber="CNP Bacău",
        counties=["NT"],
        year=2026,
        path="files/expertize2026/CNPBacau/Studiu_de_piata_Terenuri_Neamt_2026.pdf",
        title="Studiu de piață — terenuri, județul Neamț, 2026",
    ),
}


def fold(text: str) -> str:
    """Compare Romanian place names without depending on how the PDF spells diacritics.

    The studies are internally inconsistent — the roster prints BUHOCI and the table prints
    Buhoci, Târgu Ocna appears as TARGU OCNA and Târgu-Ocna — so matching folds case,
    diacritics, hyphens and runs of spaces away and compares what is left.
    """
    lowered = str(text).lower()
    # The roster is spelled to the 1993 orthography and the tables are not: the roster prints
    # Gârleni, Pâncești, Pârjol, Târgu Ocna and the tables print GIRLENI, PINCESTI, PIRJOL,
    # TÎRGU OCNA. Both letters stand for the same sound and the same place, so â is folded
    # onto î before diacritics are stripped, which lands both spellings on i.
    lowered = lowered.replace("â", "î")
    stripped = unicodedata.normalize("NFD", lowered)
    stripped = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    # ș and ț sometimes arrive as the cedilla forms, which NFD does not decompose the same way.
    stripped = stripped.translate(str.maketrans({"ş": "s", "ţ": "t", "ș": "s", "ț": "t"}))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", stripped)).strip()


def download(study: Study) -> Path:
    """Keep the source once fetched, so a re-import does not need unnpr.ro to be up."""
    out = ROOT / "sources" / f"{study.key}.pdf"
    if out.exists() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = BASE + urllib.parse.quote(study.path)
    print(f"downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        out.write_bytes(response.read())
    return out


def fetch_study(name: str, path: str, base: str = BASE) -> Path:
    """One document into sources/studies/, under the name the extraction cache keys on."""
    import tls_chain  # noqa: PLC0415
    from extract_cache import STUDIES  # noqa: PLC0415

    out = STUDIES / name
    if out.exists() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = base + urllib.parse.quote(path)
    print(f"downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    # Verified, always. One chamber's server omits the intermediate that signs its own
    # certificate; `tls_chain` supplies it from the certificate's own AIA pointer rather than
    # turning verification off, because these documents become published numbers.
    with tls_chain.opener_for(url).open(request, timeout=300) as response:
        out.write_bytes(response.read())
    return out


def prime_cache(study: Study) -> None:
    """Make sure this study's extracted tables exist — and its dialect's siblings too.

    The dialects call `extract_cache.load` directly and it does not fetch: on a missing entry
    it exits and tells you to run the whole country-wide extraction. Locally that is right —
    the cache is built once for 115 documents and every run after that is instant. On a clean
    checkout it is not, because `sources/studies/` and `cache/` are both untracked, so a fresh
    CI run had the PDF (this file downloads it) and no tables (nothing built them).

    **Two readers need more than the document they are pointed at.** Timiș is five annexes,
    one per court circumscription, and Bihor is five more; both find their siblings by globbing
    the cache, which on a clean checkout contains exactly the one file that was primed. That
    does not error — it reads one annex of five and reports 36,4% coverage for a county that
    parses at 93,9%. So a dialect declares what it needs as `NEEDS`, a pattern matched against
    its own chamber's file list in the committed study index, and those are primed with it.

    Fetching all 115 studies to parse 22 of them would be 300 MB for the sake of uniformity.
    """
    from extract_cache import build, cache_path  # noqa: PLC0415

    wanted = [(Path(study.path).name, study.path)]

    # Missing is normal, not exceptional: `dialect="bacau"` is the sentinel for the built-in
    # reader and has no module of its own. Catching the import rather than repeating that
    # sentinel here means a future study without a dialect primes correctly instead of
    # crashing on a name that was only ever a flag.
    try:
        dialect = importlib.import_module(f"dialect_{study.dialect}")
    except ModuleNotFoundError:
        dialect = None
    needs = getattr(dialect, "NEEDS", None)
    if needs is not None:
        chamber = Path(study.path).parent.name
        index = ROOT / "sources" / f"studies-{study.year}.json"
        if index.exists():
            for entry in json.loads(index.read_text(encoding="utf-8"))["studies"]:
                same = Path(entry["path"]).parent.name == chamber
                if same and needs.search(entry["file"]):
                    wanted.append((entry["file"], entry["path"]))

    for name, path in dict(wanted).items():
        if cache_path(name).exists():
            continue
        _name, seconds, status = build(fetch_study(name, path, study.base))
        print(f"extracted {name} in {seconds:.0f}s ({status})")
        if status.startswith("failed"):
            raise SystemExit(f"could not extract {name}: {status}")


def pages_of(study: Study) -> list[str]:
    """The study's pages as flattened text, from the cache when it has been extracted.

    Falls back to reading the PDF so a single chamber can still be worked on without the
    country-wide cache, but the cache is the normal path: it turns an eleven-second read into
    a fiftieth of a second, and a parser is written by running it twenty times.
    """
    try:
        from extract_cache import load  # noqa: PLC0415

        return [page["text"] for page in load(Path(study.path).name)["pages"]]
    except SystemExit:
        reader = PdfReader(str(download(study)))
        return [(page.extract_text() or "") for page in reader.pages]


def numbers(text: str) -> list[float]:
    found = []
    for raw in re.findall(NUMBER, text):
        cleaned = raw.replace(" ", "").replace(" ", "")
        # Thousands separators only ever appear left of a decimal comma in these documents.
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        found.append(float(cleaned))
    return found


def trailing_row(text: str, width: int) -> list[float | None] | None:
    """The values at the end of a table line, or None if there are not exactly `width`.

    Read from the right rather than the left because every category label contains
    punctuation the value pattern would otherwise pick up — "CC - Curti constr." opens with a
    dash, and a dash is also how a missing zone is written. Walking back from the end stops at
    the first token that is neither a value nor a dash, which is the label.
    """
    tokens = text.split()
    row: list[float | None] = []
    for token in reversed(tokens):
        if not CELL.match(token):
            break
        row.append(None if token in DASH else float(token.replace(".", "").replace(",", ".")))
        if len(row) > width:
            break
    row.reverse()
    return row if len(row) == width else None


def category_at(line: str) -> tuple[str, str] | None:
    """Split a table line into its category code and the rest, or None if it is not one."""
    for code, _ in CATEGORIES:
        pattern = rf"^\s*{re.escape(code)}\b"
        if re.match(pattern, line, re.I):
            return code, line[re.match(pattern, line, re.I).end():]
    return None


# --- The roster, which is what the parse is checked against ----------------------------

ROSTER_SECTIONS = [("municipii", "municipii"), ("orase", "ora[sșş]e?"), ("comune", "comune")]

# Two places the study calls by different names in its own pages. Aliased rather than
# dropped: a document disagreeing with itself should not read as a commune that failed to
# parse. Both spellings are the study's own; neither is invented here.
#
# Ghimeș-Făget is the sharper of the two. The county roster on the organisation page calls
# it Ghimeș-Făget, while the annex roster and the value table both call it FAGET — and its
# villages, listed underneath, are Făget and Ghimeș. Same commune, named after one half of
# itself in two places out of three.
#
# **Scoped to the county that needs them.** They were county-blind at first, which held for
# as long as only Bacău and Neamț were imported and then quietly broke: Neamț calls
# Vânători-Neamț plain VANATORI, so `vanatori → vanatorineamt` was written for it, and when
# Mureș and Vrancea arrived — each with a commune genuinely named Vânători — the alias
# renamed those too and reported both as communes the study had failed to price. An alias is
# a statement about one document, not about the Romanian language.
ALIASES: dict[str, dict[str, str]] = {
    # The study writes the town with two i's and the land register with one.
    "TR": {"rosioriidevede": "rosioridevede"},
    # Brăila abbreviates one commune in its table and drops the article from another: the
    # register has Tudor Vladimirescu and Bărăganul, the study T.VLADIMIRESCU and BĂRĂGANU.
    "BR": {"tvladimirescu": "tudorvladimirescu", "baraganu": "baraganul"},
    # The Vâlcea study drops the `Băile` from both its spa towns' names.
    "VL": {"olanesti": "baileolanesti", "govora": "bailegovora"},
    # The Ilfov study writes the commune's short name and the register writes its full one;
    # "Dărăști" alone is what the annex heading and the extravilan table both use.
    "IF": {"darasti": "darastiilfov"},
    "BC": {
        "izvorulberheciului": "izvoruberheciului",
        "faget": "ghimesfaget",
    },
    # Neamț, where the tables spell three communes differently from the county roster on the
    # study's own organisation page: Bârgăuani as BARGAOANI, Gherăești as GHERAIESTI, and
    # Vânători-Neamț as plain VANATORI.
    "NT": {
        "bargaoani": "bargauani",
        "gheraiesti": "gheraesti",
        "vanatori": "vanatorineamt",
    },
    # Alba, where the register writes Almașu Mare and the study writes Almaşul Mare.
    "AB": {"almasulmare": "almasumare"},
    # Dâmbovița, where the rural annex's commune column is spelled by ear: Brezoaiele for
    # Brezoaele, Moroieni for Moroeni, Piersinari for Perșinari, Răscăieți for Răscăeți and
    # Râul Alb for Râu Alb. The village list beside each of them spells the villages right.
    # Hunedoara, whose tables abbreviate: Baru is printed after its seat village Baru Mare,
    # General Berthelot as "G-ral Berthelot", and Geoagiu carries its rank into its name to
    # tell the town apart from the Geoagiu-Băi resort priced beside it.
    "HD": {
        "barumare": "baru",
        "gralberthelot": "generalberthelot",
        "geoagiuoras": "geoagiu",
    },
    # Buzău, where the rural annex drops a letter from Glodeanu-Siliștea.
    "BZ": {"glodeanusilstea": "glodeanusilistea"},
    "DB": {
        "brezoaiele": "brezoaele",
        "moroieni": "moroeni",
        "piersinari": "persinari",
        "rascaieti": "rascaeti",
        "raulalb": "raualb",
    },
    # Vrancea, whose annexes abbreviate to fit the column: Slobozia is "Sl", Andreiașu de Jos
    # loses its half, and Cârligele loses its ending.
    "VN": {
        "andreiasu": "andreiasudejos",
        "cirlige": "carligele",
        "slbradului": "sloboziabradului",
        "slciorasti": "sloboziaciorasti",
        "sl.bradului": "sloboziabradului",
        "sl.ciorasti": "sloboziaciorasti",
    },
}

# The county whose names are being folded. Set by register_roster, which is the one place
# that knows it and always runs before any name is compared — the importer builds the roster
# before it opens the study, and so does every probe.
ACTIVE_COUNTY: str | None = None


def key_of(name: str) -> str:
    """A place's identity, indifferent to how the PDF broke it across lines.

    Commune names wrap mid-word — the table prints CLEJ / A and ONCEST / I — so the pieces
    are rejoined without knowing whether a space belonged at the break. Comparing with all
    spaces removed makes the join decision irrelevant: DEALU + MORII and DEALUMORII are the
    same key, and so are CLEJ + A and CLEJA.
    """
    stripped = fold(name).replace(" ", "")
    return ALIASES.get(ACTIVE_COUNTY or "", {}).get(stripped, stripped)


def ai_equal(left: str, right: str) -> bool:
    """Whether two folded names differ only where â and î were flattened differently.

    Both the notaries' studies and the INS register write Romanian without settling the
    1993 orthography, and neither is consistent with itself: the register spells Bâra BIRA
    and Cândești CANDESTI, while Neamț's grid prints BARA for the first and CINDESTI for the
    second. Once diacritics are stripped, the difference is a single letter — an `a` against
    an `i` — and nothing else about the name changes.

    So this compares position by position and forgives exactly that substitution. It is a
    narrow licence on purpose: two Romanian localities in one county differing only in an a
    against an i are not a thing, whereas a commune lost to a spelling disagreement is.
    """
    if len(left) != len(right):
        return False
    return all(x == y or {x, y} == {"a", "i"} for x, y in zip(left, right, strict=True))


def resolve(key: str, table: Mapping[str, object]) -> str | None:
    """The key as the table spells it: exact if possible, else the a/i-tolerant match."""
    if key in table:
        return key
    matches = [candidate for candidate in table if ai_equal(key, candidate)]
    # Only when it is unambiguous. Two candidates means the licence above was too wide for
    # this county, and guessing between them would be worse than reporting the name missing.
    return matches[0] if len(matches) == 1 else None


def keys_of(name: str) -> set[str]:
    """Every spelling of a roster name the tables might use.

    `fold` lands â on i, which matches the tables that print GIRLENI and PIRJOL. But the same
    study also prints BARSANESTI for Bârsănești, spelling the same letter a. Neither variant
    can be the single canonical one, so a roster name is registered under both and whichever
    the table used will find it.

    The unaliased spelling is registered as well, because ALIASES has no county in it. It was
    written to reconcile one study with itself — Neamț calls Vânători-Neamț plain VANATORI —
    and when Mureș and Vrancea arrived, each with a commune of its own actually called
    Vânători, the alias renamed all three to the Neamț one and lost the other two. A roster
    name answering to what it is actually called costs nothing and is not a county's problem
    to have solved elsewhere.
    """
    plain = name.replace("â", "a").replace("Â", "A")
    return {
        key_of(name),
        key_of(plain),
        fold(name).replace(" ", ""),
        fold(plain).replace(" ", ""),
    }


# The register writes a locality's rank into its name; the grids do not.
REGISTER_RANKS = (("MUNICIPIUL ", "municipii"), ("ORASUL ", "orase"), ("ORAS ", "orase"))
AREA_YEAR = 2014


def register_roster(county: str) -> dict[str, list[str]]:
    """The county's localities, from the INS land register rather than from the study.

    The first version of this read the roster off the study's own organisation page, which
    works for the two documents from CNP Bacău and for no others: fifteen studies from four
    other chambers were tried and not one had that page. They are written by different firms —
    Cluj's by a valuation company in Cluj, Timiș's by another in Timișoara — and share no
    layout at all.

    The register does not care. It lists every locality of every county with its SIRUTA and
    its rank spelled into its name, so it can check any chamber's grid, and checking a parse
    against an outside source is better than checking it against another page of the same
    document. It also means a county's areas must be imported before its grid, which is
    stated rather than discovered: the two are joined later anyway.
    """
    global ACTIVE_COUNTY  # noqa: PLW0603 — see the note above ALIASES
    ACTIVE_COUNTY = county.upper()
    path = ROOT / "data" / f"fond-funciar-{county.lower()}-{AREA_YEAR}.json"
    if not path.exists():
        raise SystemExit(
            f"missing {path}\n"
            f"Run: uv run python simulators/impozit-teren/scripts/import_fond_funciar.py "
            f"--county {county}"
        )
    document = json.loads(path.read_text(encoding="utf-8"))
    roster: dict[str, list[str]] = {"municipii": [], "orase": [], "comune": []}
    for record in document["localities"]:
        name = record["name"]
        rank = "comune"
        for prefix, kind in REGISTER_RANKS:
            if name.upper().startswith(prefix):
                rank, name = kind, name[len(prefix):]
                break
        roster[rank].append(name.strip())
    return roster


def county_roster(pages: list[str]) -> dict[str, list[str]]:
    """The county's own list of its municipii, orașe and comune.

    The study prints this once, under "Organizarea administrativ teritorială", with the
    canonical spelling and the diacritics the tables drop. It is the authority the parse is
    measured against — better than the per-annex rosters, which are upper-cased, wrap across
    lines, and are split over five pages.
    """
    for page in pages:
        lines = [line.strip() for line in page.splitlines()]
        # Found by shape rather than by title. Bacău's study heads this page "Organizarea
        # administrativ teritorială"; Neamț's, from the same chamber and the same year, gives
        # it no heading at all. What both have is the three rank headings standing alone on
        # their own lines above bulleted names — which the per-annex rosters do not, because
        # there the first name shares the heading's line ("Orase BICAZ") and nothing is
        # bulleted. That distinction is what keeps this from matching the wrong page.
        headings = {
            name
            for name, pattern in ROSTER_SECTIONS
            if any(re.fullmatch(pattern, line, re.I) for line in lines)
        }
        if len(headings) < len(ROSTER_SECTIONS) or sum(1 for x in lines if x.startswith("•")) < 10:
            continue
        roster: dict[str, list[str]] = {name: [] for name, _ in ROSTER_SECTIONS}
        section: str | None = None
        for line in page.splitlines():
            line = line.strip()
            if not line or "֍" in line:
                continue
            matched = next(
                (name for name, pattern in ROSTER_SECTIONS if re.fullmatch(pattern, line, re.I)),
                None,
            )
            if matched:
                section = matched
                continue
            if section and line.startswith("•"):
                # "Bacău (resedinta judetului)" — the parenthetical is commentary, not name.
                name = re.sub(r"\(.*?\)", "", line.lstrip("• ")).strip()
                if name:
                    roster[section].append(name)
        if any(roster.values()):
            return roster
    return {name: [] for name, _ in ROSTER_SECTIONS}


# --- Zoned localities: a matrix of category against zone --------------------------------

ZONE_HEAD = re.compile(r"Zone\s*/\s*ctg\.?\s*fol\.?\s*(.+)")
# The four ways this study introduces a zoned locality, all in the same document.
ZONED_NAME = re.compile(
    # Internal spaces are literal rather than \s: with \s the name ran past the line break
    # and swallowed the "INTRAVILAN" heading that follows it on the next line.
    r"(?:MUNICIPIUL|ORA[ȘŞS]UL)[ \t]+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.]*)"
    # "1. Oras" and "1. Oras." both occur, sometimes in the same document on facing pages.
    r"|\d+\.[ \t]*Ora[șşs]\.?[ \t]*\n[ \t]*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.]*)"
    r"|Zonarea\s+(?:municipiului|ora[șşs]ului|comunei)\s+([A-ZĂÂÎȘŞȚŢ][\w \-\.]*?)\s+conform"
    # Neamț names the locality inside the table's own heading instead of above it, and writes
    # "Orasul Roznov" where Bacău writes "ORAŞUL BUHUŞI". Same chamber, same year, same table.
    r"|INTRAVILAN\s*\(EURO/m\.?p\.?\)\s*/?\s*ZONE\s*[-–]\s*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.]*)"
    r"|Ora[șşs]ul[ \t]+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.]*)"
)


def complete_name(name: str, before: str, known: Mapping[str, object]) -> str:
    """Finish a locality name that wrapped, using the roster to decide where it ends.

    Town names break across lines like commune names do — SLĂNIC / MOLDOVA — but unlike
    commune names they are followed by upper-case headings, so "keep reading capitals" would
    swallow INTRAVILAN. The rule instead is that a fragment is only absorbed if absorbing it
    turns an unrecognised name into a recognised one, and blank lines and the heading in
    between are stepped over rather than treated as the end of the name.
    """
    if resolve(key_of(name), known):
        return name
    candidates = [line.strip() for line in before.splitlines() if line.strip()]
    for extra in reversed(candidates[-6:]):
        if is_name_line(extra) and resolve(key_of(f"{name} {extra}"), known):
            return f"{name} {extra}"
    return name


def parse_zoned(pages: list[str], known: dict[str, str]) -> list[dict]:
    """Every locality priced by zone letter rather than as a flat per-village value.

    Not the same thing as "every town". Bacău's study zones the three municipii and five
    orașe, and also the commune of Podu Turcului, which passed its own zoning decision. So
    the parse follows the zone tables wherever they are and asks the roster afterwards what
    rank each locality holds, rather than assuming a matrix implies a town.
    """
    zoned = []
    for index, page in enumerate(pages):
        for zone_match in ZONE_HEAD.finditer(page):
            zones = re.findall(r"\b([A-F])\b", zone_match.group(1))
            if not zones:
                continue
            # The name is the last one introduced before this matrix — on this page if the
            # page carries several, otherwise on the page that opened the section.
            name = ""
            for candidate in ZONED_NAME.finditer(page[: zone_match.start()]):
                name = next(g for g in candidate.groups() if g)
            if not name:
                for back in range(index - 1, max(index - 3, -1), -1):
                    for candidate in ZONED_NAME.finditer(pages[back]):
                        name = next(g for g in candidate.groups() if g)
            if not name:
                continue
            name = complete_name(
                re.sub(r"\s+", " ", name).strip(" .-"), page[: zone_match.start()], known
            )

            body = page[zone_match.end():]
            values: dict[str, dict[str, float]] = {}
            current: str | None = None
            for line in body.splitlines():
                if ZONE_HEAD.search(line):
                    break
                split = category_at(line)
                if split:
                    current, rest = split
                else:
                    rest = line
                if current is None:
                    continue
                # A label wraps over up to three lines, so the values are taken from the
                # first line under the label that ends in exactly one cell per zone.
                row = trailing_row(rest, len(zones))
                if row is not None and current not in values:
                    values[current] = dict(zip(zones, row, strict=True))
                    current = None
            if values:
                zoned.append(
                    {
                        "name": known.get(resolve(key_of(name), known) or "", name),
                        "rank": None,
                        "zones": zones,
                        "intravilan": values,
                        "extravilan": {},
                        "page": index + 1,
                    }
                )

    # Towns carry an extravilan row as well, on a later page and in a different shape: one
    # value per category, no zones, under a bare header of the category codes. It is the same
    # information the rural tables print per commune, so it is attached to the same record
    # rather than published as a second kind of thing.
    by_key = {key_of(entry["name"]): entry for entry in zoned}
    for index, page in enumerate(pages):
        for block in re.finditer(r"EXTRAVILAN\s*\(EURO/m\.?p\.?\)", page):
            name = ""
            for candidate in ZONED_NAME.finditer(page[: block.start()]):
                name = next(g for g in candidate.groups() if g)
            if not name:
                continue
            name = complete_name(
                re.sub(r"\s+", " ", name).strip(" .-"), page[: block.start()], by_key
            )
            entry = by_key.get(resolve(key_of(name), by_key) or "")
            if entry is None or entry["extravilan"]:
                continue
            after = page[block.end():]
            header = re.search(r"A\s+V\+L\s+P\+F\s+CC\s+AP\s+DR\s+NP", after)
            if not header:
                continue
            row = numbers(after[header.end():].split("\n\n")[0])[: len(EXTRAVILAN_CODES)]
            if len(row) == len(EXTRAVILAN_CODES):
                entry["extravilan"] = dict(zip(EXTRAVILAN_CODES, row, strict=True))
                entry["extravilanPage"] = index + 1
    return zoned


# --- Villages: intravilan per village, extravilan per commune ---------------------------

COMMUNE_HEAD = re.compile(r"^\s*(\d{1,3})\s*$")
NOISE = re.compile(
        # "TI" is deliberately absent. It looked like header noise — the column head
    # "LOCALITATI RURALE" breaks as LOCALITA / TI — but it is also how BORLES / TI and
    # Z A N E S / TI finish their commune names, and filtering it truncated them. The
    # stray header fragment is harmless instead: a village with no values is dropped.
    r"^\s*(\d+\s*֍|A-\s*arabil|de exploatare|ape;|Nr\.|Crt\.|LOCALITA|RURALE|SATUL|"
    r"INTRAVILAN|EXTRAVILAN|\(EURO|A V\+L P\+F CC AP DR NP)",
    re.I,
)


ANNEX = re.compile(r"ANEXA\s+NR", re.I)
_UPPER_WORD = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ\-\.]*$")
# Romanian place names keep their connectives in lower case even when the rest is shouted:
# Neamț's table prints ALEXANDRU cel BUN. Without these the name reads as a village.
CONNECTIVES = {"cel", "cea", "de", "din", "la", "lui", "si", "și", "sub", "pe"}


def is_name_line(line: str) -> bool:
    """A locality name in a table: upper case throughout, bar the connectives."""
    words = line.split()
    if not words or not _UPPER_WORD.match(words[0]):
        return False
    # A hyphen can stand as its own word — the tables print BERESTI - BISTRITA and BICAZ -
    # CHEI with spaces either side, and rejecting those lines lost the communes entirely.
    return all(
        _UPPER_WORD.match(w) or w.lower() in CONNECTIVES or set(w) <= set(DASH) for w in words
    )
INLINE_VILLAGE = re.compile(
    r"^(?P<name>(?!CC\b|TS\b|TAPA\b)[^\d]*?[a-zăâîșşțţ][^\d]*?)\s+"
    r"(?:CC|V\+L|P\+F|TAPA SI NP|TS|A)\s+\d"
)


def parse_villages(
    pages: list[str], known: dict[str, str], rank_of: dict[str, str]
) -> tuple[list[dict], list[str]]:
    """Walk the rural tables, keeping commune numbering so gaps are visible."""
    communes: list[dict] = []
    problems: list[str] = []
    current: dict | None = None
    village: dict | None = None
    pending_number: str | None = None
    pending_name: list[str] = []

    def close_village() -> None:
        nonlocal village
        if current is not None and village is not None and village["intravilan"]:
            current["villages"].append(village)
        village = None

    def flush_commune(page_number: int, line: str = "") -> str:  # noqa: C901
        """Commit the commune whose name has finished arriving, one fragment at a time.

        A name does not always end at a line break. Valea Seacă is printed as VAL / EA /
        SEAC / "A  Valea", so its last letter shares a line with the first village. Rather
        than guess where the name stops, the roster is asked: if the fragments so far do not
        name a commune but the fragments plus the line's leading capitals do, that prefix
        belonged to the name and the rest of the line is returned to be read as a village.
        """
        nonlocal current, pending_number, pending_name
        if not pending_number or not pending_name:
            pending_number, pending_name = None, []
            return line
        close_village()
        joined = "".join(pending_name)
        match = resolve(key_of(joined), known)
        canonical = known.get(match) if match else None
        if canonical is None:
            prefix = re.match(r"[A-ZĂÂÎȘŞȚŢ]+", line)
            extended = resolve(key_of(joined + prefix.group()), known) if prefix else None
            if prefix and extended:
                joined += prefix.group()
                canonical = known[extended]
                line = line[prefix.end():].strip()
        current = {
            "index": int(pending_number),
            "name": canonical or re.sub(r"\s+", " ", " ".join(pending_name)).strip(" .-"),
            "matchedRoster": canonical is not None,
            # Not always a commune. A Romanian town keeps villages of its own, and the study
            # prices those in the rural table while pricing the town itself by zone — Bicaz
            # and Roznov each appear in both. Recording the rank the roster gives the name
            # keeps that visible instead of it reading as two communes the roster forgot.
            "rank": rank_of.get(resolve(key_of(canonical or joined), rank_of) or ""),
            "villages": [],
            "extravilan": {},
            "page": page_number,
        }
        communes.append(current)
        pending_number, pending_name = None, []
        return line

    annex_starts: list[int] = []
    for index, page in enumerate(pages):
        if ANNEX.search(page):
            annex_starts.append(index)
        lines = page.splitlines()
        # "TAPA" and "SI NP <value>" arrive as two lines; rejoin before anything else looks.
        joined_lines: list[str] = []
        for line in lines:
            if (
                joined_lines
                and re.fullmatch(r"\s*TAPA\s*", joined_lines[-1])
                and re.match(r"\s*SI\s+NP", line)
            ):
                joined_lines[-1] = "TAPA SI NP" + line.split("NP", 1)[1]
            else:
                joined_lines.append(line)

        for line in joined_lines:
            stripped = line.strip()
            if not stripped or NOISE.match(stripped):
                continue

            number_only = COMMUNE_HEAD.match(stripped)
            if number_only:
                flush_commune(index + 1)
                pending_number = number_only.group(1)
                continue

            # A commune name is upper case and carries no digits, and it wraps: the table
            # prints CLEJ / A, ONCEST / I, DEALU / MORII. Fragments are collected until a
            # line arrives that is not upper case, then rejoined and matched to the roster.
            if pending_number and is_name_line(stripped):
                pending_name.append(stripped)
                continue
            if pending_number:
                stripped = flush_commune(index + 1, stripped)
                if not stripped:
                    continue

            # A village name and its first value sometimes share a line — "Cleja CC 7,98" —
            # and sometimes do not. Split the name off before the line is read as a row.
            inline = INLINE_VILLAGE.match(stripped)
            if inline and current is not None:
                close_village()
                village = {"name": re.sub(r"\s+", " ", inline.group("name")), "intravilan": {}}
                stripped = stripped[inline.end("name"):].strip()

            split = category_at(stripped)
            if split is None:
                # Anything else inside a commune block is a village name. Names wrap, so a
                # trailing fragment is stitched onto the previous one rather than dropped.
                if current is None:
                    continue
                if re.fullmatch(r"[a-zțșăâî]{1,3}", stripped) and village is not None:
                    village["name"] += stripped
                    continue
                close_village()
                village = {"name": re.sub(r"\s+", " ", stripped), "intravilan": {}}
                continue

            code, rest = split
            row = numbers(rest)
            if not row:
                continue
            if current is None:
                continue
            if village is None:
                # A category row before any village name: the commune's seat shares its name.
                village = {"name": current["name"].title(), "intravilan": {}}
            village["intravilan"].setdefault(code, row[0])
            # The extravilan block is printed once per commune, tacked onto whichever
            # category row it lands beside. Seven values, in the header's order.
            if len(row) == 1 + len(EXTRAVILAN_CODES) and not current["extravilan"]:
                current["extravilan"] = dict(zip(EXTRAVILAN_CODES, row[1:], strict=True))

        # Deliberately not closing the village here. A village's six rows straddle the page
        # break often enough that closing at the page boundary invented a village named
        # after the commune to hold the rows that continued overleaf.

    flush_commune(len(pages), "")
    close_village()

    # Numbering restarts at 1 in each annex, so a decrease is a new annex rather than a
    # fault. Within an annex it must step by one; anything else means a commune was lost.
    previous = 0
    for commune in communes:
        index = commune["index"]
        if index != previous + 1 and not (index == 1 or index < previous):
            problems.append(
                f"commune numbering jumps from {previous} to {index} "
                f"({commune['name']}, page {commune['page']})"
            )
        previous = index
    return communes, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chamber", default="bacau", choices=sorted(STUDIES))
    parser.add_argument(
        "--from-study-roster",
        action="store_true",
        help="check against the study's own organisation page instead of the land register",
    )
    args = parser.parse_args()
    study = STUDIES[args.chamber]
    from_register = not args.from_study_roster

    # Before any reading: the dialects go straight to the extraction cache and cannot fetch.
    prime_cache(study)
    pages = pages_of(study)
    print(f"{study.title}: {len(pages)} pages")

    # The register first, the study's own page only if the register is not imported. The
    # study's page exists in two documents out of seventeen tried.
    roster = register_roster(study.counties[0]) if from_register else county_roster(pages)
    known = {key: name for names in roster.values() for name in names for key in keys_of(name)}
    rank_of = {
        key: rank for rank, names in roster.items() for name in names for key in keys_of(name)
    }
    print(
        f"roster: {len(roster['municipii'])} municipii, {len(roster['orase'])} orașe, "
        f"{len(roster['comune'])} comune"
    )
    if not known:
        print("FATAL: the study's own administrative roster did not parse", file=sys.stderr)
        return 1

    if study.dialect != "bacau":
        import importlib  # noqa: PLC0415

        parse_alba = importlib.import_module(f"dialect_{study.dialect}").parse

        # The register decides which recovered labels are real place names, which is what
        # keeps a wrapped name from being read as two communes. Towns count too: a town keeps
        # villages of its own and the rural table prices them, which is how Abrud is priced
        # in Alba and Bicaz and Roznov in Neamț.
        local_keys = {key for name in known.values() for key in keys_of(name)}

        def is_commune(text: str) -> bool:
            return resolve(key_of(text), {k: None for k in local_keys}) is not None

        zoned, communes, problems = parse_alba(Path(study.path).name, is_commune)
        for record in communes:
            record.setdefault("index", 1)
        # Canonicalise first, then merge: a commune's rows can be split across two tables and
        # spelled differently in each, so the same place arrives twice and only looks like one
        # place after the register has named it.
        merged: dict[str, dict] = {}
        for record in communes:
            match = resolve(key_of(record["name"]), known)
            record["name"] = known.get(match, record["name"]) if match else record["name"]
            record["matchedRoster"] = match is not None
            record["rank"] = rank_of.get(match or "")
            key = match or key_of(record["name"])
            first = merged.get(key)
            if first is None:
                merged[key] = record
                continue
            seen = {v["name"] for v in first["villages"]}
            first["villages"].extend(v for v in record["villages"] if v["name"] not in seen)
            if not first["extravilan"]:
                first["extravilan"] = record["extravilan"]
        communes = list(merged.values())
        for position, record in enumerate(communes, start=1):
            record["index"] = position
        for entry in zoned:
            match = resolve(key_of(entry["name"]), known)
            entry["name"] = known.get(match, entry["name"]) if match else entry["name"]
    else:
        zoned = parse_zoned(pages, known)
        communes, problems = parse_villages(pages, known, rank_of)

    # The register checks; it does not name. It shouts and drops diacritics — MUNICIPIUL
    # BACAU — while a study that carries its county's organisation page prints Bacău. So the
    # completeness check keeps the register and the published name prefers the document,
    # falling back to the register for the chambers that print no such page.
    display = {
        key: name
        for names in county_roster(pages).values()
        for name in names
        for key in keys_of(name)
    }
    for record in [*zoned, *communes]:
        better = resolve(key_of(record["name"]), display)
        if better:
            record["name"] = display[better]
    for entry in zoned:
        entry["rank"] = rank_of.get(resolve(key_of(entry["name"]), rank_of) or "")

    # A zoned entry the register ranks as rural is a commune that happens to be priced by
    # zone, and it is demoted here rather than in the reader that produced it. A dialect sees
    # a table, not a roster: Hunedoara zones twenty-seven localities and only fourteen of them
    # are towns, so the reader cannot tell which is which and guessing from the shape of the
    # grid would be guessing. Demoting late costs nothing — the zone prices become the
    # commune's readings instead of being dropped, which is what they are.
    demoted = [entry for entry in zoned if entry["rank"] not in ("municipii", "orase")]
    zoned = [entry for entry in zoned if entry["rank"] in ("municipii", "orase")]
    existing = {key_of(c["name"]): c for c in communes}
    for entry in demoted:
        prices = sorted({v for v in entry["intravilan"]["CC"].values() if v}, reverse=True)
        match = resolve(key_of(entry["name"]), known)
        # A locality can be priced twice by the same study — Bacău zones Podu Turcului as
        # though it were a town and also lists it in the rural table. Demoting it into a
        # second commune of the same name made the duplicate gate fire, which is exactly what
        # that gate is for: the readings belong to one place, so they are merged into it.
        already = existing.get(key_of(entry["name"]))
        if already is not None:
            seen = {v["name"] for v in already["villages"]}
            already["villages"].extend(
                {"name": f"{entry['name']} (zona {zone})", "intravilan": {"CC": price}}
                for zone, price in sorted(entry["intravilan"]["CC"].items())
                if price and f"{entry['name']} (zona {zone})" not in seen
            )
            if not already["extravilan"]:
                already["extravilan"] = entry.get("extravilan", {})
            continue
        communes.append(
            {
                "name": entry["name"],
                "villages": [
                    {"name": f"{entry['name']} ({position})", "intravilan": {"CC": price}}
                    for position, price in enumerate(prices, start=1)
                ],
                "extravilan": entry.get("extravilan", {}),
                "page": entry.get("page", 1),
                "matchedRoster": match is not None,
                "rank": entry["rank"],
                "index": 0,
            }
        )
    if demoted:
        for position, record in enumerate(communes, start=1):
            record["index"] = position
        print(f"zonate dar rurale, tratate ca sate: {len(demoted)}")

    # Forest, where the study gives one figure for the county instead of one per commune.
    # Filled in only if the reader found none: a per-locality price is always better, and
    # this must not overwrite one. Recorded as county-wide in the output so nobody reads it
    # as local detail it does not have.
    forest_scope: str | None = None
    if not any("PADURE" in c["extravilan"] for c in communes):
        price, where = county_price(Path(study.path).name)
        # The helper reads tables captioned EURO/Ha, so what it returns is euro. Every study
        # that has one of those tables prices in euro anyway; a lei-priced study with a euro
        # forest table would need a conversion that does not exist yet, so it is refused
        # rather than silently mixed.
        if price is not None and study.currency != "EUR":
            print(f"pădure: preț în euro într-un studiu în {study.currency}, ignorat")
            price = None
        if price is not None:
            for record in [*communes, *zoned]:
                record["extravilan"]["PADURE"] = price
            forest_scope = where
            print(f"pădure, preț pe județ: {price:.4f} {study.currency}/m² — {where}")

    villages = sum(len(c["villages"]) for c in communes)
    with_extravilan = sum(1 for c in communes if c["extravilan"])
    print(f"localități zonate: {len(zoned)}")
    print(f"comune: {len(communes)}   sate: {villages}   comune cu extravilan: {with_extravilan}")

    # The check. Every commune the county's own roster names must have come out of the
    # tables, and every commune the tables yield must be one the roster names.
    parsed = {key_of(c["name"]) for c in communes}
    listed = {key_of(name) for name in roster["comune"]}
    missing = sorted(
        known.get(k, k) for k in listed if resolve(k, {p: None for p in parsed}) is None
    )
    unlisted = sorted(c["name"] for c in communes if not c["matchedRoster"])
    # A town has to be priced somewhere, not necessarily by a zone grid. Most are zoned, but
    # a small one can be priced village by village in the rural table like a commune — Abrud
    # is — and that is the document choosing, not the parse losing it.
    towns_priced = {key_of(z["name"]) for z in zoned if z["rank"] in ("municipii", "orase")}
    towns_priced |= {key_of(c["name"]) for c in communes if c["rank"] in ("municipii", "orase")}
    towns_listed = {key_of(n) for n in roster["municipii"] + roster["orase"]}
    towns_missing = sorted(
        known.get(k, k) for k in towns_listed if resolve(k, {t: None for t in towns_priced}) is None
    )

    seen: dict[str, int] = {}
    for commune in communes:
        key = resolve(key_of(commune["name"]), seen) or key_of(commune["name"])
        seen[key] = seen.get(key, 0) + 1
    duplicates = sorted(known.get(k, k) for k, n in seen.items() if n > 1)

    expected = len(roster["comune"]) + len(roster["municipii"]) + len(roster["orase"])

    if duplicates:
        print(f"\nlocalități apărute de două ori ({len(duplicates)}): {duplicates}")
    if missing:
        print(f"\nîn roster dar nu în tabele ({len(missing)}): {missing}")
    if unlisted:
        print(f"în tabele dar nu în roster ({len(unlisted)}): {unlisted}")
    if towns_missing:
        print(f"orașe fără grilă pe zone ({len(towns_missing)}): {towns_missing}")
    for problem in problems:
        print(f"  {problem}")

    document = {
        "$schema": "../schema/ghid-teren.schema.json",
        "id": study.key,
        "title": study.title,
        "publisher": f"Uniunea Națională a Notarilor Publici din România — {study.chamber}",
        "counties": study.counties,
        "period": str(study.year),
        "currency": study.currency,
        "unit": f"{study.currency}/m²",
        "provenance": {
            "source": study.key,
            "locator": f"{BASE}{study.path}, anexele cu valorile orientative minime",
            "confidence": "verbatim",
            "note": (
                "Valorile sunt copiate din tabelele studiului, nu recalculate. Intravilanul "
                "este publicat pe sat, extravilanul pe comună; separarea este păstrată."
            ),
        },
        "summary": {
            "pages": len(pages),
            "zonedLocalities": len(zoned),
            "communes": len(communes),
            "villages": villages,
            "communesWithExtravilan": with_extravilan,
            "rosterMunicipii": len(roster["municipii"]),
            "rosterOrase": len(roster["orase"]),
            "rosterComune": len(roster["comune"]),
            # Named, not gated. A locality the study does not price is a gap in the source,
            # and refusing the whole county for it publishes nothing about the other 99%.
            # What stays gated is the opposite failure — a place the parse invented, or
            # counted twice — because that is the parse being wrong rather than the document
            # being short. The coverage figure below is what a reader should judge this on.
            "rosterMissingFromTable": missing,
            "tableMissingFromRoster": unlisted,
            "townsWithoutZoneGrid": towns_missing,
            "duplicateLocalities": duplicates,
            # Where the forest price came from when it is one figure for the whole county
            # rather than one per commune; null when the grid prices forest per locality.
            "forestPriceScope": forest_scope,
            "numberingProblems": problems,
            "coverage": {
                "localitiesExpected": expected,
                "localitiesPriced": expected - len(missing) - len(towns_missing),
                "share": round((expected - len(missing) - len(towns_missing)) / expected, 4)
                if expected
                else 0.0,
            },
        },
        "categories": [{"code": code, "label": label} for code, label in CATEGORIES],
        "extravilanCategories": EXTRAVILAN_CODES,
        "roster": roster,
        "zoned": zoned,
        "communes": communes,
        "limitations": [
            {
                "id": "grila-e-un-prag-nu-o-piata",
                "text": (
                    "Valorile sunt „minime orientative”: pragul sub care o vânzare nu poate fi "
                    "declarată, folosit pentru onorarii și pentru impozitul pe transfer. Stau "
                    "sub prețul de tranzacție cu o marjă care nu este publicată și nu este "
                    "constantă între județe. Cifrele compară locurile între ele mult mai bine "
                    "decât măsoară vreunul dintre ele."
                ),
                "severity": "blocking",
                "affects": ["valoare-teren", "impozit", "randament"],
            },
            {
                "id": "extravilanul-e-pe-comuna",
                "text": (
                    "Intravilanul este publicat pe sat, extravilanul o singură dată pe comună. "
                    "Satele unei comune primesc deci aceeași valoare extravilană; precizia pe "
                    "sat nu există în document și nu este inventată aici."
                ),
                "severity": "material",
                "affects": ["valoare-teren"],
            },
            {
                "id": "zonele-din-orase-sunt-adrese-nu-poligoane",
                "text": (
                    "În orașe valoarea depinde de zona A–D, iar zonele sunt definite prin liste "
                    "de străzi și intervale de numere, nu prin poligoane. Nu există o "
                    "geometrie publicată a lor, așa că valorile urbane pot fi raportate pe "
                    "oraș și pe zonă, dar nu așezate pe hartă sub nivelul orașului."
                ),
                "severity": "material",
                "affects": ["harta", "valoare-teren"],
            },
            {
                "id": "un-singur-judet",
                "text": (
                    "Acest fișier acoperă un singur județ. Fiecare cameră notarială publică "
                    "separat, cu alt format, așa că acoperirea națională se construiește "
                    "județ cu județ, nu dintr-un singur parser."
                ),
                "severity": "note",
                "affects": ["acoperire"],
            },
        ],
    }

    share = document["summary"]["coverage"]["share"]
    print(f"acoperire: {100 * share:.1f}% din localitățile județului")
    # A parse that has lost a tenth of a county is not a source gap, it is broken, and
    # writing it would put a hole on the map that reads as cheap land.
    if share < 0.9:
        print(f"FATAL: only {100 * share:.1f}% of localities priced; not writing", file=sys.stderr)
        return 1

    out = ROOT / "data" / f"ghid-teren-{args.chamber}-{study.year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
