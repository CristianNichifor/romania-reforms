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
| **justitie** | The judicial reform | migrated to the 2025 report |
| **salarizare** | Public-sector pay | migrated |
| **administrativ** | Consolidation of the 3 186 UATs | migrated |
| **impozit-teren** | Taxing land on its value | both taxes computed, 2 counties of 41 |

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

### impozit-teren

Romania taxes land on **surface area** times a coefficient from the Fiscal Code — rank of
locality, zone letter, and nothing about what the land is worth. This models the other
option: taxing land on its value, and what that would move.

The value exists and the state already leans on it. Each Chamber of Public Notaries publishes
an annual *studiu de piață* setting minimum orientative values, used as the floor for notary
fees and transfer tax. It is the only valuation of Romanian land that is official, national,
published, and granular below the commune — Bacău's study prices land **village by village**,
in EUR/m², split by use category, with towns priced by zone letter instead.

`scripts/import_ghid.py` reads it. Two counties are in, from two documents:

| | villages | communes | towns zoned | pages |
| --- | --- | --- | --- | --- |
| Bacău | 528 | 85 | 8 + 1 commune | 129 |
| Neamț | 664 | 78 | 5 | 108 |

**The residual method these grids were expected to need turned out to be unnecessary.** The
first plan recovered land value from property prices minus depreciated building cost, on the
assumption that the studies carried a construction-cost table. They do not — "costuri de
construcție" appears in them only in prose. They print land outright, which is better, and
the check that found this cost an afternoon rather than a rewrite.

The parse is measured against the **INS land register**, not against another page of the same
document: every locality the register lists for the county must come out of the study's tables,
and every locality the tables yield must be one the register lists. The schema refuses to
validate a file where either direction fails. An earlier version checked against the study's
own organisation page, which exists in the two documents from CNP Bacău and in none of the
fifteen tried from four other chambers. That gate earned itself immediately and repeatedly — a number pattern treating a space as
a thousands separator read Bacău's `256 123 48 35` as one number and silently dropped the
**curți construcții** row of the county's largest city, which is the single row a land tax
mostly lands on. Row counts looked fine throughout.

Two things the documents do that no template survives: commune names wrap **mid-word** —
`CLEJ` / `A`, `ONCEST` / `I`, and Valea Seacă split four ways with its last letter sharing a
line with the first village — and the same study spells the same place two ways, printing
`GIRLENI` for Gârleni but `BARSANESTI` for Bârsănești. Names are therefore resolved against
the roster rather than parsed, and a fragment is only absorbed if absorbing it turns an
unrecognised name into a recognised one.

**The other half is how much land there is.** A price per square metre is not a tax base
without a count of them. INS matrix `AGR101B` has hectares per locality by the same cadastral
categories the notaries price; `import_fond_funciar.py` reads it and `build_valoare_teren.py`
multiplies the two together.

| | localities | area | built-up | land value, low → high |
| --- | --- | --- | --- | --- |
| Bacău | 93 | 662 052 ha | 21 719 ha (3,3%) | 2,8 → 9,7 bn EUR |
| Neamț | 83 | 589 614 ha | 15 224 ha (2,6%) | 3,5 → 9,4 bn EUR |

**The answer is a band, and the band is the finding.** The grid publishes one price per
village and one per town zone, and neither villages nor zones have published areas to weight
them by — so every commune is valued at its cheapest published price, its dearest, and the
unweighted mean, and all three travel together. A single confident number here would be a
fiction. Two assumptions carry the arithmetic and both are `blocking`: that curți-construcții
is the intravilan (the register does not record the split, and intravilan land is priced up to
250× higher), and the absent weighting above.

Two defects worth recording because neither threw and both validated. INS repeats a dimension
label only when it changes and writes `-` underneath, so read literally the table credited
every category of every commune to the one named on the first row — putting Bacău county at
**4 319 hectares instead of 662 052**. And matching commune names on one spelling of â lost 16
of 176 communes, each of which then had no land value rather than a visibly missing one. Both
are now tested against numbers from outside the pipeline: the counties' real surface areas.

**Both taxes, on the same hectares.** `import_cod_fiscal.py` reads article 465 of Legea
227/2015 — five tables — from the consolidated text on the legislative portal, and
`build_impozit.py` levies it on the same land the value was computed from. Statutory against
statutory, deliberately: comparing a modelled tax with what councils actually collect would
attribute arrears, exemptions and collection rates to the change of rule.

