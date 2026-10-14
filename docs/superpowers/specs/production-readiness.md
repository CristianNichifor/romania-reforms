# Production readiness

Status legend: todo · done · blocked · needs-human. Each item names the test that proves it.
Translations written for these items are marked **needs human review**.

## A. Old paths keep working

### RR-1 Renamed simulator paths redirect — todo

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

### RR-7 Portal snapshot retries 5xx — todo

- Given the portal answers HTTP 5xx (520 seen in runs 38130733364 and 37919050016),
  when the importer makes a request,
  then it retries with exponential backoff before the shard records a failure; a 4xx is not
  retried.

Test: `tests/test_portal_retry.py` (520 then 200 succeeds after one retry; persistent 520
raises after the configured attempts; 403 is not retried).

### RR-6 Salary app tests every view — todo

- Given `simulators/salarizare/app`, when `npm test` runs, then it fails if there are no
  tests (`--passWithNoTests` removed) and at least one test renders each of Payslip,
  Structure, Proposal and Merges.

Test: `simulators/salarizare/app/src/views/*.test.tsx`.

### RR-8 Land tax shows each county's source year — todo

- Given a county's notarial guide year, when the table renders, then the year is shown for
  that county, and the counties whose values are estimated carry an "estimat" badge.

Test: vitest in `simulators/impozit-teren/app/src`.

## C. Shared shell

### RR-3 Shared navigation — todo

- Given the landing page or any simulator, when it renders, then it has
  `<nav aria-label="Simulatoare">` linking the home page and all seven simulators.

Tests: a DOM test per simulator; `tests/test_built_site.py` over built `dist/*/index.html`.

### RR-5 Landing metadata and privacy — todo

- Given `site/index.html`, then it has a meta description, Open Graph tags and a canonical
  link on `projects.cristian-nichifor.com/romania-reforms/`, links `privacy.html`, and offers
  English.
- Given `site/privacy.html`, then it states, in Romanian and English, what the code shows: no
  cookies, no analytics, hosting on Cloudflare Pages, operator Cristian Nichifor, contact
  through the repository's GitHub issues. English text: needs human review.

Test: `tests/test_site_pages.py`.

### RR-9 Content Security Policy — todo

- Given every built page, then it carries a CSP `<meta http-equiv>`.

Test: `tests/test_built_site.py`.

## D. Locale

### RR-10 English for the salary simulator — todo

- Given the salary app, when the reader picks English, then the views render in English,
  following administrativ's i18n pattern. Translations: needs human review.

Test: vitest in `simulators/salarizare/app`.
