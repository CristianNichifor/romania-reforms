# UX guidelines — Romania Reforms

One family: the landing page and seven simulators. This file decides how they look and
read. It refines the fleet guideline in civic-ui (`docs/ux-guidelines.md`) and the shared
shell in `site/shell.mjs`; where the two disagree, civic-ui wins and this file is fixed.

Romanian strings below are agent-written: needs human review.

## 1. Users and top tasks

Readers are citizens, journalists and public servants who arrive from an article or a link,
mostly on a phone, and want to know what a reform would change. The simulators are
instruments for public debate, not calculators of entitlement.

| Page | Path | Top task | The one job of the first screen |
|---|---|---|---|
| Landing | `/` | Understand the argument | "Opt regiuni, nu 41" with its three numbers, then "Ce înseamnă pentru tine" |
| Reforma administrativă | `/administrative-reform/` | See the merged map for a scenario | The map of the proposed regions, with the scenario picker |
| Salarizarea publică | `/public-pay/` | Find a job and compare its pay | Search for a role, then its payslip |
| Transport public | `/transport/` | See what the bus network becomes | The map of the network for the scenario carried from administrativ |
| Reforma justiției | `/justitie/` | See which court a place goes to | The court map with the proposed arondare |
| Impozitul pe teren | `/impozit-teren/` | Estimate the land tax in a county | County picker and the estimate |
| Serviciile deconcentrate | `/deconcentrare/` | See which services move where | The list of services with their proposed seat |
| Companiile statului | `/companii-stat/` | See what the state owns and what it costs | The table of companies with totals |

## 2. Page anatomy

Every page, in this order:

