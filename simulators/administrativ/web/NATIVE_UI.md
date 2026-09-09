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

Known pre-existing detail-field limitation: after a pin becomes the locality's
assigned region, `pinTargets` excludes that region from the offered options.
The native select can therefore show its blank/default option even while the
URL and manual-override list retain the pin. The regression checks verify that
stored state and reset; this migration does not change target-selection rules.
Reproduced in Chromium on unchanged `aab98ca`: open `#lang=en&sel=1`, choose the
first nonblank target (230), and reload. The URL retains `pin=1.230` and the
manual-override list still has UAT 1, but `#pin-select` has value `""`.

## Development toolchain

Use Node 22.12 or newer (CI uses Node 22). Vite is pinned to 7.3.6 and Vitest to
4.1.11, already used in sibling simulators. The lint-only js-yaml transitive
dependency is updated within its existing allowed range. All 23 runtime lock
entries remain structurally identical, including MapLibre and its transitives.
The existing explicit ES2022 build target and worker format are unchanged.

The [Vitest 3](https://v3.vitest.dev/guide/migration) and
[Vitest 4](https://v4.vitest.dev/guide/migration) migration guidance was checked.
The model suite uses no mocks, fake timers, custom pools, workspace APIs or
coverage provider. Node environment, globals, 120-second test timeout and the
separate Playwright exclusion stay unchanged. The existing 150ms performance
assertion is not relaxed. Model/parity assertions remain unchanged; the three
browsers compare all 15 captured pre-upgrade domain states.

`npm audit` reported zero findings for this lockfile on 2026-09-10, down from
six development-tool findings. This is a point-in-time result. No audit
suppression, dependency override or legacy-peer resolution flag is used.
The updated lock was resolved with CI-image npm 11 after npm 10's peer-graph
resolver crashed; clean `npm ci` with local Node 22/npm 10 then passed.
