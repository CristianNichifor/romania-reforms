# Shared Salary UI

The salary app uses Civic UI v0.5.0 for compatible fields, checkboxes, command buttons and all nine existing data-table declarations. The app retains its neutral light/dark tokens through the app-level `civic-scope civic-pay` boundary and `src/civic-pilot.css`. Shared CSS is loaded once in `main.tsx`. No USR theme, logo or font is imported.

## Adoption

- Field, Input and NativeSelect: comparison reference, merge filters, home search, payslip search/variant and envelope justification. Home search and justification now have visible labels; the native position listbox has its own accessible name.
- Checkbox: merge-only filter, proposal patches, occupation options, cap scope/measure, payslip supplement claims and regime selection. Existing disabled claims and the final-regime guard are preserved.
- Button: proposal bulk actions, load-more and scenario-copy commands.
- Table: comparison, distribution, structure, occupation composition, cap, merge cards and payslip views. Existing cells, totals, order and numeric alignment remain; each table gains a named keyboard-focusable horizontal scroll region. Old nested overflow wrappers are removed.
- Mobile grid minima now fit narrow claim, payslip and merge-card containers. Supplement qualifiers use the existing secondary text token for contrast.

## Intentional Local Components

- Native range inputs retain domain bounds, steps, live values and URL handlers. Civic UI v0.5.0 has no range-slider contract.
- The payslip `select size={8}` remains a native listbox. NativeSelect's dropdown arrow, fixed height and padding are unsuitable for a visible multi-row picker.
- App navigation, home result/navigation cards and descriptive next-view cards remain local composed route controls. They are not tab panels or generic command buttons.
- Occupation/domain sector filters remain the existing compact selection-button groups. Civic UI has no segmented-control API; replacing them with RadioGroup or Tabs would alter their semantics and keyboard contract.
- Charts, meters, disclosure sections, glossary tooltips and domain-specific status annotations remain local. No generic replacement is needed merely to remove native HTML.

No sorting or pagination is added to read-only tables. The existing merge load-more behavior is retained. Other Romania Reforms simulators are outside this salary-app migration.

The dependency is pinned to the public [Civic UI v0.5.0 GitHub release](https://github.com/CristianNichifor/civic-ui/releases/tag/v0.5.0). No npm account or machine-local tarball is required. The lockfile records the HTTPS artifact and its integrity. React and React DOM remain on version 18; v0.5.0 retains the existing runtime dependencies, and this migration introduces no dialogs or menus.

## Verify

After fetching the repository's declared release datasets:

```bash
npm ci --ignore-scripts
npm run build
npx --no-install playwright install chromium firefox webkit
npm run check:ui
```

The browser checks start and stop loopback preview servers in Chromium, Firefox and WebKit, covering 320/390/1440 widths in light/dark modes, scoped axe accessibility, keyboard focus, select padding, six anchor/seniority combinations, seven merge-filter scenarios and 25 consolidated control/data scenarios. They check offline interactions and reject page errors/external requests. Screenshots/results go to fresh system temporary directories. See [UI_CHECKS.md](UI_CHECKS.md) for commands and historical baseline options. CI does not require a private local baseline.

The separate engine suite remains the calculation regression gate. No engine, dataset, scenario codec, chart or slider behavior changes. Proposal descriptions, disclosure summaries and weak badges use the existing secondary text token; switched-off cards retain readable text instead of whole-card opacity. Their unchecked controls, explicit state labels and struck headings still identify the off state. Axe checks cover full proposal cards (enabled and off/expanded), migrated choice/field surfaces, and table semantics. This is not a full-page accessibility/security audit. Offline installation still requires cached dependencies and datasets; browser operation requires a reachable local server.

The browser runner also checks the reviewed v0.5.0 artifact URL, version and integrity in the manifest/lockfile. Intentional dependency upgrades must update that guard after reviewing the new release. Browser snapshots reject shared inputs/selects missing scoped Field composition or a label.

The subsequent tooling-maintenance change pins Vite 7.3.6 and Vitest 4.1.11 for both app and engine tests. On 2026-09-09, clean installs and npm audits reported zero known vulnerabilities in these two packages' dependency trees. This is not a security audit of the wider repository. Browser previews still bind only to loopback.
