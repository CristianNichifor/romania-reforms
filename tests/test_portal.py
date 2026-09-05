"""Tests for the portal crawler, concentrated on the one failure that cannot be undone.

Everything else this importer can get wrong is a number that comes out crooked and can be
rebuilt tomorrow. Publishing a private individual's name cannot be rebuilt: the file goes to a
public Release, the Release is mirrored by whoever fetches it, and there is no recall. So the
tests that matter here are not about the arithmetic. They are about the invariant that a natural
person's name never reaches the output, and they are written to fail loudly when someone widens
the marker list without thinking about which side of that line a token falls on.

The second cluster covers the XML the service actually emits, as opposed to the XML it is
supposed to emit. ECRIS free text carries control characters that XML 1.0 forbids, and the
service re-emits them as numeric character references without validating them. One `&#4;` makes
an entire 1000-case response unparseable — which is how the first probe run lost 85% of a month
of Tribunalul Bucureşti while reporting success.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "simulators/justitie/scripts/import_portal.py"

spec = importlib.util.spec_from_file_location("import_portal", MODULE)
portal = importlib.util.module_from_spec(spec)
# Registered before execution because @dataclass resolves annotations through
# sys.modules[cls.__module__], which is None for a module loaded straight off a path.
sys.modules[spec.name] = portal
spec.loader.exec_module(portal)


# Names that must never be classified "legal", because that is what publishes them. Each is a
# real pattern from the party lists: a given name that collides with an institution word, a
# surname that collides with a country, initials that collide with a company form.
NATURAL_PERSONS = [
    "IONESCU MARIA-ROMANIA",
    "ROMAN VASILE",
    "SAVA ANA",
    "POPESCU I. I.",
    "RADU IF ANDREI",
    "CASA MARIA",
    "CAMERA ELENA",
    "MUNTEANU RA",
    "ŞTEFAN BIANCA DANIELA",
    "MANOLACHE ALEXANDRA LILIANA",
    "STOIAN ŞTEFAN",
]

LEGAL_PERSONS = [
    "SC ALFA CONSTRUCT SRL",
    "SC ALFA CONSTRUCT",
    "ALFA S.R.L.",
    "MUNICIPIUL TIMIŞOARA",
    "COMUNA JIBOU",
    "BANCA TRANSILVANIA SA",
    "DIRECŢIA GENERALĂ REGIONALĂ A FINANŢELOR PUBLICE",
    "SPITALUL JUDEŢEAN CLUJ",
    "BETA SRL ÎN INSOLVENŢĂ",
    "STATUL ROMÂN PRIN MINISTERUL FINANŢELOR",
    "CASA DE PENSII A JUDEŢULUI CLUJ",
    "ANAF",
    "ASOCIAŢIA DE PROPRIETARI NR 5",
    "CAMERA DE COMERŢ ŞI INDUSTRIE",
    "AUTORITATEA NAŢIONALĂ PENTRU CETĂŢENIE",
]


@pytest.mark.parametrize("name", NATURAL_PERSONS)
def test_natural_persons_are_never_classified_legal(name: str) -> None:
    # The asymmetric one. A false "natural" over-anonymises a company and costs a finding; a
    # false "legal" publishes somebody's name and cannot be taken back.
    assert portal.classify_party(name) == "natural"


@pytest.mark.parametrize("name", LEGAL_PERSONS)
def test_legal_persons_are_recognised(name: str) -> None:
    assert portal.classify_party(name) == "legal"


def test_fold_collapses_both_encodings_of_s_comma_and_t_comma() -> None:
    # ECRIS holds both the cedilla and the comma-below forms. Left unfolded they are different
    # strings, and one institution is counted as two.
    assert portal.fold("ŞTEFAN") == portal.fold("ȘTEFAN") == "STEFAN"
    assert portal.fold("AGENŢIA") == portal.fold("AGENȚIA") == "AGENTIA"


def test_hash_is_stable_across_spellings_and_depends_on_the_salt() -> None:
    assert portal.hash_name("ŞTEFAN ION", "s") == portal.hash_name("STEFAN ION", "s")
    assert portal.hash_name("ŞTEFAN ION", "a") != portal.hash_name("ŞTEFAN ION", "b")


def test_hash_does_not_contain_the_name() -> None:
    digest = portal.hash_name("POPESCU ION", "salt")
    assert "POPESCU" not in digest.upper()
    assert len(digest) == 32


def test_sanitize_drops_invalid_character_references() -> None:
    # The exact shape that killed a Tribunalul Bucureşti window: a decimal reference to a
    # control character, inside otherwise well-formed XML.
    bad = "<r><a>ok&#4;text</a><b>hex&#x1F;here</b></r>"
    with pytest.raises(ElementTree.ParseError):
        ElementTree.fromstring(bad)
    root = ElementTree.fromstring(portal.sanitize_xml(bad))
    assert root.find("a").text == "oktext"
    assert root.find("b").text == "hexhere"


def test_sanitize_preserves_valid_character_references() -> None:
    # Romanian text arrives as character references too. A sanitiser that ate those would
    # silently mangle every institution name with a diacritic in it.
    root = ElementTree.fromstring(portal.sanitize_xml("<r><c>keep&#233;&#x41;</c></r>"))
    assert root.find("c").text == "keepéA"


def test_sanitize_strips_raw_control_bytes() -> None:
    root = ElementTree.fromstring(portal.sanitize_xml("<r><d>raw\x04byte</d></r>"))
    assert root.find("d").text == "rawbyte"


def _dosar(xml: str):
    return ElementTree.fromstring(portal.sanitize_xml(xml))


PENAL_CASE = """
<Dosar xmlns="portalquery.just.ro">
  <parti>
    <DosarParte><nume>POPESCU ION</nume><calitateParte>Inculpat</calitateParte></DosarParte>
    <DosarParte><nume>MUNICIPIUL CLUJ</nume><calitateParte>Parte civila</calitateParte></DosarParte>
  </parti>
  <sedinte>
    <DosarSedinta><complet>P1</complet><data>2026-03-01T00:00:00</data>
      <solutie>Sentinta penala</solutie><solutieSumar>Condamna pe POPESCU ION</solutieSumar>
    </DosarSedinta>
  </sedinte>
  <caiAtac>
    <DosarCaleAtac><parteDeclaratoare>POPESCU ION</parteDeclaratoare>
      <tipCaleAtac>Apel</tipCaleAtac><data>2026-04-01T00:00:00</data></DosarCaleAtac>
  </caiAtac>
  <numar>1/1/2026</numar><data>2026-01-01T00:00:00</data>
  <institutie>TribunalulTIMIS</institutie><categorieCaz>Penal</categorieCaz>
