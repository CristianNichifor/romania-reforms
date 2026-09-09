# Shared Salary UI

The salary app uses Civic UI v0.2.0 for compatible fields, checkboxes, command buttons and all nine existing data-table declarations. The app retains its neutral light/dark tokens through the app-level `civic-scope civic-pay` boundary and `src/civic-pilot.css`. Shared CSS is loaded once in `main.tsx`. No USR theme, logo or font is imported.

## Adoption

- Field, Input and NativeSelect: comparison reference, merge filters, home search, payslip search/variant and envelope justification. Home search and justification now have visible labels; the native position listbox has its own accessible name.
- Checkbox: merge-only filter, proposal patches, occupation options, cap scope/measure, payslip supplement claims and regime selection. Existing disabled claims and the final-regime guard are preserved.
- Button: proposal bulk actions, load-more and scenario-copy commands.
- Table: comparison, distribution, structure, occupation composition, cap, merge cards and payslip views. Existing cells, totals, order and numeric alignment remain; each table gains a named keyboard-focusable horizontal scroll region. Old nested overflow wrappers are removed.
- Mobile grid minima now fit narrow claim, payslip and merge-card containers. Supplement qualifiers use the existing secondary text token for contrast.

## Intentional Local Components

- Native range inputs retain domain bounds, steps, live values and URL handlers. Civic UI v0.2.0 has no range-slider contract.
- The payslip `select size={8}` remains a native listbox. NativeSelect's dropdown arrow, fixed height and padding are unsuitable for a visible multi-row picker.
- App navigation, home result/navigation cards and descriptive next-view cards remain local composed route controls. They are not tab panels or generic command buttons.
- Occupation/domain sector filters remain the existing compact selection-button groups. Civic UI has no segmented-control API; replacing them with RadioGroup or Tabs would alter their semantics and keyboard contract.
- Charts, meters, disclosure sections, glossary tooltips and domain-specific status annotations remain local. No generic replacement is needed merely to remove native HTML.

No sorting or pagination is added to read-only tables. The existing merge load-more behavior is retained. Other Romania Reforms simulators are outside this salary-app migration.

The dependency is pinned to the public [Civic UI v0.2.0 GitHub release](https://github.com/CristianNichifor/civic-ui/releases/tag/v0.2.0). No npm account or machine-local tarball is required. The lockfile records the HTTPS artifact and its integrity. Release tarball SHA-256: `9a78cb63fd9885febc5aa94eefbb3647f7dd5841fda5e7a6b2e78192b3d0c802`. React and React DOM remain on version 18; v0.2.0 adds Radix runtime dependencies, but this migration introduces no dialogs or menus.

## Verify

After fetching the repository's declared release datasets:

```bash
npm ci --ignore-scripts
npm run build
npx --no-install playwright install chromium firefox webkit
npm run check:ui
```

The browser checks start and stop loopback preview servers in Chromium, Firefox and WebKit, covering 320/390/1440 widths in light/dark modes, scoped axe accessibility, keyboard focus, select padding, six anchor/seniority combinations, seven merge-filter scenarios and 25 consolidated control/data scenarios. They check offline interactions and reject page errors/external requests. Screenshots/results go to fresh system temporary directories. See [UI_CHECKS.md](UI_CHECKS.md) for commands and historical baseline options. CI does not require a private local baseline.

The separate engine suite remains the calculation regression gate. No engine, dataset, scenario codec, chart or slider behavior changes. This is not a full-page accessibility/security audit: unchanged proposal descriptions and weak badges retain existing light-mode muted-text contrast failures, independently reproduced on deployed main. Axe checks cover migrated choice and field surfaces, not all editorial text. Offline installation still requires cached dependencies and datasets; browser operation requires a reachable local server.

The subsequent tooling-maintenance change pins Vite 7.3.6 and Vitest 4.1.11 for both app and engine tests. On 2026-09-09, clean installs and npm audits reported zero known vulnerabilities in these two packages' dependency trees. This is not a security audit of the wider repository. Browser previews still bind only to loopback.
