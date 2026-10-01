# Simulator boundaries

These instructions cover every simulator; root AGENTS.md also applies. See CONTRIBUTING.md
for exact commands and CI owners. Each simulator has its own dependency environment.

- Sources describe proposals and observations; models remain deterministic and browser-only.
  Keep assumptions, units, date windows, exclusions and uncertainty visible beside results.
- `scripts/` or `pipeline/` produce datasets; `schema/` defines contracts. App copy/prebuild
  scripts produce browser payloads: change the source/builder, not copied `public/` output.
  Preserve intentionally tracked web fixtures and justice/land-tax byte-diff baselines.
- Salary: distinguish regimes, crosswalks, base coefficients and fiscal assumptions; retain
  engine tests and reproducible pinned-regime checks. A scenario is not pay entitlement.
- Administration: preserve canonical UAT ordering, connectivity, deterministic tie-breaking
  and Python/TypeScript parity. Missing national pipeline artifacts are a blocked test,
  not evidence of equivalence. PR CI selects bounded fixtures with `-m "not full_data"`;
  the original national assertions remain fail-closed under `-m full_data`.
- Transport: positional joins must match administration's UATs; preserve route, speed,
  access and cost caveats. Do not replace absent routing artifacts with plausible defaults.
- Land tax: follow the existing CI/rebuild dependency order. Pin the exchange rate for
  byte comparisons; separate grid value, asking price, yield and tax assumptions. The
  bounded rebuild uses `--pinned --committed-built-yield`; live source comparisons and
  notarial yield extraction remain required in `land-source-verification.yml` before
  related publication. Never describe the committed-yield input as freshly extracted.
- Deconcentration and state companies: retain source-specific institution/perimeter and
  staffing/cost definitions, plus provenance and limitations in shared sidecars.
- Shared Civic UI sources are vendored: never edit them in place. Verify their pinned
  provenance and browser behavior across every consumer, using the pinned container.
- Run the relevant Python/model/app/browser checks from the contributor map. Preserve
  screenshots outside tracked data; report missing inputs and skipped assertions explicitly.