</Dosar>
"""


def test_criminal_cases_publish_no_name_at_all() -> None:
    # GDPR Art. 10 is a prohibition on processing, not a disclosure rule, so no hashing scheme
    # cures it. In a criminal case even the municipality is withheld — the point is that nobody
    # can be placed in the case, and a named co-party narrows the field.
    tables = portal.Tables()
    portal.extract(_dosar(PENAL_CASE), "salt", tables, keep_summaries=True)

    assert all(row["nume"] is None for row in tables.parti)
    assert all(row["nume_fold"] is None for row in tables.parti)
    assert all(row["parte_nume"] is None for row in tables.cai_atac)
    # The free-text summary names the defendant outright. It is the likeliest leak in the file.
    assert all(row["solutie_sumar"] is None for row in tables.sedinte)
    assert tables.dosare[0]["is_penal"] is True


CIVIL_CASE = PENAL_CASE.replace(
    "<categorieCaz>Penal</categorieCaz>", "<categorieCaz>Civil</categorieCaz>"
)


def test_civil_cases_keep_the_institution_and_hash_the_individual() -> None:
    tables = portal.Tables()
    portal.extract(_dosar(CIVIL_CASE), "salt", tables, keep_summaries=True)

    by_role = {row["calitate"]: row for row in tables.parti}
    assert by_role["Parte civila"]["nume"] == "MUNICIPIUL CLUJ"
    assert by_role["Parte civila"]["nume_hash"] is None
    assert by_role["Inculpat"]["nume"] is None
    assert by_role["Inculpat"]["nume_hash"] is not None


def test_every_party_row_carries_exactly_one_identifier() -> None:
    # The invariant the audit checks over a whole crawl, asserted here on both branches: a row
    # with neither is a lost party, a row with both is a name published beside its own hash —
    # which would also defeat the hashing everywhere else, since the pair is a rainbow table.
    tables = portal.Tables()
    for case in (PENAL_CASE, CIVIL_CASE):
        portal.extract(_dosar(case), "salt", tables, keep_summaries=True)

    for row in tables.parti:
        assert (row["nume"] is None) != (row["nume_hash"] is None)


def test_no_summaries_flag_drops_free_text_in_non_criminal_cases() -> None:
    tables = portal.Tables()
    portal.extract(_dosar(CIVIL_CASE), "salt", tables, keep_summaries=False)
    assert tables.sedinte[0]["solutie_sumar"] is None


def test_window_shrinks_for_a_busy_court_and_grows_for_a_quiet_one() -> None:
    """The sizing rule, which is what replaced blind bisection.

    A month that returned 3,000 rows should ask for roughly a fifth of that next time; a year
    that returned 40 should reach much further. Both are projections of the same rows-per-day.
    """
    from datetime import timedelta

    busy = portal.next_window(3000, timedelta(days=30))
    assert timedelta(days=5) < busy < timedelta(days=7)  # 600/100 per day

    quiet = portal.next_window(40, timedelta(days=365))
    assert quiet > timedelta(days=365)


def test_an_empty_window_reaches_further_instead_of_stepping() -> None:
    """Most of a deep backfill is empty years at small courts. Stepping through them one window
    at a time is the cost the old month walker paid; reaching further is the point."""
    from datetime import timedelta

    assert portal.next_window(0, timedelta(days=365)) == min(
        timedelta(days=365) * portal.EMPTY_GROWTH, portal.MAX_WINDOW
    )


def test_the_window_never_leaves_its_bounds() -> None:
    """A court with one case in a decade must not ask for the decade in a single call — the
    coverage report would then be unable to say which part of it failed. A court that returned
    the whole cap in an hour must not be given a window below the floor either."""
    from datetime import timedelta

    assert portal.next_window(1, timedelta(days=365)) <= portal.MAX_WINDOW
    assert portal.next_window(100000, timedelta(days=1)) >= portal.MIN_WINDOW
