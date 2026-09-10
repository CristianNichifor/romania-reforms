# Health access point locations — evolution and implementation plan

> **Executed, PR71–PR91.** All five slices shipped, including the consumer adoption in slice 5:
> `justitie` (PR76) and `transport` (PR75, PR79) both read point access. What follows is the plan
> as it was written on 2026-09-09, kept because the parts the code cannot state are here — the
> evidence ladder, and above all the non-goals. The rule that a coordinate is never inferred from
> a county name, and that Bucharest providers get no sector without address evidence, is enforced
> by the validation gates but argued for only in this document.
>
> Where reality diverged: the accepted-point set and the still-blocked providers ended up carried
> in explicit maintenance queues rather than only as named exclusions (PR87–PR91), which is a
> stronger version of the same commitment.

**Status after PR70:** `justitie`, `administrativ` and `transport` all consume the shared
UAT-level health service-access view. The next useful slice is not another consumer. It is
better provider location evidence: street addresses and, where defensible, coordinates.

## Current State

The shared health stack now has three layers:

1. `packages/health_access/data/health-access-mart-2024-2025.json`
   - 592 ANMCS provider records.
   - 68 providers with matched Ministry clinical-bed rows.
   - 324 providers with a SIRUTA and `serviceAccessEligible: true`.
   - 268 providers blocked from service-access because their source evidence is county-only.
   - Bucharest providers are placed at municipality level, not sector level.

2. `packages/health_access/data/health-service-access-uat-2024-2026.json`
   - 3,181 municipality/town/commune rows.
   - 181 UATs with at least one eligible local provider.
   - 324 eligible providers included.
   - 268 blocked providers preserved as named exclusions.
   - 6 Bucharest sector rows excluded.

3. Consumer payloads
   - `justitie` uses the shared view for court/police/health distance comparison.
   - `administrativ` aligns the shared view to its web UAT order for merged-unit local counts.
   - `transport` adds shared health local counts to `data/access.json` and map hover payloads.

This is enough for co-location claims: "this UAT has an eligible provider." It is not enough
for actual facility access: "this settlement is X minutes from the nearest eligible provider."

## Target Outcome

Produce a provider-point health access layer that lets consumers route to actual provider
locations when point evidence exists, while keeping the current UAT-level view as the safe
fallback.

The target should answer:

- Which providers have a verified address?
- Which providers have usable coordinates?
- Which coordinates are official, parsed from source text, geocoded, or manually resolved?
- Which providers still lack point evidence and must remain excluded from point routing?
- How far is each UAT seat from the nearest eligible provider point?
- How much do point-level results differ from the current same-UAT co-location view?

## Non-Goals

- Do not infer coordinates from a county name.
- Do not assign Bucharest providers to sectors unless the provider evidence names a sector or
  address that can be resolved to one.
- Do not replace the UAT-level service-access view; keep it stable for existing consumers.
- Do not commit large raw workbooks, geocoder caches, routing matrices or OSM-derived payloads.
- Do not use a provider point in routing unless its evidence and confidence are explicit.

## Data Model Evolution

Add a provider-point layer beside the existing mart, not inside every consumer.

New committed artefact, if small enough:

```text
packages/health_access/data/health-provider-points-2024-2026.json
packages/health_access/schema/health-provider-points.schema.json
packages/health_access/scripts/build_health_provider_points.py
```

Potential release assets if they become large:

```text
health-provider-point-geocode-cache-2024-2026.*
health-provider-point-routing-2024-2026.*
```

Suggested provider point fields:

```json
{
  "providerId": "anmcs-2025-001",
  "name": "SPITALUL ...",
  "countyCode": "B",
  "siruta": "179132",
  "serviceAccessEligible": true,
  "address": "street address or null",
  "addressEvidence": {
    "method": "official-provider-address | source-workbook-address | osm-name-match | manual-review | none",
    "source": "source id",
    "sourceValue": "verbatim value used",
    "retrievedDate": "YYYY-MM-DD"
  },
  "latitude": 44.437,
  "longitude": 26.102,
  "pointConfidence": "official-coordinate | address-geocoded | osm-name-address-match | manual-coordinate | none",
  "pointEvidence": {
    "method": "published-coordinate | geocoded-address | osm-feature-match | manual-review | none",
    "source": "source id",
    "sourceValue": "verbatim value used"
  },
  "pointAccessEligible": true,
  "pointAccessBlockedReason": null
}
```

