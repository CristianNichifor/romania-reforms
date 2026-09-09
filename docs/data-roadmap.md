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
- done: wire the local-finance mart into `administrativ` through a compact 2024 own-revenue
  payload, without replacing its simulator-specific administration-spending series
- done: move `impozit-teren`'s budget denominator onto the 2023-2025 shared mart/release
  asset so the app no longer carries a parallel finance artifact
- done: expose 2023-2025 spending growth and own-revenue-share movement from the shared
  mart in `administrativ`, with endpoint bases carried in the compact payload so merged
  units can recompute trends from summed values
- done: expose 2024 per-inhabitant revenue/spending and personnel-spending pressure in
  `administrativ`, recomputed from compact payload bases for merged units rather than
  averaged member ratios
- next: leave deeper local-finance dimensions deferred until a consuming simulator needs
  arrears, capital/development mix or funding-source dependence

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

- done: one validation county plus Bucharest
- done: provider identity, beds, specialty, owner type and accreditation
- done: explicit location confidence for each provider
- done: named exclusions for unmatched providers
- done: expand beyond the Cluj and Bucharest sample to the national ANMCS provider roster
  and all Ministry county bed totals
- done: attach per-provider location evidence and a service-access eligibility flag so
  county-only rows cannot be used as if they had a provider location
- done: build a UAT-level service-access view from eligible providers only, with named
  exclusions for county-only provider rows
- done: wire the shared UAT service-access view into `justitie`'s court/police/health access
  comparison
- done: wire the shared UAT service-access view into `administrativ`'s merged-unit detail
  panel as aligned local-provider counts
- done: wire the shared UAT service-access view into `transport` as local-provider counts on
  routed UAT rows
- done: add a provider-point evidence contract that carries every mart provider and blocks all
  rows from point routing until point evidence exists
- done: import the Ministry of Health `Unitati sanitare` map as a compact source extract and
  attach 174 exact name/county street-address matches without making any provider routeable
- done: retain Ministry map marker coordinates and accept 162 exact name/county,
  service-eligible, non-county-only provider points after source/provider county and Romania
  bounds checks; UAT polygon containment still needs SIRUTA-keyed geometry
- done: build `health-point-access-2024-2026` from pointAccessEligible providers only,
  with 162 accepted provider coordinates, 430 named exclusions and an explicit
  `distanceMethod: not-computed` contract for downstream consumers
- done: wire the point-level health access view into `transport` as nearest accepted provider
  straight-line distances from UAT centroids; the committed run computes 3,136 routed-row
  distances, with 18.7 km unweighted median and 13.5 km population-weighted median
- done: wire the point-level health access view into `justitie`'s court/police/health
  comparison, keeping UAT-level local-provider counts separate from nearest-provider distance
- done: add a shared point-to-road snapping/routing contract so point-level health distances
  can graduate from straight-line evidence to road-network distances without treating provider
  coordinates as graph nodes
- done: wire that shared road-proxy contract into `justitie` as the first consumer, while
  keeping straight-line point distance and UAT-level routed health distance separately named
- done: wire the shared road-proxy provider-point distances into `transport`, keeping the
  current straight-line point metric as a fallback/comparison rather than a routing claim;
  the committed run computes 3,136 routed-row road-proxy distances, with 28.7 km unweighted
  median and 19.6 km population-weighted median
- done: add 37 curated same-county Ministry source-record aliases for official names that do
  not exactly match the ANMCS provider names, raising the point layer to 199 accepted provider
  coordinates and 393 named exclusions without enabling generic fuzzy matching
- done: refresh `transport` and `justitie` from the larger point set; the transport road-proxy
  run now has 26.9 km unweighted median and 18.3 km population-weighted median
- done: build `health-provider-point-evidence-review-2024-2026` as a manual-review queue
  for the 125 service-eligible providers still blocked by `no-point-evidence`; it finds 4
  exact same-county Ministry rows without street-address evidence, 7 providers with unused
  same-county Ministry review candidates and 114 providers with no Ministry candidate
- done: adjudicate the high-signal street-backed candidates from the review report and add
  three curated source-record aliases for Timisoara railway hospital, Targu Lapus town
  hospital and Constantin Balaceanu Stolnici chronic/geriatrics hospital; the point layer now
  has 202 accepted provider coordinates and 390 named exclusions, and the remaining review
  queue has 122 providers: 4 exact/no-street rows, 4 locality-only Ministry overlaps and 114
  rows with no Ministry candidate; refreshed consumers report 26.7 km transport road-proxy
  median and 18.9 km justitie point-road median
- done: add a reviewed coordinate-only acceptance source for the four exact same-county Ministry
  rows that publish coordinates but no street-address evidence; the provider-point contract keeps
  `addressEvidence.method: none` while accepting source-record-pinned
  `reviewed-published-coordinate` evidence, raising the point layer to 206 accepted provider
  coordinates and lowering named exclusions to 386; refreshed consumers report 26.5 km transport
  road-proxy median and 18.0 km justitie point-road median
- done: add `health-provider-point-source-acquisition-2024-2026` as a non-evidence work queue
  for the remaining 118 no-point providers: 4 locality-only Ministry overlaps needing
  provider-specific corroboration, 13 public bed providers with no Ministry candidate, 45 other
  public no-candidate rows, and 56 private or unknown no-candidate rows
- done: execute the first source-acquisition batch through audited ANMCS CAPeSaRo dashboard rows,
  promoting 17 provider/sourceCode pairs with source-specific street address and coordinate
  evidence; the point layer now has 223 accepted provider coordinates and 369 named exclusions,
  and the remaining source-acquisition queue has 101 no-Ministry-candidate providers
- done: formalize CAPeSaRo as a release-asset-backed compact source extract plus a non-evidence
  candidate report instead of committing the raw dashboard feed; the report covers all 101
  remaining acquisition rows and finds 53 providers with same-county active street-address
  CAPeSaRo candidates, including 35 of the 45 public no-candidate providers
- done: run the final high-signal CAPeSaRo review batch, promoting 29 public exact-name
  provider/sourceCode pairs; the point layer now has 252 accepted provider coordinates and 340
  named exclusions, and the remaining source-acquisition queue has 72 no-point-evidence
  providers: 16 public rows and 56 private or unknown rows
- next: pause health-point expansion and switch active development back to a non-health target;
  when health resumes, the remaining 72-row queue is the maintenance backlog, with only medium
  or low public CAPeSaRo candidates left

This should support service-access views in `administrativ`, `justitie` and `transport`
without each simulator building its own hospital roster.

## Guardrails

- Keep raw large workbooks and geocoded/routing outputs out of git.
- Store source URL, retrieval date, checksum and transform version with every derived file.
- Treat unmatched joins as named limitations, not dropped rows.
- Prefer official source files for citation and Transparenta code/schema for integration
  design unless Transparenta publishes an explicit data export license for a snapshot.
