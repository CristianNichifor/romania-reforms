# Design screens — target state (2026-10-14)

Static mockups of the five screens that fix the family look of the landing page and the seven
simulators. They follow `docs/ux-guidelines.md` (PR #163) and the civic-ui guideline; every
file is self-contained HTML with inline CSS that copies the civic-ui `neutral` token values
(`--civic-bg #f4f6f6`, `--civic-surface #ffffff`, `--civic-text #182b2c`, `--civic-muted
#475d60`, `--civic-action #006b60`, `--civic-danger #a31b34`, radius 6 px, the justitie
space/type scale) and the Okabe–Ito viz palette. No JS, no external requests. Open them in a
browser; each has a desktop layout and a 390 px layout (media query, or two phone frames side
by side for 04).

Romanian copy in the mockups is agent-written: **needs human review**. Figures are only those
already on the site or in `simulators/*/data` (41 → 8, 820 → 179, 659 → 56, 3.186 UAT, 241
instanțe, the Legea 153/2017 coefficients 3,32 / 3,47 / 6,00); anything else is "—".

No PNG screenshots were produced: the coordinator banned local Playwright runs during this
round (laptop memory). The "before" state is the live site on 2026-10-14 as described in
`docs/ux-guidelines.md` § 9 and `/tmp/fleet2/ux-review-notes.md`; an implementation session
with headroom should add `screens/*.png` at 1440 × 900 and 390 × 844 from these files.

| # | Screen | User task | Guideline sections | What changes vs today | File |
|---|---|---|---|---|---|
| 01 | Story-first landing | Understand the argument, then pick "your" question | ux-guidelines §1, §2, §6, §7 | Light-first on civic-ui roles (today dark-first with its own palette); family bar on the hub itself; H1 is the argument ("Opt regiuni, nu 41") with purpose and `Date:` line; three numbers as cards with the same type scale as the apps; every simulator card carries its status badge and its own `Date:` line; "în lucru" becomes a visible "Prototip" badge, not opacity | `screens/01-landing.html` |
| 02 | Map simulator template (administrative-reform; also transport, justitie) | See the merged map for a scenario and why a unit lands where it does | §2 (panel = page), §4, §5, §6 deviations | Panel on civic-ui light chrome, dark only on the map canvas; H1 + purpose + `Date:` in the panel; legend names every class and adds hatch/dashed outline so colour is never alone; "Vezi tabelul" alternative; staged loader, error + Reîncearcă, demo badge on the map; phone order map → panel, legend docked under the map; KPI tiles wrap instead of clipping | `screens/02-map-simulator-administrative-reform.html` |
| 03 | Public pay | Find a position and read its payslip | §2, §3, §4 | Chrome on family tokens (blue kept for series only); H1 → purpose → `Date:` → search → results → 11-card menu (UX-7 order); source marks as superscript with title; code secondary with annex locator; bars from zero with values printed; lei table beside the chart; four states | `screens/03-public-pay.html` |
| 04 | Impozit teren, mobile | Pick county, locality, zone, area; read the estimate | §2, §3, §5, §6 mobile | Phone order title → `Date:` → picker → estimate → small map → zone table → method (today the map and a gap come first); 44 px zone buttons; unit once in the header; sticky first column; loading / error / empty states with the county named | `screens/04-impozit-teren-mobile.html` |
| 05 | Shared nav and footer | Know where you are in the family and get back to the hub | §2, §6, §7 | One family bar for all eight pages (shell.mjs output restyled: surface background, 44 px, current page bold + 2 px action line, status badge at the right); fixed footer order Metodă · Confidențialitate · Codul sursă · Contact; measures for contrast and targets | `screens/05-shared-nav-footer.html` |

## Implementation notes and acceptance criteria

Each criterion is written so a test can assert it (see spec item UX-8 in
`docs/superpowers/specs/production-readiness.md`).

1. **Family bar everywhere.** Every page's first landmark is `nav[aria-label="Simulatoare"]`
   whose first link goes to the hub; the current page has `aria-current="page"`; the bar is
   ≥ 44 px tall; at 390 px the document has no horizontal overflow
   (`scrollWidth <= clientWidth`) while the bar scrolls inside itself.
2. **Light-first chrome.** `:root` on landing, deconcentrare and companii-stat sets the light
   civic-ui values; dark only under `prefers-color-scheme: dark` or `data-theme="dark"`. Map
   apps set `color-scheme: dark` only on the map element, never on `body`.
3. **Head of page.** In DOM order: family bar, `h1`, one `p` purpose, one `p.data-line`
   matching `^Date: .+, (19|20)\d\d` (en `^Data: `). In map apps the three live inside the
   side panel.
4. **Status badge.** Exactly one `.badge` per page, text in {Date reale, Date demonstrative,
   Prototip, Arhivat}; the hub card for that path shows the same text.
5. **Legends.** Every map legend lists every class with a label; at least one non-colour
   channel (hatch, outline style, marker shape, or inline label) distinguishes classes; a
   table alternative is reachable from the panel ("Vezi tabelul …").
6. **Charts.** Bars start at zero, values printed next to bars, one y axis, source line
   under every chart and map.
7. **States.** Loader text appears within 100 ms and changes after 2 s ("Se încarcă harta…" →
   "Se calculează…"); error state contains a button "Reîncearcă"; empty state names the query
   and a suggestion; demo data shows "Date demonstrative" on the chart or map itself.
8. **Targets and contrast.** All interactive elements ≥ 24 × 24 px (44 preferred on touch);
   axe-core reports zero serious/critical issues per page; the token pairs in
   `05-shared-nav-footer.html` § Măsuri stay ≥ 4.5:1.
9. **Mobile order (impozit-teren).** At 390 px the estimate block precedes the map in DOM
   and visual order; the zone table scrolls inside `.table-scroll` with a sticky first column.
10. **Public pay.** Search input precedes the section menu; source marks render as `sup`
    with a `title`; the position code is not part of the heading text.
