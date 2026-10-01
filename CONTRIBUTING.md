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
  --require public-enterprise-administrative-footprint-2024-2026
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
| Shared schemas, packages, importers / root | `uv run python scripts/check_repo_size.py`; `uv run python scripts/validate_data.py`; `uv run --with geopandas python -m pytest tests/ -q --junitxml=/tmp/shared.xml`; `python3 scripts/check_test_report.py /tmp/shared.xml` | `shared` (also rebuilds justice baselines and byte-diffs them) |
| Salary / `simulators/salarizare` | `uv run --with jsonschema python scripts/validate_data.py`; `uv run --with openpyxl --with pytest --with jsonschema pytest tests/ -q`; `npm ci && npm run typecheck && npm test` | `salarizare` (also rebuilds the pinned July regime and checks its hash) |
| Salary app / `simulators/salarizare/app` | `npm ci --ignore-scripts && npm run build`; pinned-container `npm run check:ui` | `salarizare` |
| Justice / root then `simulators/justitie/app` | `uv run python simulators/justitie/scripts/locate_instante.py --year 2025`; in app: `npm ci --ignore-scripts && npm run build && npm test`; pinned-container `npm run check:ui -- --reporter=list` | `justitie`, reusable `justice-browser` |
| Administration / `simulators/administrativ` | `uv sync --all-groups`; `uv run ruff check pipeline tests`; `uv run ruff format --check pipeline tests`; `PYTHONHASHSEED=0 uv run pytest -q` | `administrativ` |
| Administration web / `simulators/administrativ/web` | `npm ci && npm run lint && npm run typecheck && npm test && npm run build`; pinned-container `npm run check:ui -- --reporter=list` | `administrativ`, reusable `native-consumers` |
| Transport / `simulators/transport` | `uv sync --all-groups`; `uv run ruff check scripts tests`; `uv run ruff format --check scripts tests`; `PYTHONHASHSEED=0 uv run pytest -q` | `transport` |
| Transport app / `simulators/transport/app` | `npm ci && npm run build`; pinned-container `npm run check:ui -- --reporter=list` | `transport`, reusable `native-consumers` |
| Land tax / `simulators/impozit-teren/app` | `npm ci && npm run typecheck && npm test && npm run build`; pinned-container `npm run check:ui -- --reporter=list` | `impozit-teren` (full importer/rebuild order in `ci.yml`) |
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

## Missing inputs are blockers

The administration reference suite needs `data/processed/{uat_geometry.gpkg,uat_seats.gpkg,
adjacency.parquet,candidacy.parquet,finance.parquet}` and any further inputs its model reads.
These are not provided by the existing release manifest. Building them requires the documented
administration pipeline; do not invent fixtures or remove national-data assertions to get green.
Transport also has tests requiring generated routing/traffic/access data; its road-time rebuild
needs administration's graph and the large OSM source. Consult those simulators' READMEs and
report the exact missing files from test evidence. The land-sales plausibility test also
needs overlapping ANCPI sales and transfer-tax years; the current sources do not overlap,
so that assertion remains unverified and the evidence guard reports it. Existing browser parity fixtures do not
substitute for the national Python reference tests.

The `verify` aggregate depends on every CI correctness job, including both reusable browser
workflows and their matrix/provenance jobs. Failures, cancellations and skipped jobs cannot
pass. Existing missing-data skips now block the corresponding Python job: provisioning those
inputs is a prerequisite for enabling a passing required gate, not a reason to waive it.
Public PRs need no secrets. Public asset/source availability can still fail network-backed
checks; disclose it rather than asserting the affected data was verified.

## Data and review evidence

Preserve tracked justice and land-tax regression baselines. Keep large derived data in
checksum-pinned releases listed by `data-assets.json`, respecting `.gitignore` and the size
policy. Do not publish new assets during a normal contribution. Keep source provenance,
confidence, limitations, SIRUTA joins and browser/Python parity visible in the diff.

PR evidence should identify commands, pass/fail/skip counts, browser artifacts for UI changes,
byte/hash comparisons for data changes, and any unverified acceptance criteria. Link related
issues and explain changed assumptions. Live portal collection requires the maintainer's stable
hash salt and deliberately runs only on schedule/manual dispatch; never invoke it as a PR test.