| județ | Cod fiscal, mil RON | valoarea terenului, mld RON | **cota neutră** |
| --- | --- | --- | --- |
| Bacău | 40 → 94 → 179 | 15 → 28 → 51 | 0,08 → **0,33** → 1,21 % |
| Neamț | 31 → 64 → 114 | 18 → 31 → 49 | 0,06 → **0,21** → 0,62 % |

**A land value tax replacing today's land tax would be a fifth to a third of one per cent** of
land value in these two counties — an order of magnitude below the 1% that gets assumed in
argument. The reason is not that land is worth little; it is that the current tax is very
small relative to the value it sits on.

**The tax we already have is a band too, and a wider one than the land value.** That was the
surprise. Article 465 (2) does not state a rate, it states 8 282–20 706 lei/ha for zone A of a
rank-0 locality, and paragraph (9) leaves the choice to the local council. The zone A–D is a
council decision as well, with no national register of zones or their areas. And a commune's
seat is rank IV while its other villages are rank V. Three unpublished local decisions
multiply: **the cheapest and dearest lawful readings of today's tax differ by 4,5× in Bacău.**
Nobody can say what Romania charges on land without reading 3 186 council decisions.

**Where it stops, and it stops early — two counties of 41, and the reason is measured.**
Fifteen more were tried, from four other chambers: Alba, Sibiu, Hunedoara, Cluj, Maramureș,
Bistrița-Năsăud, Sălaj, Timiș, Arad, Caraș-Severin, Iași, Satu Mare, Vâlcea, Mureș, Harghita.
**None parsed**, and none was landed, because a grid that fails its own checks is worse than
a county that is honestly absent.

The studies are not one document in 41 editions. They are written by different valuation
firms — Cluj's by a company in Cluj, Timiș's by another in Timișoara — and share no layout:

| chamber | what the tables look like | distance from here |
| --- | --- | --- |
| Alba, Iași, Mureș, Harghita | closest to Bacău's shape; 30–70% of communes parse | a dialect of the same parser |
| Cluj (CJ, MM, BN, SJ) | 22–45 pages for a whole county, compact per-locality tables | a second parser |
| Timiș, Arad, Caraș, Satu Mare, Vâlcea | prose by court circumscription; no per-village land table in this shape at all | a different document |

What did generalise is the checking. The **land areas are imported for all 42 counties** on
demand, and the register is now the roster every grid is measured against — so the next
chamber's parser starts with its check already written.

Inside towns the value depends on zone A–D and the zones are defined as **lists of
streets and house-number ranges**, not polygons; there is no published geometry for them, so
urban values are per-town and per-zone but cannot be put on a map below the town. And the
grids are legal floors, not transactions: they sit under market prices by a margin that is
neither published nor constant between counties. They rank places against each other far
better than they measure any of them, and that limitation is carried as `blocking` so it
reaches every figure derived from it.

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

## Adding a reform

Five edits, deliberately by hand:

1. `simulators/<name>/` — its own `schema/`, `scripts/`, `data/`, `sources/`, and an app if it
   has one. Its data validated by its own script; the caveat vocabulary from
   `packages/provenance` so a limitation means the same thing across simulators.
2. A job in `.github/workflows/ci.yml`.
3. A build step in `.github/workflows/deploy.yml`, with `VITE_BASE` set to
   `/${{ github.event.repository.name }}/<name>/`.
4. A line in that workflow's assembly step, and its path in the check below it — the check is
   what stops a simulator that failed to build appearing on the landing page as a link to a
   404.
5. A card in `site/index.html`.

**Not a registry, and not a shared build.** Three simulators have three shapes: one React, one
not, one with no interface at all; `app/` in one and `web/` in another; different test
commands and different lockfiles. A config file over three special cases would be the same
mistake as extracting a UI package from a single consumer — it reads as generality and
behaves as a fourth thing to keep in sync. Five explicit edits are cheaper to get right than
one clever one, and the deploy check catches the one that matters if you forget it.

## Running it

```sh
uv run python simulators/justitie/scripts/import_instante.py   # fetches and parses
uv run python scripts/validate_data.py                          # the gate
```

Importers download their sources on first run and keep them, so a re-import does not
depend on a government website being up.
