# romania-reforms

Simulators for Romanian public-policy reforms. Deterministic, explainable, browser-only.
Instruments for public debate, not calculators of entitlement.

## Commands and verification

Use Python 3.12+, uv and Node 22.12+; there is no root npm workspace.
See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and the per-domain verification map.

- `uv sync --all-groups`
- `uv run python scripts/check_repo_size.py`
- `uv run python scripts/validate_data.py` (fetch required release assets first)
- `uv run --with geopandas python -m pytest tests/ -q --junitxml=/tmp/reforms-tests.xml`
- `python3 scripts/check_test_report.py /tmp/reforms-tests.xml`
- `python3 scripts/verify_civic_ui_provenance.py`

This is a pytest suite: unittest discovery is not a substitute. Missing artifacts and
skipped tests are incomplete verification, even when pytest returns zero.

## Delivery boundaries

- Branch from fetched `origin/dev` with `feat/`, `fix/`, `chore/`, `docs/`, `sec/`, or
  `adr/`; open a PR back to `dev`. **Agents must never merge any PR or deploy**, including
  with administrator credentials. GitHub restrictions do not enforce agent intent.
- Maintainers use `wt new <branch> origin/dev` at the repository root; worktrees belong
  at `<repo>/.worktrees/<branch>`. Preserve dirty/ahead checkouts. Contributors without
  `wt` can use a separate standard clone (see CONTRIBUTING).
- CI's aggregate status is `verify`: all simulator, shared, provenance and browser jobs
  must succeed. The separate scheduled portal collector and Pages deployment are not
  PR correctness gates. Remote required-check settings are managed separately.
- `main` is production; its Pages workflow publishes the site. Do not trigger deployment,
  releases or collection as part of development verification.

## Working rules

- Conventional Commits: imperative lower-case subject, no trailing full stop, at most
  72 characters; one coherent change per commit. Body explains why; diff shows what.
- Never modify vendored third-party sources. Fix the environment or update through the
  documented vendoring process with provenance evidence.
- Every figure needs source and locator; preserve provenance confidence and limitations.
- Preserve tracked baseline data, especially `simulators/{justitie,impozit-teren}/data`:
  CI rebuilds and byte-diffs it. Do not move it to releases to satisfy size checks.
  Large generated payloads follow `data-assets.json` and `.gitignore`; never commit
  portal parquet, raw personal data, build output or downloaded caches.
- Public setup and tests require no private handbook, 1Password or secrets. Maintainer
  publishing credentials may use `op run` / `op://`; never store or print credentials.
- Verify before claiming completion; report failed/skipped checks and missing inputs.
  A merge is not a deployment, and a tag is not a publication.
