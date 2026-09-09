# Native Civic UI adoption

Administration remains a vanilla TypeScript/MapLibre app with its existing
neutral palette. Models, data, URL format, saved versions, translations, map
paint and worker implementation are unchanged.

## Dependency and offline use

`src/vendor/civic-ui` is unmodified CSS plus the MIT license from the published
v0.2.0 GitHub release. `provenance.json` records release URL, archive SHA-256 and
file hashes. `npm run check:civic-css` verifies those local files offline.
`node scripts/vendor-civic-css.mjs --update` fetches only that exact release and
verifies its archive before extracting selected files. Builds and the UI do not
fetch styles remotely or require React/npm publishing credentials.

The native CSS-only release is not published. `native-ui.css` documents the
interim native-select arrow/padding adapter and maps existing host colors to
Civic tokens rather than importing a party theme.

## Adopted controls

- Six layer toggles retain native checkbox behavior inside `civic-choice`.
- Candidate search/county controls use `civic-field` wrappers and their existing
  translated accessible names. The selected-locality pin selector keeps its
  visible translated label.
- Methodology, reset, copy-link, save-version, detail force and dialog-close
  commands use `civic-button` alongside their existing handlers.
- Sliders, language/view/hover segmented groups, panel drag/resize, MapLibre
  controls, compact link actions, candidate row actions, native dialogs and
  disclosures intentionally retain their domain-specific implementation.
  There are no native table elements in this app to migrate.

## Checks

`npm run lint`, `npm test`, and `npm run build` cover source, model/persistence
tests and TypeScript/build. `npm run check:ui` verifies vendor provenance then
runs three browsers. The CI Playwright image runs Firefox under Xvfb for WebGL2.

Browser tests cover lazy candidate filters; RO/EN text; saving, opening and
deleting a version across reload; selected-locality pin URL persistence;
native keyboard controls; targeted axe checks; mobile sheet opening; and
320/390/1440px screenshots with map pixel/zoom checks. Responsive tests block
and reject external HTTP requests. This tests serving bundled local assets,
not installation as a service-worker offline application.

All three browsers captured pre-migration domain snapshots. For comparison,
capture the domain-output test on the baseline revision with
`NATIVE_UI_BASELINE=/tmp/native-baseline NATIVE_UI_CAPTURE=1`, then run the new
revision with `NATIVE_UI_BASELINE` alone. Timing text is excluded from summaries;
model values, filter counts, options and hashes are retained. Historical
snapshots are local artifacts; CI reruns the independent behavior assertions.
The scoped tests are not whole-app accessibility certification.

Existing Vite/esbuild and legacy Vitest development-tool advisories remain a
separate upgrade task. No audit rules are disabled by this adoption.
