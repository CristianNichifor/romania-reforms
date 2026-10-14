# Contributing

Open changes against `dev`. Describe the issue, acceptance criteria, affected simulator
and observable result before implementation; include exact checks and evidence in the PR.
Keep model changes separate from source refreshes so reviewers can distinguish a changed
assumption from changed observations. Agents never merge PRs or deploy.

## Public setup

Install Git, Python 3.12+, uv and Node 22.12+ (CI uses Node 22). Docker is needed for the
pinned Playwright browser environment. No private handbook, 1Password or credentials are
needed to read sources, install dependencies or run PR checks.

```sh
git clone https://github.com/CristianNichifor/romania-reforms.git romania-reforms-work
cd romania-reforms-work
git fetch origin dev
git switch -c chore/my-change origin/dev
uv sync --all-groups
uv run python scripts/fetch_release_data.py \
  --require local-finance-mart-2023-2025 \
  --require salarizare-ro-draft-2026-07-16 \
  --require public-enterprise-administrative-footprint-2024-2026 \
  --require transport-road-speeds
```

Maintainers with `wt` instead run `wt new chore/my-change origin/dev` from their existing
repo; it creates `<repo>/.worktrees/chore/my-change`. Never reuse a dirty checkout or base
work on local ahead commits. The separate clone above is the equivalent for outsiders.
Release assets are public, checksum-pinned inputs, not permission to refresh source data.

## Verification map

Run commands from the stated directory. The workflows are the authoritative full step
order; do not omit model or browser checks just because the change is in shared code.

| Scope / directory | Local checks | CI owner |
|---|---|---|
| Shared schemas, packages, importers / root | `uv run python scripts/check_repo_size.py`; `uv run python scripts/validate_data.py`; `uv run --with geopandas python -m pytest tests/ -q -m "not full_data" --junitxml=/tmp/shared.xml`; `python3 scripts/check_test_report.py /tmp/shared.xml` | `shared` (also rebuilds justice baselines and byte-diffs them) |
| Salary / `simulators/salarizare` | `uv run --with jsonschema python scripts/validate_data.py`; `uv run --with openpyxl --with pytest --with jsonschema pytest tests/ -q`; `npm ci && npm run typecheck && npm test` | `salarizare` (also rebuilds the pinned July regime and checks its hash) |
| Salary app / `simulators/salarizare/app` | `npm ci --ignore-scripts && npm run build`; pinned-container `npm run check:ui` | `salarizare` |
| Justice / root then `simulators/justitie/app` | `uv run python simulators/justitie/scripts/locate_instante.py --year 2025`; in app: `npm ci --ignore-scripts && npm run build && npm test`; pinned-container `npm run check:ui -- --reporter=list` | `justitie`, reusable `justice-browser` |
| Administration / `simulators/administrativ` | `uv sync --all-groups`; `uv run ruff check pipeline tests`; `uv run ruff format --check pipeline tests`; `PYTHONHASHSEED=0 uv run pytest -q -m "not full_data"` | `administrativ` (bounded fixture; national parity remains in web tests) |
| Administration web / `simulators/administrativ/web` | `npm ci && npm run lint && npm run typecheck && npm test && npm run build`; pinned-container `npm run check:ui -- --reporter=list` | `administrativ`, reusable `native-consumers` |
| Transport / `simulators/transport` | `uv sync --all-groups`; `uv run ruff check scripts tests`; `uv run ruff format --check scripts tests`; `PYTHONHASHSEED=0 uv run pytest -q` | `transport` |
| Transport app / `simulators/transport/app` | `npm ci && npm run build`; pinned-container `npm run check:ui -- --reporter=list` | `transport`, reusable `native-consumers` |
| Land tax / `simulators/impozit-teren/app` | `npm ci && npm run typecheck && npm test && npm run build`; pinned-container `npm run check:ui -- --reporter=list` | `impozit-teren` (pinned rebuilds from committed parsed sources; live-source checks separate) |
| Deconcentration / root then its `app` | `uvx ruff check simulators/deconcentrare`; `uvx ruff format --check simulators/deconcentrare`; in app: `npm ci && npm run build` | `deconcentrare` |
| State companies / root then its `app` | `uvx ruff check simulators/companii-stat`; `uvx ruff format --check simulators/companii-stat`; in app: `npm ci && npm run build` | `companii-stat` |
| Civic UI vendoring / root | `python3 scripts/verify_civic_ui_provenance.py` plus every consuming app's browser checks | reusable `native-consumers` provenance + browser matrix |
| Portal workflow / root (offline) | `uv run python -m pytest tests/test_portal_snapshot_workflow.py tests/test_merge_coverage.py -q` | `shared`; scheduled collector remains separate |

For each Python suite, add `--junitxml=/tmp/<suite>.xml`, then run the root
`scripts/check_test_report.py` on that report. It rejects missing, empty, failed and skipped
evidence. A pytest exit of zero with skips does not establish readiness.

Browser jobs use `mcr.microsoft.com/playwright:v1.63.0-noble`. Copy the exact Docker command
and mounts from `ci.yml`, `justice-browser.yml` or `native-consumers.yml`; these preserve
screenshots and reports. Missing expected browser artifacts fail the job.

## Bounded PR verification versus full-data certification

`verify` covers every CI correctness job, including both reusable browser workflows and
all provenance/browser matrix jobs. Failures, cancellations, skipped tests and missing
reports/artifacts cannot pass. Two explicit `full_data` scopes are outside this bounded
PR gate; CI lists their collected test names in the job summaries, not as passing skips:

