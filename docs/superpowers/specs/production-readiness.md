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

### RR-10 English for the salary simulator — todo

- Given the salary app, when the reader picks English, then the views render in English,
  following administrativ's i18n pattern. Translations: needs human review.

Test: vitest in `simulators/salarizare/app`.
