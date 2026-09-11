# Native Civic UI Pilot

This app remains vanilla TypeScript and MapLibre. Its native controls consume
the published Civic UI v0.4.0 CSS-only archive without introducing React or
changing the simulator's identity.

## Scope

- County and GDP-year selectors: scoped Field/Select styles, associated labels,
  native browser arrows and 44px minimum height.
- Pagination: native buttons using shared focus, hover and disabled styles.
- Results: named, keyboard-focusable shared scroll region with explicit column
  scopes. Table typography, numeric alignment, county groups and data stay local.
- Existing host colors are mapped to Civic UI tokens. No party theme is imported.

Sliders, rate entry, segmented scenario/sort controls, map, tooltips, calculations,
datasets and URL codec are not migrated. The inspected app has no search field;
the earlier portfolio inventory's search reference was not an implementation target.

The narrow native HTML contract supplies select appearance and padding through
`native.css` and `civic-select--native`. The earlier equivalent local rules were
removed; theme, font, color-scheme and layout overrides remain host-owned.

## Distribution

`src/vendor/civic-ui/` contains only published CSS, native contract documentation and the MIT license, copied
verbatim from the pinned public GitHub release. `provenance.json` records archive
and individual-file SHA-256 hashes. There is no React, Radix or Lucide runtime
dependency, no npm publication requirement and no browser CDN request.

- `npm run check:civic-css`: verify local vendored bytes without network access.
- `npm run update:civic-css`: download the pinned archive, verify its checksum,
  and regenerate the eight allowlisted archive files. Requires Node with fetch and tar.

The [v0.4.0 release](https://github.com/CristianNichifor/civic-ui/releases/tag/v0.4.0)
is public. Published bytes are retained for verification.

Do not manually edit vendored CSS. Make host overrides in `src/native-ui-pilot.css`.
A version change requires reviewing the upstream markup contract, updating the
pinned URL/checksum and rerunning the browser suite.

## Verification

Use Node 22.12+ and the existing release-data prerequisites described by `copy-data.mjs`.

```sh
npm ci
npm test
npm run build
xvfb-run -a npm run check:ui
```

The browser suite uses Playwright 1.63.0 in Chromium, Firefox and WebKit. CI uses
the matching `mcr.microsoft.com/playwright:v1.63.0-noble` image with Docker `--init`,
Xvfb and `LIBGL_ALWAYS_SOFTWARE=1`. Firefox runs headed because the image's headless
Firefox refuses WebGL2; the same pixel test passes with this setup. This follows
[Playwright's headed Linux CI guidance](https://playwright.dev/docs/ci#running-headed).
Tests cover county,
year, national pagination, reload and sort-reset workflows; 320/390/1440px layouts;
native labels/focus, table keyboard scrolling, scoped axe checks, map pixel content
and zoom interaction. Browser output goes to `/tmp/land-tax-ui-results`.

For an explicit before/after comparison with the same data, build the unmodified
app and run with `LAND_UI_CAPTURE=1 LAND_UI_BASELINE=/tmp/land-tax-before`. Rebuild
the pilot and rerun with only `LAND_UI_BASELINE=/tmp/land-tax-before`. Seven
rendered-data/URL snapshots per engine must match exactly. Historical snapshots
are local artifacts, not committed financial fixtures; regular CI exercises the
workflows without claiming comparison against historical data.

Tests block requests outside the local preview origin. This verifies a locally
served build does not need the internet for these workflows, not that a cold
GitHub Pages visit works offline. No service worker or caching feature is added.
Automated checks are not a full accessibility or physical screen-reader audit.

The follow-up toolchain upgrade pins Vite 7.3.6, matching the salary app, and
replaces the affected Vite 5/esbuild dependency chain. The app keeps its explicit
`es2022` build target and module-worker configuration. It does not use the removed
Sass, SSR or plugin APIs described in the
[Vite 6](https://v6.vite.dev/guide/migration) and
[Vite 7](https://v7.vite.dev/guide/migration.html) migration guides.
Run `npm audit` alongside build/browser checks when updating the lockfile;
an audit result describes the advisories known at that time, not a security certification.