- Administration's **50 national assertions** remain in `test_reference_model.py`. The
  PR suite adds an eight-UAT, two-county synthetic fixture that writes all six loader
  inputs, calls the real loader and model, and checks complete/unique assignment,
  connectivity, county boundaries, savings, determinism and each missing-input failure.
  The browser suite still checks the tracked national Python/TypeScript parity cases.
  Neither check certifies a rebuild of the national source pipeline.
- The **one real-source land-price assertion** requires overlapping ANCPI sales and
  transfer-tax years. Bounded fixtures exercise the same arithmetic and verify rejection
  of missing years and factor-of-100 errors. Other committed-data assertions still run.
  The real-source assertion fails, rather than skips, until the sources overlap.

The separate **Full national data verification** workflow (`full-data.yml`, manual only)
executes these original assertions and rejects missing/failed evidence. It performs no
collection or publication. Run the same checks locally after provisioning trusted inputs:

```sh
# At repository root: actual source-year coverage, not synthetic fixtures.
uv run python -m pytest tests/ -m full_data -q --junitxml=/tmp/full-source.xml
python3 scripts/check_test_report.py /tmp/full-source.xml
# In simulators/administrativ: actual national processed artifacts.
PYTHONHASHSEED=0 uv run pytest tests/ -m full_data -q --junitxml=/tmp/full-national.xml
python3 ../../scripts/check_test_report.py /tmp/full-national.xml
```

Running without a marker selection also includes these full-data assertions and fails
when their inputs are absent. No default configuration silently excludes them.

### Precise outstanding full-data prerequisites

As inspected on 2026-10-01, the trusted repository's `data-v1` release has 11 assets and
**none** supplies administration's `data/processed/uat_geometry.gpkg`, `uat_seats.gpkg`,
`adjacency.parquet`, `road_distance.parquet`, `candidacy.parquet`, or `finance.parquet`.
`pipeline.reference_model.load_data` needs all six. Build them using the documented
pipeline and its trusted source vintages, or have a maintainer publish a checksum-pinned
bundle and add its fetch to `full-data.yml`. This PR does not collect those sources,
substitute browser binaries for original geometry, or borrow another checkout's data.
Full-data CI is deliberately blocked until that public provisioning path exists.

The tracked transfer-tax file describes 2025; ANCPI sales observations do not include
that year. The full-data source check reports `no ANCPI counts for 2025`. A reviewed
source refresh with overlapping years is required before claiming national price
plausibility. Do not shift the year or fabricate counts to satisfy the assertion.

Transport's three speed-layer assertions need the existing checksum-pinned
`transport-road-speeds` release asset. CI now fetches it as required before the pipeline
tests; local setup above does the same. This is a fixable setup dependency, not a
full-data exemption. Public PR checks require no credentials.

### Land rebuild and publication boundary

The land job no longer re-queries INS for every PR or downloads all notarial PDFs. It
still runs the cached asking-price/agricultural/Fiscal-Code parsers, rebuilds all 42
counties' values, yields, taxes, rents and national estimate, byte-compares tracked
baselines, and runs app model and browser checks. Its exact local command is:

```sh
simulators/impozit-teren/scripts/rebuild.sh --pinned --committed-built-yield
git diff --exit-code simulators/impozit-teren/data/
```

The explicit `--committed-built-yield` profile takes the tracked built-land yield as an
input. Re-extracting its four notarial PDF caches remains in full-source verification;
those caches are absent from a clean checkout and the public release manifest. Existing
root tests still check the committed yield's identity, bounds and limitations. Pinned
rebuilds now pin **both** land value and tax conversions to their own recorded exchange
rates, and fail if a required baseline is absent instead of contacting the ECB.

`land-source-verification.yml` preserves the former live INS/notary/ECB source comparisons
and the national geometry build as a separate manual check. Unreachable INS is an error
there, not a warning converted into a successful empty diff; missing national geometry
also fails. It is **required before publication of related land-data or pipeline changes**,
just as `full-data.yml` is required before related national-model/source publication.
A green bounded `verify` is not permission to publish those data. Do not dispatch live
source verification as an onboarding test. Agents never publish or deploy.

The 2026-10-01 PR run remained in `The land areas are reproducible` for over 20 minutes
before reaching any derived check. Separating this network-dependent source assertion
lets contributors verify source code without claiming an unavailable source was checked.

### Portal bootstrap diagnosis

Read-only probes of the official WSDL on 2026-10-01 reproduced HTTP 403 with Python's
default user agent and HTTP 200 with all 246 court enum values when the existing honest
`romania-reforms` SOAP client identity was supplied. HTTPS returned 525, and the WSDL
advertised the HTTP address. `load_courts()` now uses that same identified request;
an offline regression test reproduces the rejected anonymous request. Only the WSDL was
read; no case collection or publication was performed. Scheduled collection still needs
the stable maintainer hash salt, upstream availability and complete shard evidence.

## Data and review evidence

Preserve tracked justice and land-tax regression baselines. Keep large derived data in
checksum-pinned releases listed by `data-assets.json`, respecting `.gitignore` and the size
policy. Do not publish new assets during a normal contribution. Keep source provenance,
confidence, limitations, SIRUTA joins and browser/Python parity visible in the diff.

PR evidence should identify commands, pass/fail/skip counts, browser artifacts for UI changes,
byte/hash comparisons for data changes, and any unverified acceptance criteria. Link related
issues and explain changed assumptions. Live portal collection requires the maintainer's stable
hash salt and deliberately runs only on schedule/manual dispatch; never invoke it as a PR test.