1. Family bar — the shared shell from `site/shell.mjs` ("Simulatoare" / "Toate
   simulatoarele"), with the same names as the hub. No app renames itself.
2. H1 + one-line purpose (what the reader can do here, not what the project is).
3. Provenance line under the H1: `Date: <sursă>, <an>` (en: `Data: <source>, <year>`).
   One line, short source name, the year of the data, not of the build.
4. Primary task (map, search or picker) — visible without scrolling at 1440 and at 390.
5. Secondary views (tables, charts, method notes), each with its own source and as-of.
6. Footer: method, privacy (`/privacy.html`), source code, contact.

Map apps put 2–3 in the side panel; the panel is the page for anatomy purposes.

## 3. Content rules

- Romanian is the default language; English is a full alternative, not a partial one.
  Untranslated prose is a bug, not a fallback.
- Diacritics: ș ț with comma below, never ş ţ (cedilla). Enforced on the landing pages.
- Numbers in the reader's language: ro `1.234,5`, `92,2 %`, `21,7 km`; en `1,234.5`,
  `92.2%`. Use `Intl.NumberFormat` (civic-ui `formatRON` where vendored), never
  `toFixed` for display.
- Money: `lei` after the number (`1.250 lei`); large sums `1,23 mld lei`, `45,6 mil lei`
  (en `bn`, `m`). Euro only where the source is in euro, labelled `€`.
- Dates: ro `14 octombrie 2026` or `14.10.2026`; years as plain digits; ranges `2024–2025`.
- Units are spelled once per table header, not per cell.
- Tone: plain, second person where the reader acts ("Alege județul"), no slogans, no
  exclamation marks. A figure without a source does not ship.
- Touch wording: "Atinge" on touchscreens, "Apasă"/"Fă clic" only for pointers.
- Banned on the page (internal terms): raw data keys (`blocking`, `major`, `minor`,
  `alta`), dataset or file names, `UAT` without expansion on first use, `TODO`, `demo`
  in lower-case prose, schema codes and footnote markers such as `*1)`, English words in
  Romanian mode. Severities read "blocant / important / de reținut".

## 4. Data visualisation

- Colours from the civic-ui viz palette (colour-blind safe). Sequential ramps must stay
  distinct under protanopia and deuteranopia (the justitie ramp test is the model); no
  green → red ramps.
- Colour is never the only channel: legends name every class; categories also differ by
  label, pattern or position.
- Label bars and map classes directly; no dual axes; axes start at zero for bars.
- Every chart and map carries its source and as-of, and has a table alternative (a
  visible table or a "Vezi tabelul" toggle).
- Overlapping marks (Bucharest and Ilfov) are separated or inset, never stacked unreadably.
- Demo or partial data gets a badge on the chart itself, not only in the method page.

## 5. States

- Loading: a skeleton or message at once; for anything over 2 s (map tiles, large JSON)
  a staged message ("Se încarcă harta…", then "Se calculează…").
- Empty: say why and what to try ("Niciun rezultat pentru …; încearcă alt județ").
- Error: what failed, in the reader's language, and a "Reîncearcă" action; never a blank
  map or a stack trace.
- Demo data: badge "Date demonstrative" plus the reason, until real data replaces it.

## 6. Visual style, mobile and accessibility

**One style.** Light by default, built on civic-ui roles (`--civic-bg`, `--civic-surface`,
`--civic-text`, `--civic-action`); dark only when the reader's system asks for it or the
reader picks it. Token names say role, not appearance (the justitie `tokens.css` rule).

**Permitted deviations.**

| Simulator | Deviation | Why |
|---|---|---|
| `/administrative-reform/`, `/transport/`, `/impozit-teren/` | Dark map canvas and map side panel (`color-scheme: dark` on the map only) | Choropleths and networks are tuned against a dark basemap |
| `/justitie/` | Map pins `data-theme="dark"`; the statistics page follows the system | Same ramp, one set of contrast checks |
| `/public-pay/` | Blue series colour (`--series-1`) for charts | Two-hue validated chart palette; chrome still follows the family |
| `/deconcentrare/`, `/companii-stat/` | None | Document pages: light by default |

Everything outside the map canvas — family bar, H1, provenance line, forms, tables, footer —
looks the same on every page.

**Mobile (390 px).** No horizontal page scroll; wide tables scroll inside their own
container with the first column sticky; the primary task comes before secondary panels;
map panels collapse below the map. Touch targets ≥ 24 px, 44 px preferred.

**Accessibility.** WCAG 2.1 AA; axe with zero serious or critical issues on every page;
every control reachable and operable by keyboard with a visible focus ring; map content
also reachable as a list or table; honour `prefers-reduced-motion` (no animated map
transitions) and `forced-colors` (borders and focus stay visible).

## 7. Status vocabulary

One badge per app, in the family bar, from civic-ui's list (`StatusBadge`), and the hub
card must agree:

| Status | ro | Meaning |
|---|---|---|
| Live data | Date reale | Real data with a stated as-of date, refreshed on a documented schedule |
| Demo data | Date demonstrative | Synthetic, partial or sample data; nothing on the page is a measurement |
| Prototype | Prototip | The interaction is the point; say whether the data are real or demo |
| Archived | Arhivat | No longer updated; the as-of date is final |

"Prototip" describes the app, never the data: a simulator with real data and an unfinished
interface is "Date reale" with an honest method page.

## 8. Conformance

| Rule | Evidence |
|---|---|
| Every page carries the family bar and CSP | `tests/test_site_shell.py` |
| Every app registers the shell for its own path | `tests/test_site_shell.py`, `simulators/salarizare/app/tests/shell.test.ts`, `simulators/justitie/app/src/shell.test.ts`, `simulators/transport/app/src/shell.test.ts`, `simulators/impozit-teren/app/src/shell.test.ts`, `simulators/deconcentrare/app/src/shell.test.ts`, `simulators/companii-stat/app/src/shell.test.ts`, `simulators/administrativ/web/tests/shell.test.ts` |
| Landing describes itself, links privacy, leads with the argument | `tests/test_site_pages.py` |
| Comma-below diacritics on the landing pages | `tests/test_site_pages.py::test_romanian_text_uses_comma_below` |
| Romanian labels, not data keys | `simulators/companii-stat/app/src/labels.test.ts`, `simulators/deconcentrare/app/src/labels.test.ts`, `simulators/impozit-teren/app/src/labels.test.ts`, `simulators/salarizare/app/tests/i18n.test.tsx` |
| Numbers in the reader's language | `simulators/administrativ/web/tests/format.test.ts`, `simulators/administrativ/web/tests/lang.test.ts` |
| Colour-blind safe ramp | `simulators/justitie/app/src/ramp.test.ts`, `simulators/administrativ/web/tests/colour.test.ts` |
| Touch wording | `simulators/justitie/app/src/touch.test.ts` |
| Map legends | `simulators/transport/app/src/legend.test.ts` |
| Browser checks (civic-ui native controls, map render) | `simulators/administrativ/web/tests/browser/native-ui.spec.ts`, `simulators/transport/app/tests/browser/native-ui.spec.ts`, `simulators/impozit-teren/app/tests/browser/native-ui.spec.ts`, `simulators/justitie/app/tests/browser/map.spec.ts` |
| Every public-pay view renders | `simulators/salarizare/app/tests/views.test.tsx` |
| This guideline covers every simulator and cites real tests | `tests/test_ux_guidelines.py` |

Not yet enforced by a test: provenance line (rr #160 adds it), axe on every page, 390 px
no-horizontal-scroll, status badge vocabulary.

## 9. Known deviations backlog

From the live review (2026-10-14) and a source audit of `origin/dev`. Items marked *in
flight* belong to another session; do not start them in parallel.

1. Landing, `/deconcentrare/`, `/companii-stat/` are dark-first: `:root` sets the dark
   palette and light only under `prefers-color-scheme: light`. Flip to light-first.
2. Three palettes for chrome (dark map apps, light pages, public-pay neutrals); move
   chrome to civic-ui roles so only the map canvases differ.
3. No `Date: sursă, an` line under the H1 — *in flight* (#160).
4. justitie: overlapping Bucharest circles; administrativ: no legend for unit colours,
   mobile stats clipping; transport loader; impozit-teren gap under the sidebar and mobile
   ordering; companii-stat mobile table clipping — *in flight* (#161).
5. public-pay layout: menu below the H1, search after the lead, humanised codes, `*1)`
   markers — done (UX-7, #162).
6. English mode: public-pay view prose is still Romanian (RR-10). *Acasă (UX-25), Domenii (UX-21),
   Structură (UX-22), Distribuție (UX-23), Fluturaș (UX-24), Cât costă tot (UX-26) and Echivalențe
   (UX-27) are bilingual; Ce se schimbă, Meserii, Funcție cu funcție and Propunerea noastră follow.*
7. No status badge on any page. Agree the status per simulator with the owner (most
   use real data, so "Date reale"), then add the badge.
8. No as-of date on charts and maps beyond the provenance line.
9. No page-level axe or 390 px overflow check; add to the browser suites.
