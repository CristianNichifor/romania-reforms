# Shared data roadmap

This is the execution plan for the first shared datasets that should move out of
simulator-local code and into a shared data layer.

## 1. SIRUTA, UAT and CUI registry

Make this the first shared import. Every other dataset joins on it.

Source of truth:

- INS SIRUTA 2026 from `data.gov.ro`
- Transparenta.eu UAT CUI/natcode crosswalk as a comparison source, not a silent authority

First slice:

- done: import current SIRUTA
- done: import Transparenta UAT crosswalk
- done: write a mismatch report for duplicate, missing and ambiguous CUIs
- done: import official UAT population from the committed POP107D county extracts
- done: point the `impozit-teren` land-value map builder at the shared registry for
  SIRUTA, county and sector-parent joins
- next: move remaining simulator-local SIRUTA assumptions to this registry as each
  shared dataset adopts it

## 2. Local finance mart

Use Transparenta.eu budget execution as the primary integration path, because this repo
already has a working importer in `simulators/impozit-teren/scripts/import_buget_uat.py`.
Do not treat Transparenta repository licenses as licenses for the underlying financial
data; each imported snapshot still needs its own source, query, retrieval time and checksum.

First slice:

- done: extract ten UATs for 2023-2025
- done: preserve the GraphQL query and report-type/account-category filters
- done: compare 2024 national Transparenta totals against the available `data.gov.ro`
  workbook and keep the scope mismatch as a warning
- done: publish classification assumptions for own revenue, transfers, personnel and capital
  spending
- done: generate the full 2025 national mart and prove the existing `buget-uat-2025`
  output can be regenerated through the shared package without changing published totals
- done: inspect the official `data.gov.ro` Arierate package, add a compact UAT resource index,
  and add importer hooks for the legacy UAT XLS workbooks; the official package only covers
  2013-09-30 through 2018-06-30, so it cannot populate the 2025 mart
- done: publish the full 2023-2025 national mart as a release asset so the full history is
  downloadable without pushing the tracked tree past the repository size gate
- next: wire the local-finance mart into a first consuming simulator view, starting with the
  indicators that are already proven by the mart and validation report

Useful first indicators:

- revenue and spending per inhabitant
- own revenue share
- personnel spending share
- capital/development spending share
- arrears per inhabitant
- EU/PNRR/funding-source dependence

## 3. Health access mart

Build this after the registry exists, because matching provider location to UAT is the main
risk.

Source of truth:

- Ministry of Health hospital unit and bed workbooks on `data.gov.ro`
- ANMCS accreditation workbooks on `data.gov.ro`

First slice:

- one validation county plus Bucharest
- provider identity, beds, specialty, owner type and accreditation
- explicit location confidence for each provider
- named exclusions for unmatched providers

This should support service-access views in `administrativ`, `justitie` and `transport`
without each simulator building its own hospital roster.

## Guardrails

- Keep raw large workbooks and geocoded/routing outputs out of git.
- Store source URL, retrieval date, checksum and transform version with every derived file.
- Treat unmatched joins as named limitations, not dropped rows.
- Prefer official source files for citation and Transparenta code/schema for integration
  design unless Transparenta publishes an explicit data export license for a snapshot.
