"""The target-state design screens keep the contract UX-8 wrote for them (UX-37).

They are the reference the live pages are measured against, so they must themselves be
self-contained, light-first on civic-ui roles, headed the way § 2 of the guideline says, and
badged from the § 7 vocabulary, in comma-below Romanian. Each frame in a screen (desktop and
phone mock-ups share one file) is checked on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCREENS = sorted((ROOT / "docs/design/screens").glob("*.html"))
STATUS = {"Date reale", "Date demonstrative", "Prototip", "Arhivat"}
PAGE = pytest.mark.parametrize("screen", SCREENS, ids=lambda p: p.name)


def read(screen: Path) -> str:
    return screen.read_text(encoding="utf-8")


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", fragment)).strip()


def test_there_are_screens():
    assert len(SCREENS) >= 5, "the design round shipped five screens"


@PAGE
def test_screens_are_self_contained(screen):
    """No scripts, no fetched assets: the file is the whole page."""
    html = read(screen)
    assert "<script" not in html
    assert not re.search(r'<(?:link|img|iframe|source|video|audio)\b[^>]*\b(?:href|src)="https?://', html)
    assert not re.search(r"@import|url\(\s*[\"']?https?://", html)


@PAGE
def test_screens_use_comma_below(screen):
    assert not re.search("[şţŞŢ]", read(screen))


@PAGE
def test_screens_are_light_first_on_civic_ui_roles(screen):
    """Criterion 2: the plain `:root` is light with civic-ui roles; dark is the opt-in only."""
    style = re.search(r"<style>(.*?)</style>", read(screen), re.S).group(1)
    media = [m.group(1) for m in re.finditer(r"@media\s*\(prefers-color-scheme:\s*(\w+)\)", style)]
    assert media == ["dark"], f"{screen.name}: colour-scheme overrides {media}"
    root = re.search(r":root\s*\{(.*?)\}", style, re.S).group(1)
    assert "color-scheme:light" in root.replace(" ", "")
    for role in ("--civic-bg", "--civic-surface", "--civic-text", "--civic-action"):
        assert f"{role}:" in root, f"{screen.name}: {role} is not set on :root"


@PAGE
def test_each_frame_leads_with_the_family_bar_then_h1_purpose_and_data_line(screen):
    """Criteria 1 and 3: nav[aria-label="Simulatoare"] whose first link is the hub, then h1,
    the purpose line and one `p.data-line` reading "Date: <sursă>, <an>". A frame that only
    demonstrates the bar (screen 05) has no h1 of its own and is checked for the bar alone."""
    html = read(screen)
    body = html[html.index("<body") :]
    frames = re.split(r"(?=<header class=\"family\")", body)[1:]
    assert frames, f"{screen.name}: no family bar"
    for frame in frames:
        nav = re.search(r'<nav aria-label="Simulatoare">(.*?)</nav>', frame, re.S)
        assert nav, f"{screen.name}: a frame has no Simulatoare navigation"
        hub = re.search(r'<a class="hub" href="([^"]+)"', frame).group(1)
        assert hub in {"./", "../"}, f"{screen.name}: the hub link is {hub!r}"
        h1 = frame.find("<h1")
        if h1 < 0:
            continue
        assert nav.start() < h1, f"{screen.name}: the family bar does not precede the h1"
        line = re.search(r'<p class="data-line[^"]*">(.*?)</p>', frame, re.S)
        assert line and h1 < line.start(), f"{screen.name}: a frame lacks the data line under its h1"
        purpose = re.search(r'<p class="purpose[^"]*">', frame)
        if purpose:
            assert h1 < purpose.start() < line.start(), f"{screen.name}: head order is not h1, purpose, data line"
        # "Date: <sursă>, <an>", where the year may sit inside a phrase ("Recensământ 2021").
        assert re.match(r"^Date: .+, .*(19|20)\d\d", text(line.group(1))), text(line.group(1))


@PAGE
def test_every_badge_uses_the_status_vocabulary(screen):
    """Criterion 4: the words on a badge are the § 7 vocabulary, nothing else; a simulator's
    bar carries exactly one, and the hub shows one on every card instead."""
    html = read(screen)
    badges = [text(b) for b in re.findall(r'<span class="badge[^"]*"[^>]*>(.*?)</span>', html, re.S)]
    assert badges, f"{screen.name}: no status badge"
    wrong = [b for b in badges if b not in STATUS]
    assert not wrong, f"{screen.name}: badges outside the vocabulary: {wrong}"
    for frame in re.findall(r'<header class="family".*?(?=<header class="family"|\Z)', html, re.S):
        bar = re.search(r'<header class="family">(.*?)</header>', frame, re.S).group(1)
        is_hub = 'class="hub" href="./"' in bar
        in_bar = len(re.findall(r'class="badge', bar))
        if is_hub:
            cards = re.findall(r'<li><a href="[a-z-]+/">(.*?)</a></li>', frame, re.S)
            assert cards and all('class="badge' in card for card in cards), f"{screen.name}: a hub card has no badge"
        else:
            assert in_bar == 1, f"{screen.name}: a simulator bar carries {in_bar} badges, not one"


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_measured_token_pairs_keep_their_contrast():
    """Criterion 8: the pairs the shared-nav screen lists under „Măsuri” are recomputed; each
    stays at or above AA 4.5:1 and the ratio written beside it is the one measured."""
    html = read(ROOT / "docs/design/screens/05-shared-nav-footer.html")
    card = re.search(r"<strong>Contrast</strong><p class=\"source\">(.*?)</p>", html, re.S).group(1)
    pairs = re.findall(
        r"<code>(#[0-9a-f]{6})</code> pe (?:<code>(#[0-9a-f]{6})</code>|(alb)) ≈ (\d+):1", card
    )
    assert len(pairs) >= 4, card
    for fg, bg, white, claimed in pairs:
        ratio = contrast(fg, "#ffffff" if white else bg)
        assert ratio >= 4.5, f"{fg} on {bg or 'white'} is {ratio:.2f}:1"
        assert abs(ratio - int(claimed)) <= 1, f"{fg} on {bg or 'white'}: measured {ratio:.2f}, written {claimed}"


def test_public_pay_screen_orders_search_before_menu_and_keeps_codes_out_of_headings():
    """Criterion 10: the search input precedes the section menu, every source mark is a `sup`
    with a title, and no position code sits inside a heading."""
    html = read(ROOT / "docs/design/screens/03-public-pay.html")
    search = re.search(r'<input id="q" type="search"', html)
    menu = re.search(r'<ul class="menu">', html)
    assert search and menu and search.start() < menu.start(), "the search does not precede the menu"
    marks = re.findall(r'<sup class="mark"([^>]*)>', html)
    assert marks and all('title="' in attrs for attrs in marks), "a source mark has no title"
    headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.S)
    assert headings and not any('class="code"' in h for h in headings), "a position code sits inside a heading"


def test_impozit_teren_phone_frame_puts_the_estimate_before_the_map_and_pins_the_zone_column():
    """Criterion 9 (the DOM part): at 390 px the estimate block comes before the map and the
    zone table; the table scrolls inside `.table-scroll` with a sticky first column."""
    html = read(ROOT / "docs/design/screens/04-impozit-teren-mobile.html")
    phone = html[html.index("pasul 2: estimarea") :]
    estimate = phone.find('<div class="est"')
    minimap = phone.find('<div class="minimap"')
    table = phone.find('<div class="table-scroll">')
    assert 0 < estimate < minimap < table, "the phone frame is not estimate → map → table"
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    assert re.search(r"\.table-scroll\{[^}]*overflow-x:auto", style)
    assert re.search(r"\.table-scroll th:first-child,\.table-scroll td:first-child\{[^}]*position:sticky;left:0", style)
