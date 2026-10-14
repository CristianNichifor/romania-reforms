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
        assert f'href="{prefix}{target}"' in html[you:simulators]
