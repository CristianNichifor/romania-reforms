"""The asking-price dataset, and the politeness that produced it.

Two things are guarded here and they are unusual company. The first is ordinary: that the
quartiles are quartiles, that a locality with too few offers has no median, and that every row
joins to a locality the rest of the project knows.

The second is that the crawler cannot be rude. `politete.py` is the only code in this
repository that fetches from a site which did not publish itself to be fetched, and its whole
value is a set of refusals — robots.txt as a gate rather than a suggestion, a floor under the
delay, a budget on the run, and a stop rather than a retry when the host says no. Those are
properties nothing else would notice breaking: a crawler with its manners removed still returns
the same data, right up until the day it is blocked and the dataset can never be rebuilt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "simulators" / "impozit-teren" / "data"
SCRIPTS = ROOT / "simulators" / "impozit-teren" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def latest(prefix: str) -> dict:
    found = sorted(DATA.glob(f"{prefix}-*.json"))
    if not found:
        pytest.skip(f"{prefix} is not built")
    return json.loads(found[-1].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def listings() -> dict:
    return latest("anunturi-teren")


# ---- the dataset ---------------------------------------------------------------------


def test_quartiles_are_ordered(listings):
    for row in listings["localities"]:
        asked = row["askedEurPerM2"]
        if asked is None:
            continue
        assert asked["p25"] <= asked["median"] <= asked["p75"]
        assert asked["p25"] > 0


def test_a_median_needs_enough_offers_to_have_a_middle(listings):
    """Thin localities keep their count and lose their median, rather than disappearing."""
    floor = listings["assumptions"]["minOffers"]
    for row in listings["localities"]:
        if row["usableOffers"] < floor:
            assert row["askedEurPerM2"] is None, row["name"]


def test_the_placeholder_prices_are_gone(listings):
    """Offers at 17 EUR for a whole parcel are 'price on request' wearing a number."""
    floor = listings["assumptions"]["minEurPerM2"]
    for row in listings["localities"]:
        assert row["usableOffers"] + row["droppedBelowFloor"] == row["offers"]
        if row["askedEurPerM2"]:
            assert row["askedEurPerM2"]["p25"] >= floor


def test_truncation_is_declared_rather_than_hidden(listings):
    """One page is read per locality, so a busy one is a partial count and must say so."""
    per_page = listings["assumptions"]["perPage"]
    for row in listings["localities"]:
        assert row["truncated"] == (row["totalOffersReported"] > per_page)
    declared = sum(1 for r in listings["localities"] if r["truncated"])
    assert listings["summary"]["truncatedLocalities"] == declared


def test_every_locality_joins_to_a_priced_one(listings):
    """The join is by folded name, so a wrong SIRUTA is the failure mode worth testing.

    Every row must name a locality that the notary grids also price, or the asking price has
    nothing to sit beside and the import was pointless.
    """
    import re

    known = set()
    for path in DATA.glob("valoare-teren-*.json"):
        if "nationala" in path.name:
            continue
        county = re.search(r"valoare-teren-([a-z]{1,2})-", path.name).group(1).upper()
        for locality in json.loads(path.read_text(encoding="utf-8"))["localities"]:
            known.add((county, locality["siruta"]))
    for row in listings["localities"]:
        assert (row["county"], row["siruta"]) in known, f"{row['name']} does not join"


def test_a_partial_run_says_so(listings):
    """A budget that ran out must leave a mark, or a slice looks like the country."""
    summary = listings["summary"]
    assert summary["localities"] == len(listings["localities"])
    assert summary["localitiesWithMedian"] == sum(
        1 for r in listings["localities"] if r["askedEurPerM2"]
    )
    if summary["stoppedBecause"] is not None:
        assert isinstance(summary["stoppedBecause"], str)


def test_no_listing_content_is_stored(listings):
    """Statistics, not a mirror. The distinction is the whole basis for reading the source."""
    allowed = {
        "siruta", "name", "county", "totalOffersReported", "truncated", "offers",
        "usableOffers", "droppedBelowFloor", "askedEurPerM2", "medianAreaM2", "privateShare",
    }
    for row in listings["localities"]:
        assert set(row) <= allowed, f"unexpected field: {set(row) - allowed}"


def test_the_two_blocking_caveats_are_present(listings):
    """Asking is not paid, and an advertised parcel is not the average hectare.

    Both change what the number means rather than how precise it is, so neither may be
    downgraded to a note without somebody noticing.
    """
    severity = {limit["id"]: limit["severity"] for limit in listings["limitations"]}
    assert severity.get("pret-cerut-nu-pret-platit") == "blocking"
    assert severity.get("anunturile-sunt-selectate") == "blocking"


# ---- the crawler ---------------------------------------------------------------------


def test_robots_is_a_gate_and_not_a_suggestion(tmp_path, monkeypatch):
    """A disallowed URL raises. There is no flag to make it not raise."""
    import politete

    fetcher = politete.Politete(cache=tmp_path, budget=5)
    rules = __import__("urllib.robotparser", fromlist=["robotparser"]).RobotFileParser()
    rules.parse(["User-agent: *", "Disallow: /api/"])
    monkeypatch.setattr(fetcher, "_rules", lambda url: rules)

    with pytest.raises(politete.Disallowed):
        fetcher.get("https://example.invalid/api/query")


def test_an_unreachable_robots_grants_nothing(tmp_path):
    """A host that cannot be reached at all has not said yes."""
    import politete

    fetcher = politete.Politete(cache=tmp_path, budget=5)
    with pytest.raises(politete.Blocked):
        fetcher.get("https://this-host-does-not-resolve.invalid/anything")


@pytest.mark.parametrize(
    ("code", "forbidden"),
    [
        (401, True),   # the host refuses to show its rules, which is a refusal
        (403, True),
        (404, False),  # no robots.txt is not a prohibition — most of the web has none
        (410, False),
        (500, True),   # a broken server is not consent
        (503, True),
    ],
)
def test_each_robots_answer_means_what_the_standard_says(tmp_path, monkeypatch, code, forbidden):
    """RFC 9309 §2.3.1: the three cases are different, not three flavours of failure.

    The first version of this treated every failed robots fetch as a refusal, which sounds
    like the cautious choice and is simply wrong — e-licitatie.ro answers 404 and publishes an
    API called `api-pub`, so refusing it would have been the crawler inventing a prohibition
    nobody stated.
    """
    import urllib.error

    import politete

    def raise_http(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, code, "no", {}, None)

    monkeypatch.setattr(politete.urllib.request, "urlopen", raise_http)
    fetcher = politete.Politete(cache=tmp_path, budget=0, log=lambda m: None)

    if forbidden:
        with pytest.raises(politete.Blocked):
            fetcher.allowed("https://example.invalid/anything")
    else:
        assert fetcher.allowed("https://example.invalid/anything") is True


def test_the_budget_is_a_ceiling_on_live_requests(tmp_path, monkeypatch):
    """A paging bug and an attack are indistinguishable from the far end."""
    import politete

    fetcher = politete.Politete(cache=tmp_path, budget=0)
    rules = __import__("urllib.robotparser", fromlist=["robotparser"]).RobotFileParser()
    rules.parse(["User-agent: *", "Allow: /"])
    monkeypatch.setattr(fetcher, "_rules", lambda url: rules)

    with pytest.raises(politete.BudgetSpent):
        fetcher.get("https://example.invalid/allowed")


def test_the_cache_answers_without_the_network(tmp_path, monkeypatch):
    """A cached page costs the host nothing, which is what makes a slow crawler affordable."""
    import politete

    fetcher = politete.Politete(cache=tmp_path, budget=0)
    url = "https://example.invalid/page"
    # Bytes, because the cache stores what came off the wire. Half of what a public body
    # publishes is a spreadsheet, so decoding at the door would corrupt it.
    fetcher._store(url, b"<html>hello</html>")
    assert fetcher.get(url) == "<html>hello</html>"
    assert fetcher.get_bytes(url) == b"<html>hello</html>"
    assert fetcher.from_cache == 2
    assert fetcher.fetched == 0


def test_the_delay_never_drops_below_the_floor(tmp_path, monkeypatch):
    """A host asking for less than we chose does not get taken up on it."""
    import politete

    fetcher = politete.Politete(cache=tmp_path, delay=5.0, budget=1)
    rules = __import__("urllib.robotparser", fromlist=["robotparser"]).RobotFileParser()
    rules.parse(["User-agent: *", "Crawl-delay: 1", "Allow: /"])
    monkeypatch.setattr(fetcher, "_rules", lambda url: rules)
    assert fetcher.crawl_delay("https://example.invalid/x") == 5.0

    slower = politete.Politete(cache=tmp_path, delay=5.0, budget=1)
    strict = __import__("urllib.robotparser", fromlist=["robotparser"]).RobotFileParser()
    strict.parse(["User-agent: *", "Crawl-delay: 30", "Allow: /"])
    monkeypatch.setattr(slower, "_rules", lambda url: strict)
    assert slower.crawl_delay("https://example.invalid/x") == 30.0


def test_there_is_no_way_to_pretend_to_be_a_browser():
    """The user agent is one string with a contact URL, and nothing rotates it.

    This is the test that protects the project rather than the data. Everything else in
    politete.py can be argued about; a crawler that disguises itself has decided to defeat a
    decision the site already made, and that is the line this file does not cross.
    """
    import ast

    import politete

    assert "github.com/CristianNichifor/romania-reforms" in politete.UA

    # Read the code and not the prose. The docstring is *about* these techniques — it explains
    # which ones the file refuses and why — so a grep over the raw source fails on the very
    # paragraph that promises not to do them. What must stay clean is what the module executes.
    source = (SCRIPTS / "politete.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]
    names = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)] + [
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    ]
    executed = " ".join(literals + names)
    for banned in ("Mozilla", "Chrome", "Safari", "choice", "proxy", "Proxy", "Cookie"):
        assert banned not in executed, (
            f"politete.py *does* {banned!r}, it does not merely mention it"
        )
