# Production readiness

Status legend: todo · done · blocked · needs-human. Each item names the test that proves it.
Translations written for these items are marked **needs human review**.

## A. Old paths keep working

### RR-1 Renamed simulator paths redirect — done (stubs need the workflow line: needs-human)

The English paths (#147) renamed `administrativ/` to `administrative-reform/` and
`salarizare/` to `public-pay/`. The old addresses are linked from outside the repository and
answer 404 on `projects.cristian-nichifor.com/romania-reforms/` today.

- Given a request for `/romania-reforms/administrativ/<rest>?<query>`,
  when the Pages middleware handles it,
  then it answers 301 with `Location: /romania-reforms/administrative-reform/<rest>?<query>`
  (relative, so the hub host is kept; the browser carries the `#hash` over). Same for
  `salarizare/` to `public-pay/`, and for the bare `/romania-reforms/administrativ`.
- Given the deploy's staged site directory,
  when `scripts/redirect_stubs.py <dir>` runs,
  then every renamed path has an `index.html` stub (canonical to the new address, `noindex`,
  meta refresh, script that keeps the rest of the path, query and hash) and `_redirects`
  carries a 301 rule per renamed path, with any existing rules kept.
- The map of renamed paths lives once, in `functions/renamed-paths.js`; the stub generator
  reads it.

Tests: `tests/test_deploy_paths.py` (stubs and `_redirects` exist for every renamed path;
middleware redirects, through `node --test tests/renamed_paths_middleware.test.mjs`).

The middleware ships with the deploy as is. The stubs and `_redirects` need one line in
`deploy-pages-cloudflare.yml`, which this repository's automation cannot push: the diff is
in the PR body (needs-human).

## B. Reliability and coverage

### RR-7 Portal snapshot retries 5xx — done

- Given the portal answers HTTP 5xx (520 seen in runs 38130733364 and 37919050016),
  when the importer makes a request,
  then it retries with exponential backoff before the shard records a failure; a 4xx is not
  retried.

Test: `tests/test_portal_retry.py` (520 then 200 succeeds after one retry; persistent 520
raises after the configured attempts; 403 is not retried).

### RR-6 Salary app tests every view — done

- Given `simulators/salarizare/app`, when `npm test` runs, then it fails if there are no
  tests (`--passWithNoTests` removed) and at least one test renders each of Payslip,
  Structure, Proposal and Merges.

Test: `simulators/salarizare/app/tests/views.test.tsx`, run by `npm test` and by `npm run build` (CI builds the app but does not run its `npm test`).

### RR-8 Land tax shows each county's source year — done

- Given a county's notarial guide year, when the table renders, then the year is shown for
  that county (and in the county picker when older than the newest guide: BR, BZ, DB, PH, VN
  are 2025, VL is 2024), and a county the national estimate values carries an "estimat" badge.
- The brief's "10 estimated counties" is out of date: `valoare-nationala-2026.json` now has
  all 42 counties `measured`, so the badge renders for none today and returns if a chamber
  stops publishing.

Test: `simulators/impozit-teren/app/src/sources.test.ts`.

## C. Shared shell

### RR-3 Shared navigation — done

- Given the landing page or any simulator, when it renders, then it has
  `<nav aria-label="Simulatoare">` linking the home page and all seven simulators, marking
  the current one with `aria-current="page"`.
- One source, `site/shell.mjs`: the apps apply it with the `siteShell()` Vite plugin at their
  `<!-- rr-nav -->` marker; the static pages in `site/` carry its output verbatim.

Tests: `src/shell.test.ts` (or `tests/shell.test.ts`) in every simulator runs the app's own
Vite config over its HTML entries; `tests/test_site_shell.py` checks the static pages, every
app's entries and `scripts/check_site_shell.py`, which checks an assembled `dist/` (the deploy
runs it once the workflow line in the PR is added: needs-human).

### RR-5 Landing metadata and privacy — done (publishing `privacy.html` and `en/` needs the workflow line: needs-human)

- Given `site/index.html`, then it has a meta description, Open Graph tags and a canonical
  link on `projects.cristian-nichifor.com/romania-reforms/`, links `privacy.html`, and offers
  English.
- Given `site/privacy.html`, then it states, in Romanian and English, what the code shows: no
  cookies, no analytics, hosting on Cloudflare Pages, operator Cristian Nichifor, contact
  through the repository's GitHub issues. English text: needs human review.
- Given `site/en/index.html`, then it is the landing page in English with the same simulator
  list (needs human review), linked both ways with `hreflang` alternates.

Test: `tests/test_site_pages.py`.

### RR-9 Content Security Policy — done

- Given every built page, then it carries a CSP `<meta http-equiv>`: everything `'self'`,
  inline styles allowed, `data:`/`blob:` images and workers, no objects. The dev server is
  exempt because it injects inline scripts of its own.
- Checked by loading every assembled page in Chromium: no CSP violations, no console errors.

Tests: as RR-3.

## D. Locale

### RR-10 English for the salary simulator — partial (shell done; view prose remains Romanian: needs-human)

