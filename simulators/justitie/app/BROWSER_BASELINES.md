# Justice Browser Baselines

These checks exercise the built, separate statistics and MapLibre entry points.
They do not migrate controls, change datasets or refactor the judicial or
administrative models. The fixture inputs are committed public aggregates and
court/boundary data. A single synthetic national case total distinguishes the
authoritative national document from an accidental sum of court records. No case
records, identities, credentials, private services or external map tiles are used.

## Run

From the repository root, run the existing prerequisite:

```sh
uv run python simulators/justitie/scripts/locate_instante.py --year 2025
```

From `simulators/justitie/app`:

```sh
npm ci --ignore-scripts
npm run build
npm test
```

Build first: the existing arondare unit tests consume the copied `public/data`
payloads prepared by the build scripts. The `Justice browser baselines` workflow
then runs `npm run check:ui` in the
existing Playwright `v1.63.0-noble` container, using software graphics and Xvfb
for Firefox WebGL. All three engines run with one worker, no retries, a 90-second
per-test timeout and a 15-minute CI job budget. Evidence goes to
`/tmp/justitie-browser-baselines` and is retained as a CI artifact for seven days.

## Coverage

- National totals, county and court-tier cohort sums, individual-court disabled
  tier, returning to national scope and national-only section notices.
- Filter `loc`/`grad` reload and same-document hash changes, preserved unrelated
  scenario keys and `replaceState` history behavior.
- On-demand proposal loading, disabled loading button, controlled matrix-load
  failure, retry, direct proposed-court reload and cached offline scope changes.
- Full rendered statistics/chart attributes recorded as JSON evidence; identical
  views compared over reload/offline round trips. These are runtime comparisons,
  not a frozen snapshot that blesses changed public datasets automatically.
- Statistics keyboard selection and labels, chart text invariance, screenshots
  and page overflow at 320/390/1440px in both system color modes.
- Real WebGL pixels, map mode controls, zoom/pan, staffing/ceiling changes, lazy
  commune outlines, missing optional roads and native reader focus/close behavior.
- Map screenshots and exposed-canvas pixel probes at 320/390px; map remains dark
  as designed, independent of statistics system theme.
- External HTTP(S) requests blocked and reported; browser page errors fail tests.
  Local uncached resources are allowed until explicitly switching offline.

## Known Boundaries

The inherited fixed sidebar covers approximately 92% of a 320px mobile viewport.
The mobile checks prove controls fit and the narrow exposed map is not blank;
they do **not** prove useful mobile map framing. A dedicated responsive map/panel
design is still needed before claiming mobile map usability.

This baseline does not certify accessibility, screen readers, real devices or
all chart contrast. It does not cover every court/commune hover detail, successful
optional roads geometry, every manual administrative pin, or cold offline reload
with missing lazy resources. The reader's native containment, Escape and explicit
close are tested; all disclosure contents are not individually audited.

The current Vite/esbuild advisories and MapLibre bundle-size warning predate these
tests. Build-tool upgrades remain separate from the baseline changes.
