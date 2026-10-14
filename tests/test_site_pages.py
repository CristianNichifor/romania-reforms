"""Landing page metadata, the English landing page and the privacy page (RR-5)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
HOST = "https://projects.cristian-nichifor.com/romania-reforms/"
ISSUES = "https://github.com/CristianNichifor/romania-reforms/issues"


def read(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def meta(html: str, attr: str, key: str) -> str | None:
    match = re.search(rf'<meta\s+{attr}="{re.escape(key)}"\s+content="([^"]*)"', html)
    return match.group(1) if match else None


@pytest.mark.parametrize(
    ("page", "url", "lang"),
    [("index.html", HOST, "ro"), ("en/index.html", HOST + "en/", "en")],
)
def test_landing_pages_describe_themselves(page, url, lang):
    html = read(page)
    assert f'<html lang="{lang}">' in html
    assert meta(html, "name", "description")
    assert f'<link rel="canonical" href="{url}" />' in html
    assert meta(html, "property", "og:title")
    assert meta(html, "property", "og:description")
    assert meta(html, "property", "og:url") == url
    assert meta(html, "property", "og:type") == "website"
    assert f'<link rel="alternate" hreflang="ro" href="{HOST}" />' in html
    assert f'<link rel="alternate" hreflang="en" href="{HOST}en/" />' in html


def test_landing_pages_link_each_other_and_the_privacy_page():
    ro, en = read("index.html"), read("en/index.html")
    assert 'href="en/index.html"' in ro and 'href="privacy.html"' in ro
    assert 'href="../index.html"' in en and 'href="../privacy.html#en"' in en


def test_english_landing_links_every_simulator():
    def main_list(page: str) -> str:
        return re.sub(r"<nav .*?</nav>", "", read(page), flags=re.S)

    ro_links = re.findall(r'<li>\s*<a href="([a-z-]+/)">', main_list("index.html"))
    en_links = re.findall(r'<li>\s*<a href="\.\./([a-z-]+/)">', main_list("en/index.html"))
    assert en_links == ro_links


def test_privacy_page_states_what_the_code_shows_in_both_languages():
    html = read("privacy.html")
    assert '<html lang="ro">' in html
    assert '<section id="en" lang="en">' in html
    assert "Cristian Nichifor" in html
    assert ISSUES in html
    for fact in ("cookie", "Cloudflare", "localStorage"):
        assert html.count(fact) >= 2, fact
    assert "analytics" in html.lower() and "analiză" in html
    assert "@" not in re.sub(r"<style>.*?</style>", "", html, flags=re.S)


@pytest.mark.parametrize("page", ["index.html", "brief.html", "privacy.html", "en/index.html"])
def test_romanian_text_uses_comma_below(page):
    html = read(page)
    assert not re.search("[şţŞŢ]", html)


@pytest.mark.parametrize(
    ("page", "prefix", "argument", "for_you"),
    [
        ("index.html", "", "Opt regiuni, nu 41", "Ce înseamnă pentru tine"),
        ("en/index.html", "../", "Eight regions, not 41", "What it means for you"),
    ],
)
def test_landing_leads_with_the_argument_then_what_it_means_for_you(
    page, prefix, argument, for_you
):
    """UX review: the argument and three headline numbers first, then the reader's own case,
    then every simulator."""
    html = read(page)
    lead = html.index(f"<h2>{argument}</h2>")
    you = html.index(f"<h2>{for_you}</h2>")
    simulators = html.index('<section class="simulators">')
    assert lead < you < simulators
    assert html[lead:you].count('<div class="headline-number">') == 3
    assert f'href="{prefix}brief.html"' in html[lead:you]
    for target in ("public-pay/#/payslip", "transport/", "impozit-teren/"):
        assert f'href="{prefix}{target}' in html[you:simulators]


@pytest.mark.parametrize(
    ("page", "word"), [("index.html", "Date:"), ("en/index.html", "Data:")]
)
def test_landing_names_its_data_under_the_h1(page, word):
    """UX-5: "Date: <sursă>, <an>" right under the H1, and every year is the one the data files
    carry, so the landing cannot quietly age."""
    import json

    html = read(page)
    match = re.search(r"<h1>[^<]*</h1>\s*<p class=\"data-line\">\s*(.*?)\s*</p>", html, re.S)
    assert match, "no data line under the H1"
    line = re.sub(r"\s+", " ", match.group(1))
    assert line.startswith(word)
    data = ROOT / "simulators"
    periods = {
        "CSM": json.loads((data / "justitie/data/instante-2025.json").read_text("utf-8"))["period"],
        "ANFP": json.loads(
            (data / "deconcentrare/data/deconcentrare.json").read_text("utf-8")
        )["period"],
        "Codul fiscal" if word == "Date:" else "Fiscal Code": json.loads(
            (data / "impozit-teren/data/cod-fiscal-teren-2026.json").read_text("utf-8")
        )["period"],
    }
    companii = json.loads((data / "companii-stat/data/companii-stat.json").read_text("utf-8"))
    periods["Ministerul Finanțelor" if word == "Date:" else "Ministry of Finance"] = companii[
        "period"
    ].replace("-", "–")
    for source, period in periods.items():
        assert f"{source}, {period}" in line, (source, period, line)
    footer = data / "salarizare/app/src/i18n.ts"
    package_date = re.search(r"MMFTSS din (\d\d\.\d\d\.\d{4})", footer.read_text("utf-8")).group(1)
    assert f"MMFTSS, {package_date}" in line


@pytest.mark.parametrize(
    ("page", "word"), [("index.html", "Date:"), ("en/index.html", "Data:")]
)
def test_every_simulator_card_names_its_own_data(page, word):
    """UX-11: each simulator card repeats the source and year the H1 data line already
    states for it, so a reader scanning cards sees the as-of without the legend."""
    html = read(page)
    head = re.search(r"<h1>[^<]*</h1>\s*<p class=\"data-line\">\s*(.*?)\s*</p>", html, re.S)
    legend = re.sub(r"\s+", " ", head.group(1))
    cards = re.findall(
        r"<li>\s*<a href=\"(?:\.\./)?([a-z-]+)/\">(.*?)</a>\s*</li>", html, re.S
    )
    simulators = [
        "administrative-reform", "public-pay", "transport", "justitie",
        "impozit-teren", "deconcentrare", "companii-stat",
    ]
    by_path = dict(cards)
    assert set(simulators) <= set(by_path), "a simulator card is missing"
    for path in simulators:
        card = by_path[path]
        line = re.search(r"<div class=\"card-data\">\s*(.*?)\s*</div>", card, re.S)
        assert line, f"{page}: {path} has no card data line"
        text = re.sub(r"\s+", " ", line.group(1))
        assert text.startswith(word), f"{page}: {path}: {text}"
        assert text[len(word) :].strip() in legend, f"{page}: {path}: not in the H1 line"
