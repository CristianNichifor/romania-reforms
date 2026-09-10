# Native Civic UI adoption

Transport stays a vanilla TypeScript app. No React runtime, model, map paint, data,
scenario encoding or network dependency is introduced by this styling change.

## Published dependency

`src/vendor/civic-ui` contains the unmodified CSS and MIT license extracted from
the public Civic UI v0.2.0 release. `provenance.json` records the release URL,
archive SHA-256 and file hashes. `npm run check:civic-css` verifies local bytes
without network access; `node scripts/vendor-civic-css.mjs --update` downloads
and verifies that exact release. The source is committed so normal installs,
builds and the running application need no GitHub connection.

The separate native CSS contract/release is not published yet. `native-ui.css`
therefore keeps an explicit interim `civic-select--native` adapter, restoring
the browser arrow and padding. It does not claim to consume an unreleased asset.
Host palette tokens remain transport's own; no USR theme is imported.

## Scope and exceptions

- Service-level selector: native select within `civic-field`, existing label.
- Seven optional map layer checkboxes: native inputs within `civic-choice`.
- Cost table: named, keyboard-focusable `civic-table-scroll` wrapper. Numeric
  column alignment and compact table styles remain native, not `civic-table`.
- Timetable segmented buttons, links, MapLibre controls, map paint and legends
  intentionally retain domain-specific markup and behavior.

## Verification

`npm test` runs model tests. `npm run build` checks TypeScript, model tests,
bundles the application and verifies the emitted map worker.
`npm run check:ui` verifies vendored bytes then runs Chromium, Firefox and WebKit.
The Linux Playwright image needs `xvfb-run -a` for Firefox's WebGL2 context.

Browser checks cover every service level, both timetable scenarios, URL reload,
native keyboard focus, layer toggling, semantic table headers and scrolling,
targeted axe checks, 320/390/1440px screenshots and real map canvas pixels/zoom.
External HTTP requests are blocked and asserted absent in responsive checks.
This means local assets work without external services, not a service-worker
offline-install guarantee. Optional road release files may be absent; existing
disabled-toggle handling is preserved.

Before migration, all three browsers captured unchanged output. To repeat a
comparison, set `NATIVE_UI_BASELINE=/tmp/native-baseline` and
`NATIVE_UI_CAPTURE=1` on the domain-output test at the baseline revision, then
run the changed revision with only `NATIVE_UI_BASELINE` set. Baselines are local,
not committed data copies. CI continuously runs behavior and layout checks.
This targeted suite is not whole-app accessibility certification.

## Development toolchain

Use Node 22.12 or newer (CI uses Node 22). Vite is pinned to 7.3.6, matching the
land-tax app; the existing explicit ES2022 build target remains unchanged.
The upgrade removes the Vite 5/esbuild advisories without changing runtime
dependencies: all 23 non-development lock entries remain identical.
`npm audit` reported zero findings for this lockfile on 2026-09-10; this is a
point-in-time result, not a future security guarantee. No audit suppression or
forced dependency override is used.

The [Vite 6](https://v6.vite.dev/guide/migration) and
[Vite 7](https://v7.vite.dev/guide/migration) migration guidance was checked.
The app uses no removed Sass API or custom plugin hooks. Browser comparisons
retain all 18 pre-upgrade domain states across the three engines, alongside
the existing offline map/worker and native-control checks.