Keep `serviceAccessEligible` and `pointAccessEligible` separate. A provider can be safe for
UAT-level co-location but unsafe for point routing, and vice versa after better address
evidence is found.

## Evidence Ladder

Use the first defensible evidence available, in this order:

1. Official coordinates published by a public authority.
2. Official street address published by a public authority, then geocoded with cache and review.
3. Provider-published address, when the provider identity is unambiguous.
4. OSM feature match, when name, address/locality and county agree.
5. Manual review row with recorded source URL and reviewer note.
6. No point. Keep the provider named and blocked from point routing.

Any automated geocoding must be reproducible enough to audit:

- Store query string, source address, provider id, returned address, returned coordinates,
  provider/county/SIRUTA match result and retrieval date.
- Do not silently update coordinates when a geocoder changes its answer.
- Keep geocoder cache out of git if it is large; publish it as a release asset if needed.

## Implementation Slices

### Slice 1 — Source Reconnaissance And Schema

Goal: define the point-evidence contract before importing anything.

Files:

- Add `packages/health_access/schema/health-provider-points.schema.json`.
- Add `packages/health_access/scripts/build_health_provider_points.py` with an empty/no-point
  implementation that reads the existing mart and writes blocked point rows.
- Add tests in `tests/test_health_provider_points.py`.
- Update `data-catalog.json` and `docs/data-roadmap.md`.

Behaviour:

- Every mart provider appears exactly once in the point file.
- All 592 providers initially carry `pointAccessEligible: false` unless the first slice includes
  a verified source.
- Existing `serviceAccessEligible` values are copied through unchanged.
- The schema requires explicit evidence objects, even when the method is `none`.

Acceptance:

- Schema validation passes.
- Tests prove no provider is dropped.
- Tests prove point routing cannot use rows with `pointAccessEligible: false`.

### Slice 2 — Address Source Import

Goal: attach verified street-address evidence where a source exists.

Files:

- Extend `build_health_provider_points.py`.
- Add a source manifest under `packages/health_access/sources/` only for small metadata files.
- Keep bulky source downloads out of git.

Behaviour:

- Import address fields as evidence, not as coordinates.
- Match source rows to mart providers by stable keys first. If no stable key exists, match by
  normalised name + county + locality and record the method.
- Ambiguous matches are exclusions, not guesses.
- Bucharest rows stay municipality-level until the address itself resolves lower.

Acceptance:

- Every address-bearing provider has `addressEvidence.method != "none"`.
- Every ambiguous candidate is named in `exclusions`.
- A committed test pins a few known hard matches and non-matches.

### Slice 3 — Coordinate Resolution

Goal: convert address evidence into point evidence under an auditable rule.

Files:

- Add a geocode/cache reader module under `packages/health_access/scripts/`.
- Add optional `--refresh-geocode` path only when network use is explicitly intended.
- Add a small fixture cache for tests, not the national cache if it is large.

Behaviour:

- Coordinates from official sources are accepted directly.
- Geocoded coordinates must pass county and UAT consistency checks.
- OSM/provider-name matches must require name similarity plus locality/county agreement.
- Coordinates outside the provider's UAT polygon are blocked unless manually reviewed.
- Providers with only county-level evidence remain blocked.

Acceptance:

- Tests reject coordinates outside Romania and outside the expected UAT.
- Tests reject duplicate point matches for different providers unless explicitly allowed.
- Tests prove geocoder changes do not rewrite committed point rows without updating evidence.

### Slice 4 — Point-Level Access View

Goal: build a UAT-to-nearest-provider access view that consumers can adopt.

Files:

- Add `packages/health_access/data/health-service-access-point-2024-2026.json`.
- Add `packages/health_access/schema/health-service-access-point.schema.json`.
- Add `packages/health_access/scripts/build_health_service_point_access.py`.

Behaviour:

- Inputs are provider points, UAT registry and an explicit routing substrate.
- Start with straight-line distance only if road routing is not yet available, and label it as
  straight-line.
- Prefer the same road graph used by `justitie`/`transport` once the point-to-road snapping
  contract exists.
