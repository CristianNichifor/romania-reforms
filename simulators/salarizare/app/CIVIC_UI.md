# Shared Control Pilot

The comparison-reference field on `#/echivalente` uses Civic UI's Field and NativeSelect. Search/family filters on `#/functii` use Field, Input and NativeSelect; the merged-only filter uses Checkbox. The app retains its existing neutral light/dark tokens through narrow `civic-scope civic-pay` boundaries and `src/civic-pilot.css`. No USR theme, logo or font is imported.

The dependency is pinned to the public [Civic UI v0.2.0 GitHub release](https://github.com/CristianNichifor/civic-ui/releases/tag/v0.2.0). No npm account or machine-local tarball is required. The lockfile records the HTTPS artifact and its integrity. Release tarball SHA-256: `9a78cb63fd9885febc5aa94eefbb3647f7dd5841fda5e7a6b2e78192b3d0c802`. React and React DOM remain on version 18; v0.2.0 adds Radix runtime dependencies, but this migration introduces no dialogs or menus.

## Verify

After fetching the repository's declared release datasets:

```bash
npm ci --ignore-scripts
npm run build
npx --no-install playwright install chromium firefox webkit
npm run check:ui
```

The browser checks start and stop loopback preview servers in Chromium, Firefox and WebKit, covering 320/390/1440 widths in light/dark modes, scoped axe accessibility, keyboard focus, select padding, six anchor/seniority combinations and seven merge-filter scenarios. They check offline interactions and reject page errors/external requests. Screenshots/results go to fresh system temporary directories. See [UI_CHECKS.md](UI_CHECKS.md) for commands and historical baseline options. CI does not require a private local baseline.

The separate engine suite remains the calculation regression gate. No engine, tracked dataset, scenario codec, charts or slider behavior is changed by this pilot. This is not a full UI migration or accessibility/security audit. Offline installation still requires cached dependencies and datasets; browser operation requires a reachable local server.

The subsequent tooling-maintenance change pins Vite 7.3.6 and Vitest 4.1.11 for both app and engine tests. On 2026-09-09, clean installs and npm audits reported zero known vulnerabilities in these two packages' dependency trees. This is not a security audit of the wider repository. Browser previews still bind only to loopback.
