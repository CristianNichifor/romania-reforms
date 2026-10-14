# Justice simulator and portal collector

Root and simulator instructions apply. Court registries, arondare, workload, staffing,
pay and costs describe different source vintages; do not join across them by display name
or silently treat missing coverage as zero workload. Keep limitations with affected outputs.

- `data/` contains intentional tracked reproducibility baselines. Change importers/builders
  and review regenerated diffs, preserving original user changes in other worktrees.
- Locate courts before building `app/`; run model and three-browser checks. Shared root
  tests cover importers, schemas, coverage merging and publication reporting offline.
- Portal snapshots are survival samples, not historical censuses. Preserve window metadata,
  failed/truncated windows, missing shard identities and strict mixed-window rejection.
- Never commit parquet or raw personal data. Public collection requires a stable secret
  `PORTAL_HASH_SALT` and `--no-summaries`; no free-text disposition summaries may ship.
- Partial output is worth retaining, but incomplete collection must remain failed. No output
  must prevent publication before existing release assets can be changed. Do not manufacture
  empty successful coverage or fall back to another date/window.
- Scheduled collection and release publication are operational work, separate from PR
  verification. Do not trigger either to test a fix. Replay reporting with offline fixtures.
