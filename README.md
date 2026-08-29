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
| **justitie** | The judicial reform | in progress |
| **salarizare** | Public-sector pay — [live](https://cristiannichifor.github.io/public-pay-simulator/) | to migrate |
| **administrativ** | Consolidation of the 3 186 UATs — [live](https://cristiannichifor.github.io/administrative-reform-simulator/) | to migrate |

The two live ones stay in their own repositories until `justitie` has proven which pieces
are genuinely shared. Extracting an abstraction before its second real consumer exists is
how shared packages end up wrong.

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
