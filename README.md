# Romania Reforms

Simulators for Romanian public-policy reforms. Each one takes a published proposal, models
what it actually says, and lets the reader argue with it — deterministic, explainable,
running entirely in the browser.

> **Instruments for public debate, not calculators of entitlement.**
> They compute what a document says, not what anyone receives. No figure here is a right
> and no scenario is a recommendation.

## The rule the whole repository runs on

Every number carries the document and the article, page or cell it came from. Where the
data does not reach, the page says so instead of filling the gap with a plausible guess.
That is the only thing all the simulators have in common, and it is the thing worth
sharing.

`packages/provenance` holds that vocabulary — `provenance` with a confidence of
`verbatim | derived | assumed`, and `limitation` with a severity and the outputs it
affects. One definition, resolved by every simulator's schema, so a caveat means the same
thing in all of them.

## What gets shared, and what does not

**Shared:** the vocabulary above, and the clients for sources more than one simulator
needs — budget execution, INS Tempo, Eurostat, Danmarks Statistik, the SIRUTA registry.
A second copy of an importer is a second thing to drift.

**Not shared:** the engines. A pay engine and a court-consolidation engine have nothing in
common but the ethos, and forcing them into one abstraction would cost more than it saves.

**Not merged:** the URLs. Each simulator stays independently deployable and linkable,
because what makes these useful is that a scenario is a link you can paste into an
argument. This repository is an index, not a monolith.

## Simulators

| | | |
| --- | --- | --- |
| **justitie** | The judicial reform | in progress, no app yet |
| **salarizare** | Public-sector pay | migrated |
| **administrativ** | Consolidation of the 3 186 UATs | migrated |

Both live simulators now live here, with their history, on project paths under one Pages
site: `/romania-reforms/salarizare/` and `/romania-reforms/administrativ/`. Their old
repositories become one-page redirects that carry `location.hash` across, so a scenario
someone has already pasted into an argument still opens the scenario.

**The code moved; the abstraction has not.** They are three apps in one repository, not
three consumers of a shared UI package. `packages/provenance` is shared because a second
simulator genuinely needed the same vocabulary; there is no `packages/ui` because
`justitie` has no interface yet, and extracting one from a single real consumer is how
shared packages end up wrong. That extraction waits for `justitie` to need it.

### justitie

Models the reform paper's proposal to turn **176 judecătorii and 42 tribunale into 42
consolidated tribunale and 15 regional courts of appeal**, plus its chapters on judicial
pay, service pensions, and the comparison with Denmark.

The baseline is in. `simulators/justitie/scripts/import_instante.py` reads Annex 1 of the
CSM's *Raport privind starea justiției* — **241 courts**, with the cases each carried, the
cases it disposed of, and the caseload per post and per judge:

| | courts | cases | judges |
| --- | --- | --- | --- |
| Înalta Curte | 1 | 21 995 | 23 |
| Curți de apel | 15 | 205 720 | 314 |
| Tribunale | 50 | 678 688 | 728 |
| Judecătorii | 175 | 2 307 236 | 1 586 |

The report never prints judge counts, but it prints caseload *per judge* — so dividing
back recovers the divisor. That divisor is an average over the year rather than a headcount
on a date, which is why it is almost never a whole number, and why it is marked `derived`
and good for comparing courts rather than for citing one.

Reading tables out of a PDF is the least reliable thing this repository does, so the
importer checks itself against the report's own row numbering. That guard earned its place
immediately: a first version silently dropped eight courts, including all six **Bucharest
sector courts** — among the largest in the country, Sector 1 alone carrying more cases than
every tribunal but Bucharest. A court map arguing that small courts are the problem while
missing the biggest urban ones would have been worse than no map. The tolerance check on
averages had passed at 4,5%; the rank-continuity check caught it outright, and with the
rows restored the reconstructed average matches the printed one to 0,0%.

## Decided: how the migration goes

No custom domain. URLs will be plain GitHub Pages project paths, one Pages site for the
whole repository:

```
cristiannichifor.github.io/romania-reforms/              the index
cristiannichifor.github.io/romania-reforms/justitie/
cristiannichifor.github.io/romania-reforms/salarizare/
cristiannichifor.github.io/romania-reforms/administrativ/
```

That breaks the links people already have, and for `salarizare` that matters more than it
looks: its whole design premise is that a scenario *is* a link, hash and all. So each old
repository stays alive as a one-page redirect that carries `location.hash` across, then
gets archived. Nothing shared before the move stops working.

A domain would remove the problem rather than absorb it, and the stubs are compatible with
adding one later — they would simply point somewhere else. Not needed now.

**Order, each step independently verifiable — after each, both old and new sites work:**

1. Move `salarizare`. Most tests, best understood, proves the layout under real load.
2. Extract `packages/ui` (`money.ts`, the dataviz primitives, the nav shell) only once
   `justitie` has an app that actually wants them — a second real consumer, not a guess.
3. Move `administrativ`, renaming `pipeline/` → `scripts/` and `web/` → `app/` to match.
4. Replace both old repositories with redirect stubs and archive them.

**Build:** both apps already read `VITE_BASE` from the environment instead of hardcoding a
path, so each is built with `VITE_BASE=/romania-reforms/<name>/` and the outputs are
assembled into one Pages artifact with the index. One deploy for the repository means one
broken build can block every simulator, so the assembly step should fail loudly and leave
the previous deployment standing rather than publish a site with a dead tile.

**Packaging:** a `uv` workspace with `members = ["simulators/*", "packages/*"]`, so each
simulator declares only the dependencies it uses — the flat list in the root
`pyproject.toml` is a placeholder for the single simulator that exists today. npm
workspaces over `simulators/*/app` and `packages/ui` on the Node side.

## Layout

```
packages/provenance   the shared vocabulary
scripts/              one validation gate for every simulator's data
simulators/<name>/    schema/ · scripts/ · data/ · sources/ · engine/ · app/
```

## Running it

```sh
uv run python simulators/justitie/scripts/import_instante.py   # fetches and parses
uv run python scripts/validate_data.py                          # the gate
```

Importers download their sources on first run and keep them, so a re-import does not
depend on a government website being up.
