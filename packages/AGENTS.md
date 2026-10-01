# Shared data packages

These instructions cover `packages/`; root AGENTS.md also applies.

- `provenance/schema` defines the shared vocabulary: `source`, `locator`, confidence
  (`verbatim`, `derived`, `assumed`) and limitations with affected outputs. Keep references
  resolvable offline; never upgrade confidence merely because a calculation is deterministic.
- `uat_registry` owns canonical SIRUTA identities. Finance, health access and enterprise
  governance must join through those identities, preserving mismatch reports instead of
  silently dropping unknown rows or joining by display name.
- Keep finance vintages, geographic coverage, health-provider coordinate evidence and
  enterprise perimeter/compensation assumptions distinct. A point or aggregate is not
  evidence of service capacity or entitlement.
- Edit importers/schemas and regenerate deliberately; do not hand-patch a derived mart.
  Compact tracked samples/reports remain reviewable; full marts and review extracts follow
  `data-assets.json` and `.gitignore`. Do not move CI baselines out of git.
- Run root schema validation and pytest after fetching the required pinned public assets;
  run the JUnit evidence guard and size/provenance checks in CONTRIBUTING.md. Exercise all
  consuming simulator jobs for a shared contract change; one app build is insufficient.
