# Pay Browser Checks

Run from this app directory after installing its locked dependencies:

```bash
npm run build
npx --no-install playwright install chromium firefox webkit
npm run check:ui
```

The runner starts and stops a Vite preview for each engine: Chromium, Firefox,
then WebKit. It checks `#/echivalente` and `#/functii`, not every simulator screen.

- Six layouts per engine: 320/390/1440 pixels in light and dark modes.
- Select padding, keyboard focus order and visible focus; scoped axe checks on
  the shared field, not a full-page accessibility audit.
- Six scenarios: three comparison anchors at zero and 35 years. Firefox and
  WebKit must match Chromium's rendered values, benchmarks and route exactly.
- In-page offline selection, no external HTTP requests and no page errors.
- Seven merge-filter scenarios: initial, search, combined family, merged-only,
  reload, empty and reset. Assertions verify nonempty reduced results, family
  metadata, merged badges, persisted controls and restored results.
- Merge filters also check six layouts per engine, the longest family option,
  control bounds, select padding, keyboard checkbox activation, visible checkbox
  focus and scoped axe results including the shared checkbox. Layout
  assertions and screenshots cover the filter row, not the entire cards page.

Cross-engine agreement is not independent validation of the salary calculations.
The engine suite remains separate. `CIVIC_BASELINE=/path/to/results.json` compares
all engines against a caller-supplied historical result instead of Chromium.
For merge filters, use `CIVIC_MERGES_BASELINE=/path/to/results.json`; without it,
Firefox and WebKit compare against Chromium. Merge comparisons retain card order,
all displayed text/amounts and URL hashes, normalizing only rendered whitespace
because engines insert different tabs and newlines around table cells.
Screenshots and JSON reports go to a fresh `/tmp/pay-civic-ui-*` directory per
engine and are retained as CI artifacts for seven days.

For one engine, use `CIVIC_BROWSER=firefox node scripts/check-civic-ui.mjs`.
Use `scripts/check-merge-filters.mjs` instead for merge filters. On a pre-migration
build, `CIVIC_STAGE=before` captures its behavior with the legacy select locator
and skips checks that require Civic UI controls; this mode is not used in CI.
`DEMO_CHROMIUM=/path/to/chromium` overrides only Chromium's executable;
`DEMO_PORT` overrides the default preview port 5200. Build before running checks.
Local execution needs compatible browser system libraries. CI uses the official
`mcr.microsoft.com/playwright:v1.63.0-noble` image; keep its version aligned with
the app's locked Playwright version.

WebKit coverage is not Safari/iOS device certification. Offline checks do not
promise reloads with the local server stopped. Tests do not modify source data,
calculation logic, branding or the installed Civic UI release.