- Publish per-UAT:
  - nearest provider id/name
  - provider county/SIRUTA
  - metres or minutes
  - distance method
  - candidate provider count
  - whether the result is exact, upper bound, or unavailable

Acceptance:

- Point access uses only `pointAccessEligible: true` rows.
- Summary reports eligible point providers and blocked point providers.
- County-only providers remain named exclusions.
- A test proves UAT-level co-location counts do not get mistaken for point distances.

### Slice 5 — Consumer Adoption

Goal: adopt point access where it changes the product, without breaking existing UAT-level
health counts.

Order:

1. `justitie`
   - Replace "hospitalMetresAtMost" source with the point-access view where available.
   - Keep the upper-bound language if unresolved provider points mean the nearest real provider
     could be closer.
   - Continue publishing local provider counts from the UAT-level view.

2. `transport`
   - Add nearest eligible provider distance/time to hover or sidebar.
   - Keep current local count in hover; it answers a different question.
   - Use the transport road-time model only after point-to-road snapping is implemented.

3. `administrativ`
   - Keep merged-unit local counts from the UAT-level payload.
   - Add point access only if the detail panel needs nearest-provider distance for merged units.

Acceptance:

- Existing UAT-level health tests remain.
- New point-level tests prove each consumer states method and limitations.
- No consumer computes point routing from provider county-only rows.

## Validation Gates

Add or extend tests for these invariants:

- Provider identity
  - Every `providerId` from the mart appears exactly once in provider points.
  - No point row exists for a provider absent from the mart.

- Evidence
  - `pointAccessEligible` requires non-null latitude/longitude and non-`none` point evidence.
  - Rows with `locationConfidence: county-only` cannot become point eligible without explicit
    address/coordinate evidence.
  - Bucharest providers do not receive a sector unless address evidence supports it.

- Geography
  - Coordinates must be inside Romania.
  - Coordinates should be inside the provider UAT polygon, or carry a manual exception.
  - County and SIRUTA agreement are checked against `packages/uat_registry`.

- Consumers
  - `justitie`, `administrativ` and `transport` still consume the shared UAT view.
  - Point-distance consumers use only the point-access view.
  - Summary totals reconcile to provider-level eligibility counts.

Recommended commands for each PR:

```bash
uv run --with referencing python scripts/validate_data.py
uv run --with referencing python -m pytest tests/ -q
cd simulators/transport && uv run pytest -q
cd simulators/transport/app && npm run build
cd simulators/justitie/app && npm run build && npm test
cd simulators/administrativ && uv run pytest -q
cd simulators/administrativ/web && npm run lint && npm run typecheck && npm test
python3 scripts/check_repo_size.py
git diff --check
```

## PR Sequence

Keep the work in small reviewable PRs:

1. Provider-point schema and empty blocked-point builder.
2. First address source import with evidence and exclusions.
3. Coordinate/geocode cache support and point eligibility gates.
4. Point-level service-access view.
5. `justitie` point-distance adoption.
6. `transport` point-distance adoption.
7. Optional `administrativ` point-distance adoption if useful in the merged-unit panel.

## Main Risks

- **False precision.** A coordinate that came from a weak name match looks authoritative on a
  map. Mitigation: separate address evidence, point evidence and point eligibility.

- **Bucharest over-assignment.** Current sources place 87 providers at the municipality. Sector
  assignment must wait for address evidence.

- **Licensing and source drift.** Repository code licenses do not license underlying datasets.
  Every imported source needs its own source URL, retrieval date, checksum and licence note.

- **Repository size.** National geocoder caches and routing outputs may exceed the size budget.
  Keep generated bulk data as release assets.

- **Consumer confusion.** UAT local-provider counts and nearest-provider distance are different
  facts. Keep both named separately in schemas and UI copy.

## Definition Of Done

This project is finished when:

- The shared health package publishes both UAT-level and point-level service-access views.
- Point-level views route only to providers with explicit point evidence.
- Providers still lacking point evidence remain named exclusions.
- `justitie` and `transport` can report nearest-provider access from the shared point view.
- Existing UAT-level consumers continue to report local provider counts without local rosters.
- The data catalog clearly states what remains unresolved and why.
