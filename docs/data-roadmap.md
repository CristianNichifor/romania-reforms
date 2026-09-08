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
- next: import official UAT population and move simulator-local SIRUTA assumptions to this registry

## 2. Local finance mart

Use Transparenta.eu budget execution as the primary integration path, because this repo
already has a working importer in `simulators/impozit-teren/scripts/import_buget_uat.py`.
Do not treat Transparenta repository licenses as licenses for the underlying financial
data; each imported snapshot still needs its own source, query, retrieval time and checksum.

First slice:

- extract ten UATs for 2023-2025
- preserve the GraphQL query and report-type/account-category filters
- compare totals against available `data.gov.ro` finance files
- publish classification assumptions for own revenue, transfers, personnel and capital
  spending
- prove the existing `buget-uat-2025` output can be regenerated through the shared mart

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