- Given the salary app, when the link carries `lang=en` (administrativ's rule: the hash decides,
  Romanian by default), then the navigation, controls, messages and footer render in English,
  a switch links the other language, and the scenario keeps its language through the round
  trip. Translations: needs human review.
- Not done: the prose inside the eleven views (about 5,000 lines of Romanian JSX). In English a
  note says the views are still Romanian. Translating them is a separate, reviewable piece.

Test: `simulators/salarizare/app/tests/i18n.test.tsx`.

## E. UX review (coordinator, 2026-10-14)

### UX-1 Landing leads with the argument — done

- Given the landing page (RO and EN), then "Opt regiuni, nu 41" with three headline numbers
  already stated on the page (41 → 8, 820 → 179, 659 → 56) and a link to the brief comes first,
  then "Ce înseamnă pentru tine" (salary, bus, land tax), then every simulator.

Test: `tests/test_site_pages.py::test_landing_leads_with_the_argument_then_what_it_means_for_you`.

### UX-2 Romanian on the page — done

- Severities print as "blocant / important / de reținut", not the data's English keys
  (impozit-teren, companii-stat, deconcentrare, salarizare payslip); "alta" → "altă"; lei
  amounts in companii-stat as "1,23 mld" / "45,6 mil".
- administrativ prints decimals in the reader's language ("92,2 %", "21,7 km").

Tests: `labels.test.ts` (companii-stat, deconcentrare, impozit-teren), salarizare
`tests/i18n.test.tsx`, administrativ `tests/format.test.ts`.

### UX-3 Accessibility fixes — done

- justitie grades blue → orange; the ramp is simulated under protanopia and deuteranopia and
  every step stays apart (the old green → red ramp fails the same test).
- justitie's map hint says "Atinge …" on touchscreens.
- transport: panel links readable on the dark panel (was the browser's default blue).

Tests: justitie `src/ramp.test.ts`, `src/touch.test.ts`; transport is CSS only.

### UX-4 Carry the scenario to transport — done

- Given the administrative map, then "Deschide în Transport →" opens the transport map on the
  same hash (both read it).

Test: administrativ `tests/transport-link.test.ts`.

### Not done from the review (needs a follow-up)

"Date: <sursă>, <an>" under every H1; overlapping Bucharest circles (justitie); a legend for
the administrative unit colours and mobile stats clipping; public-pay layout (menu below the H1,
search after the lead, humanised codes and "*1)" markers); transport loader; impozit-teren gap
under the sidebar and mobile ordering; companii-stat mobile table clipping.

### UX-7 Public-pay layout — done (Romanian labels: needs human review)

- Given the salary app's first screen, then the H1 and its lead come first, the function
  search follows the lead, and the eleven-card section menu sits below them; every other view
  draws the menu under its own H1 and lead. While a view's data is still loading or failed,
  the menu is still on the page.
- Given a position whose name carries a source mark ("Farmacist primar*1)", "Rector*)",
  "Director unitate de învățământ*) **)"), then the mark renders as a superscript, in the place
  the sheet put it, with an `aria-label` and title saying it is a note from the source table
  whose text is not in this tool's data. No footnote text is invented: the regime files carry
  none.
- Given a position code ("153.II.31.18", "21.00303045.04"), then it appears only next to the
  position's name, muted, with a title saying it is the code in the source annex. The regime
  toggles on the payslip read the law's name ("Legea-cadru 153/2017") with the file id secondary.

Test: `simulators/salarizare/app/tests/layout.test.tsx`.
### UX-16 impozit-teren page check — done

- Given `/impozit-teren/#j=bc` at 390 × 844, when the county table has rendered, then the
  document does not scroll sideways (`scrollWidth <= clientWidth + 1`), axe-core (wcag2a,
  wcag2aa, wcag21aa) reports no serious or critical issue, and the page raises no JS error.
  Same contract as the administrativ, transport, justitie and salarizare page checks
  (ux guideline § 9 item 9; design criteria 1 and 8).

Test: impozit-teren `tests/browser/page-checks.spec.ts`.


### UX-18 Status badge on the map simulators — done

- Given `/administrativ/`, `/transport/` and `/impozit-teren/`, then the data line under the H1
  ends with exactly one `.badge.status` reading „Date reale” (EN „Live data” in administrativ,
  whose chrome is translated); the badge is a sibling span, so the script that fills the data
  line never overwrites it (design criterion 4; ux-guidelines § 9 item 7). The other five pages
  carry theirs from #169, #176 and #179.
- The status word is the agent's reading of the sources (real registries and statistics, not
  fixtures): needs the owner's confirmation per simulator.

Tests: administrativ `tests/data-line.test.ts`, transport and impozit-teren `src/shell.test.ts`
(order and exactly one badge).

### UX-17 Companii-stat light-first on civic-ui roles — done

