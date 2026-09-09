# Shared Control Pilot

Only the comparison-reference field on `#/echivalente` uses Civic UI's Field and NativeSelect. The app retains its existing neutral light/dark tokens through `src/civic-pilot.css`. No USR theme, logo or font is imported.

The dependency is pinned to the public [Civic UI v0.1.0 GitHub release](https://github.com/CristianNichifor/civic-ui/releases/tag/v0.1.0). No npm account or machine-local tarball is required. The lockfile records the HTTPS artifact and its integrity. Release tarball SHA-256: `67aa86d0c6672917e25efdfe777b4827eef71847e6b11834be2c9d1cbe0b598f`.

## Verify

After fetching the repository's declared release datasets:

```bash
npm ci --ignore-scripts
npm run build
npx --no-install playwright install chromium
npm run check:ui
```

The browser check starts and stops a loopback preview server, tests 390/1440 widths in light/dark modes, field-scoped axe accessibility, keyboard focus, select padding, six anchor/seniority combinations, no external requests or page errors, and offline in-memory recalculation. Screenshots/results go to a fresh system temporary directory. `DEMO_PORT` selects another port; `DEMO_CHROMIUM` can point to an installed Chromium. `CIVIC_BASELINE` optionally names a previously captured results JSON for exact scenario/URL comparison; CI does not require a private local baseline.

The separate engine suite remains the calculation regression gate. No engine, tracked dataset, scenario codec, charts or slider behavior is changed by this pilot. This is not a full UI migration or accessibility/security audit. Offline installation still requires cached dependencies and datasets; browser operation requires a reachable local server.

The subsequent tooling-maintenance change pins Vite 7.3.6 and Vitest 4.1.11 for both app and engine tests. On 2026-09-09, clean installs and npm audits reported zero known vulnerabilities in these two packages' dependency trees. This is not a security audit of the wider repository. Browser previews still bind only to loopback.