- Given `simulators/companii-stat/app/src/style.css`, then the unconditional `:root` block
  carries the civic-ui `neutral` light values (`--bg: #f4f6f6`, `--fg: #182b2c`, `--muted:
  #475d60`, `--card: #ffffff`, `--link: #006b60`) and `color-scheme: light`; the dark values
  appear only under `@media (prefers-color-scheme: dark)` (ux-guidelines § 6, § 9.1; design
  criterion 2). The national tier tag takes a `--danger` role in both themes instead of two
  hard-coded reds.

Test: `simulators/companii-stat/app/src/theme.test.ts`.

### UX-6 Maps and readability — done (Romanian UI strings: needs human review)

- Given courts that share a courthouse (the appellate court, tribunal and judecătorie of a
  county seat; four in București), then each gets its own circle: the largest stays at the
  courthouse and the others step onto a ring about 3 km across, ordered by volume. A
  presentation offset, not a relocation.
- Given the administrative map, then the legend explains the unit colours ("Fiecare unitate
  propusă are culoarea ei; comunele poartă culoarea centrului lor", EN too) with the palette as
  one striped swatch, and it is no longer hidden on phones. The summary bar on phones wraps
  instead of scrolling, so "8,73 mld RON" is not clipped off its edge.
- Given the transport map, then "Se încarcă harta…" sits over the map until the data lands,
  and on a load failure it turns into the error title beside the panel's full message.
- Given impozit-teren on a wide screen, then the sidebar column is painted to the bottom of
  the page (no black gap under the sticky sidebar). On a phone the order is title and
  controls, then figures, map and table, then "Ce nu putem calcula" and the sources.
- Given companii-stat on a phone, then the clusters table scrolls sideways inside its region
  with the activity name pinned, so every numeric column is reachable.

Tests: justitie `src/spread.test.ts`; administrativ `tests/legend-mobile.test.ts`; transport
`src/map-status.test.ts`; impozit-teren `src/layout.test.ts`; companii-stat
`src/table-mobile.test.ts`. The CSS tests read the stylesheet; the layouts themselves were not
screenshot-checked on a phone: needs human review.
## F. Family UX guideline (uxg-b, 2026-10-14)

### UXG-1 One guideline for the landing and the seven simulators

- Given `docs/ux-guidelines.md`, then it fixes one visual style for the family (light by
  default, following the reader's system setting for dark; dark map canvases allowed), lists
  each simulator's permitted deviation, and covers page anatomy, content, data-viz, states,
  mobile and accessibility rules, status vocabulary, a conformance checklist and a backlog of
  known deviations.
- Given any simulator in `site/shell.mjs`, then the guideline names its path.
- Given a test the conformance checklist cites, then that test file exists.
- Romanian wording in the guideline is agent-written: needs human review.

Test: `tests/test_ux_guidelines.py`.
### UX-9 Static pages light-first on civic-ui roles — done

- Given `site/index.html`, `site/en/index.html`, `site/brief.html` and `site/privacy.html`,
  then the unconditional `:root` block carries the civic-ui `neutral` light values
  (`--bg: #f4f6f6`, `--fg: #182b2c`, `--muted: #475d60`, `--card: #ffffff`,
  `--link: #006b60`) and `color-scheme: light`; the dark values appear only under
  `@media (prefers-color-scheme: dark)` (ux-guidelines § 6 and § 9.1; design screen 01).

Test: `tests/test_site_pages.py::test_static_pages_are_light_first_on_civic_ui_roles`.
### UX-10 Static pages lead with the family bar — done

- Given the four static pages, then the shared `rr-nav` is the first element in `<body>`,
  before the `h1`, its first link goes to the hub, and the page restyles it as a header
  (border below, 24 px link targets) instead of the shell's footer rule (ux-guidelines § 2;
  design screens 01 and 05, acceptance criterion 1).

Test: `tests/test_site_pages.py::test_static_pages_lead_with_the_family_bar`.
### UX-11 Every landing card names its own data — done

- Given the seven simulator cards on `site/index.html` and `site/en/index.html`, then each
  carries a `card-data` line "Date: <sursă>, <an>" (en "Data: …") whose source and year are
  the ones the H1 data line already states for that simulator; nothing new is asserted
  (design screen 01; ux-guidelines § 2.3).

Test: `tests/test_site_pages.py::test_every_simulator_card_names_its_own_data`.
### UX-8 Target-state design screens — docs only (Romanian copy: needs human review)

- Given `docs/design/screens/01..05*.html`, then each is a self-contained static page (no
  external requests, no scripts) with a desktop and a 390 px layout, built on the civic-ui
  `neutral` token values, with a family bar, `h1`, purpose line and `Date: <sursă>, <an>`
  line, a status badge from the vocabulary in `docs/ux-guidelines.md` § 7, and comma-below
  diacritics only.
- Given `docs/design/README.md`, then every screen maps to a user task, guideline sections,
  the change versus today and acceptance criteria 1–10 that later items turn into tests.
- No PNG screenshots in this round (no local browser runs allowed); a follow-up adds them.

Test: none yet (documentation); `tests/test_site_pages.py::test_romanian_text_uses_comma_below`
is the model for a future check over `docs/design/screens/*.html`.
