# Public Pay Simulator (Romania)

Compare Romanian public-sector pay regimes against each other and against the Danish
model — the 2017 framework law, the July 2026 unified draft, and your own proposal, side
by side. Everything runs in the browser; a scenario is a URL.

> **This is a tool for public debate, not a payroll calculator.**
> It computes what a law *says*, not what anyone is actually paid. No figure here is an
> entitlement, and no scenario is a recommendation.

## Status

Built and live. The three views the brief asked for are there, both Romanian regimes and
the Danish comparator are imported from their sources, and every number carries the
document and article it came from.

**Done**

- `schema/` — regime, crosswalk and fiscal document types; one schema swallows RO and DK
- `engine/` — pure, no runtime dependencies, 124 tests. `payslip()` reproduces the Danish
  published figures to the krone
- `ro-draft-2026-07-16` — 1 049 positions, 2 929 variants, from the ministry's workbook
- `ro-153-2017` — 1 524 positions, from the consolidated annexes; every coefficient
  confirmed against the salary printed beside it
- `dk-stat-2026` — 16 positions transcribed from the IDA tables, plus 165 measured series
  from Danmarks Statistik
- Budget execution, the 20% ceiling per *ordonator*, and INS measured base pay
- A home page explaining the scope, seven views behind it, a year control, and every
  scenario in the URL
- 27 Python tests over the importers, schema validation in CI, Pages deploy

**Blocked, and not by us**

These are properties of what Romania publishes. They are recorded in the data, surfaced
on the pages they affect, and are not work waiting to be done.

- **Filled posts per position.** Nothing published maps headcount to the 1 049 functions.
  The MF report stops at the *ordonator*; INS stops at ten ISCO groups and omits public
  administration entirely. `aggregate()` is implemented and tested and has nothing to run
  on, which is why envelope mode is top-down.
- **Art. 33, the transitional difference.** Needs individual November 2026 income, which is
  not published. Bounded as far as the data allows: no matched post's base falls below its
  2022 grid value, because the reference rise more than covers the largest fall in standing.
- **The ±15% band for health units.** Set by a Government decision that is not published.
- **Two seniority mechanisms.** Art. 13(2) and the Annex I seniority rows contradict each
  other. That is a finding about the law, not a defect to repair.

**Editorial, and better done by someone who knows the job families**

- Crosswalk coverage past 34%. Matching by title is exhausted — a study-level tiebreaker
  was tried and resolved none of the seven ambiguous groups. Going further means reading
  duty descriptions.
- 97 positions where the importer refused to split a merged title and said so.
- The Danish comparator is 16 transcribed positions against 1 049 Romanian ones. Counts
  and spans derived from it are marked as a sample on the landing page and do not win
  their row; the measured comparison on *Meserii RO–DK* is the one to trust.

Live: <https://cristiannichifor.github.io/public-pay-simulator/>

## Two constraints that shape everything

1. **The law is data, not code.** Every regime is a JSON document validated against one
   schema. The engine is a pure function. Changing a coefficient means editing JSON — never
   TypeScript. If the schema cannot express a system without special-casing it, the schema
   is wrong and gets fixed.
2. **Compare levels only against each system's own middle.** This started as "never compare
   RON and DKK", which was too blunt to be useful: a reader shown 38 264 DKK has to leave the
   page to know whether that is a lot. So amounts are compared, under two rules that hold
   everywhere. A figure in a currency the reader does not think in never appears alone —
   `money.ts` is the one place that decides this, and it always adds RON and EUR. And a
   cross-country *comparison* is always a ratio to that country's own median, never a
   converted amount set beside another converted amount. Denmark is still mainly here for
   shape: how a ladder is built, how much of pay is base, how far apart the ends sit.

## What the same schema had to swallow

Romania and Denmark turn out to be the same multiplication:

```
base = positionValue × reference.amount × reference.factor
```

Romania freezes a coefficient and moves the reference value (4 100 lei, Art. 36(2)).
Denmark freezes a 2012 basic amount and moves the *reguleringsprocent* (1,265085). Same
arithmetic, opposite halves held still. The Danish figures reproduce exactly: 261 000 ×
1,265085 = 330 187 as published, pension 59 665, gross 389 852.

Where the schema had to grow past the obvious design:

- **Seniority is two different mechanisms.** Romanian *gradații* compound (+7,5/5/5/2,5/2,5%);
  Danish scale grades each name their own absolute amount, and a Danish bachelor walks
  grades 1, 2, 4, 4, 5 — a path with a repeat. So a ladder has typed steps and a position
  carries its own path through them.
- **`countsToCap` cannot be a boolean.** Art. 15(18) exempts the EU-funds supplement from the
  20% ceiling *to the extent it is settled from external funds*, and 15(19) puts the
  co-financed share back in. It is a proportion.
- **Coefficients are dated.** Annex IX phases dignitary coefficients across 2026/2027 → 2031.
  The same primitive carries the Danish regulation factor and the annual Romanian reference.
- **Caps are plural and of three different kinds** — share of base, share of headcount, and a
  growth bound on the reference value itself.

Full reasoning: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## What reading the sources actually turned up

- **The coefficients are back-solved, not designed.** 1 376 distinct values; 852 of them
  (61,9%) carry 14 or more decimal places and 585 sit at 16. Only 224 are rounded to two.
  The workbook still has the working columns visible — old-lei and new-lei amounts side by
  side, ratio columns, live `#DIV/0!` cells.
- **The 1:8 ratio is a five-year destination.** The grid does reach it — exactly — but only in
  2031. The floor is 1,00; the Annex IX ceiling climbs 6,4702 → 6,85 → 7,24 → 7,62 → 8,00.
  The ratio in force when the law commences is 1:6,47.
- **The grade structure has gaps that real coefficients fall into.** Art. 9(2) defines bands to
  two decimals (grade 1 ends at 1,19, grade 2 starts at 1,20) while the annexes deliver
  sixteen. 92 of 2 821 variants (3,3%) belong to no salary grade at all.
- **The law merges jobs with punctuation.** Roughly a quarter of coded positions collapse two
  or more former titles into one code and one coefficient — `Director; șef compartiment;
  inspector șef; comisar șef divizie; …` is nine. No assimilation table is published.
- **Two seniority systems coexist.** Art. 13(2) says every execution coefficient is set at
  *gradația* 0, but Annex I publishes a separate coefficient row per seniority band. For
  teaching staff, applying the *gradații* on top would pay seniority twice.

Each of these is recorded as a `limitations` entry inside the regime document, keyed to the
output it affects, so the caveat travels with the number instead of living in a footnote.

## Position assimilation

The draft abrogates Law 153/2017 (Art. 37) and requires everyone to be reassigned onto a new
position (Art. 32) — but publishes no mapping, leaving each *ordonator de credite* to decide.
The same former title can therefore land differently in two institutions.

The model splits this in two, on purpose:

- **Within a regime**, `position.titles[]` records the titles the source itself merged into one
  row, alongside the raw cell verbatim and how much to trust the split. The merge is a fact of
  the source.
- **Between regimes**, `data/crosswalks/` holds the mapping as a separate document with its own
  provenance. A regime never depends on another regime to be read, and deleting a crosswalk
  never changes what a law says.

Crosswalks are typed by cardinality — `merge`, `split`, `abolished`, `new` — because a
nine-to-one merge and a rename are different claims.

`scripts/build_crosswalk_153.py` now reconstructs the 153/2017 → draft mapping, and the
hard part is that the two laws name jobs differently on purpose: 153/2017 keeps every
qualifier inside the title (*Profesor studii superioare de lungă durată grad didactic I*)
while the draft moved qualifiers into dimensions (*Profesor* carrying a `grad`). Matching
the strings directly fails on exactly the posts that did not change.

So it matches twice and refuses more than it accepts — exact title within a family
(`derived`), then the same title with qualifiers stripped, one-to-one only (`assumed`).
**221 links, covering 34% of the old grid and 38% of the new.** An exact match is allowed
to be wide, because both laws print the same title once per employer and *Director*
legitimately joins twelve former posts to eight new ones; a stem match is not.

A third pass was written and removed. Where a stem matched several posts on each side, the
study level looked like it should decide which is which — *Consilier* with an S row and an
M row on both sides is two unambiguous pairs, not one ambiguous group. It resolved **none**
of the seven candidate groups; the levels do not line up on the remaining collisions. So
coverage stays at 34%, and going further means reading duties rather than titles, which is
editorial judgement a script should not fake.

`abolished` is never emitted, and that is deliberate. Calling every unmatched former post
abolished would roughly double the apparent coverage and would assert something the
evidence does not support: a post with no same-named counterpart is usually one the script
could not resolve, not one the draft deleted.

Across the 117 one-to-one links, the median post keeps its place almost exactly — a
coefficient ratio of **1,014**, with p10 at 0,84 and p90 at 1,21. That is a change in
*standing*, not in pay: the reference value moves from 2 500 lei to 4 100 lei, so
coefficients measure position in the hierarchy rather than an amount. The payslip says so
next to every figure it shows.

## The law in force, and what it shows

For most of this project's life there was no "today". The law actually paying people —
153/2017 — was listed as blocked on "the consolidated annexes", which turned out to mean
nobody had gone and fetched them. legislatie.just.ro serves the consolidated text with all
annexes as HTML: 176 tables, each row giving the position, the study level, the 2022 base
salary in lei, and the coefficient.

`scripts/import_153.py` reads them, and it proves its own work. The source prints the
salary beside the coefficient that produces it, so salary ÷ (coefficient ÷ 100) must land
on the 2 500 lei reference. Headers alone were not enough — merged header cells make the
parser repeat "Coeficient" across every column, which first produced a grid running 0,01
to 12,00 with a 1:833 span and salaries out by a quarter of a million lei. Every
coefficient is now confirmed against its printed salary **row by row**: 1 750 confirmed,
worst deviation 9,90 lei (the law's own rounding), 11 dropped as unconfirmed.

The result changes what the comparison is about:

| | 153/2017, today | Proiectul MMFTSS | Propunerea | Danemarca |
| --- | --- | --- | --- | --- |
| Numbers to decide | **230** | 1 264 | 324 | 16 |
| Back-solved (≥14 decimals) | **0%** | 60,3% | 0% | 0% |
| Span | **1:7,02** | 1:7,39 → 1:8,00 | 1:7,00 | 1:3,55 |
| Names hiding the institution | **0** | 37 | 0 | 0 |

The draft is not simplifying a tangle. The law in force decides 230 numbers, every one
printed to two decimals. The draft asks for 1 264, five and a half times as many, and
60,3% of them carry fourteen decimal places or more — the residue of dividing existing
salaries rather than the product of a decision. And it *widens* the gap between lowest and
highest paid, from 1:7,02 to 1:7,39 on day one and 1:8,00 by 2031.

Two things this regime deliberately does not do. It models **no supplements** — 153/2017
scatters them across annexes and connected acts, so the comparison holds for base pay and
not for total income. And it models **no levies**, so it yields no net figure: the Fiscal
Code rates in this repo were marked `assumed`, with a note that they came from no source
in `./sources`, and a law described as in force may not carry guessed provenance. Verify
those rates and the net follows.

## Four systems, one screen

The landing page asks the same seven questions of the ministry's draft, our proposal, and
Denmark. The strongest single result:

| | MMFTSS | Propunerea noastră |
| --- | --- | --- |
| Named positions | 1 049 | **767** |
| Distinct coefficients | 1 264 | **324** |
| Back-solved (≥14 decimals) | 61,9% | **0%** |
| Coefficients in no salary grade | 92 | **0** |
| Years until the declared grid applies | 5 | **0** |

Rounding to two decimals reveals that the grid only ever needed 324 distinct values. The
other 940 were the residue of dividing one salary by another.

The position count falls for a different reason. The draft names a job once *per
employer*: "Director" appears under 25 codes across six annexes, "Șef serviciu" under 25
more, "Director general adjunct" under 22. So 1 176 measures how many institutions exist,
not how many occupations. Merging rows that agree on title, occupational family, kind of
post and study level — and only those — collapses 282 of them, and turns the pay
difference between employers into an explicit multiplier instead of a second job title.

That import defect is now fixed at the source. The workbook writes a rank under the
occupation it belongs to and indents the cell — `"         gradul  I"`, `"    clasa a
II-a"` — and the importer had two ways of losing the parent. In Annex I the occupation
sits on its own line with no coefficient beside it, so the row was skipped and its name
thrown away. In Annex VIII the occupation is in one column and the class in the next, and
a "longest text cell in the row" fallback promoted `"    clasa a II-a"` to a job title
whenever the occupation cell was blank — defeating the importer's own continuation logic.

Both are repaired: ranks now become a `grad` dimension on the position above. `Pilot
instructor` is one position with three class variants instead of three positions, 524
positions carry a grad dimension across 958 variants, and the grid went from 1 176
positions to 1 049 without losing a single coefficient. Positions named after a bare rank
fell from 116 to 12, and those twelve are real occupations — *asistent medical*,
*asistent social*.

The merge keeps its own guard anyway, because the two fixes are independent and a future
sheet layout could reintroduce the rows. A test builds a regime containing exactly the
defect and asserts the merge refuses it.

**Our proposal is a patch list, not a second grid.** Five named edits against the
ministry's document, each naming the defect it fixes — and a test asserts every patch
points at a limitation the base regime actually declares, so a policy preference cannot
enter dressed as a repair. None of the five moves any salary relative to any other:
compression, the reference value, and the split between occupational families are left
exactly as the ministry proposed. What changes is whether the rules written in the law can
be applied at all.

## Comparing Romanian and Danish pay

Two different things, kept apart on purpose.

**Inside the payslip view**, regimes denominated differently — RON per month against DKK
per year — sit side by side with **no delta**, and what remains is a dimensionless table:
base as a share of gross, supplements as a share of gross, net over gross, employer cost
above gross, seniority uplift.

**In the equivalence view**, amounts *are* converted, because a reader comparing two
systems needs a unit they think in. The rate is the ECB daily reference rate, committed as
a dated series in `data/fiscal/ecb-fx.json` rather than written into the app, so any
converted figure can be traced to the day it was taken. Every screen carrying a converted
number also carries the caveat that a market rate says how large a number is, not what it
buys — Danish price levels are substantially higher, so a converted salary is not the same
standard of living.

## The same job, two systems

`Meserii RO–DK` regroups the grid by **occupation** rather than by annex, then sets each
group beside what the same job earns in the Danish public sector. Every group states the
rule that selected it and how many positions it caught, so the grouping can be disputed
rather than only the numbers.

Both sides are expressed against the middle of their own system — the median base salary
of the Romanian grid, the median earnings of all Danish public employees — so the units
cancel and the ratios compare. As multiples of that middle:

| | România | Danemarca |
| --- | --- | --- |
| Medici | 1,15–1,63× | 1,17–**2,41×** |
| Asistenți medicali | 0,84–1,05× | 0,94–1,18× |
| Învățători și profesori de gimnaziu | **0,97–1,04×** | 1,06–1,22× |
| Personal administrativ, studii medii | 0,74–0,94× | 0,84–1,06× |
| Conducere | 1,29–2,23× | 1,84–2,26× |

Denmark's figure includes supplements, so the Romanian one has to as well or the
comparison is rigged. The Art. 21(2) ceiling — 20% of the base wage bill — is added as a
second, hatched segment, and it moves the reading: nurses go from below their Danish
counterparts to slightly above, care staff from 0,89–1,14× to 1,07–1,37× against Denmark's
0,87–1,10×.

That ceiling is not what it first appears, and the page says so. It is measured **per
ordonator principal de credite, per funding source — not per person**, so it caps an
institutional average rather than anyone's payslip. And the statute lifts a long list out
of it: night work, overtime, disability, three-shift health work, Delta isolation,
EU-fund administration, and the performance premium. Three supplements remain inside.

## How big the supplement layer already is

For a long time this page could only put a Danish fact beside a Romanian legal ceiling:
Denmark publishes what it paid, and Romania looked as though it published nothing below
"personnel expenditure". It does. Every public entity files its budget execution against
the economic classification, and that classification runs to paragraph depth — `10.01.01
Salarii de baza` beside `10.01.05 Sporuri pentru conditii de munca` and `10.01.06 Alte
sporuri`. [transparenta.eu](https://transparenta.eu) has those filings in a queryable
database; summing the *ordonatori principali* gives a national figure without counting a
subordinate institution twice. `scripts/import_executie.py` reads it over GraphQL.

So both sides are now measured, and the answer is not the one the headline numbers
suggest:

| | România | Danemarca |
| --- | --- | --- |
| Tot sectorul public | 81% bază, **18,8%** peste | 94% bază, **5,5%** peste |
| Sănătate | 72% bază, **27,6%** peste | medici 12%, asistenți 10% |
| Educație | 86% bază, **14,4%** peste | profesori 1,9% |
| Ordine publică | 74% bază, **26,2%** peste | poliție 8,6% |

Romania's layer above base pay is about **3,4×** the Danish one. The interesting part is
not that a 20% ceiling exists — it is that pay already leans on supplements this heavily,
which is what makes the ceiling bind.

Three adjustments make the two comparable, and `engine/composition.ts` does them in one
place because getting them wrong changes the answer:

- **Employer pension (13,5%) and paid sickness (5,7%) come out of the Danish side.**
  Romania excludes title `10.03` and pays sick leave from a different title, so leaving
  them in would compare pay against the cost of employment.
- **Delegation and secondment come out of the Romanian side** — reimbursed expense, not
  pay, and with no Danish counterpart.
- **Holiday pay comes out of neither.** Danmarks Statistik prints it at ~12%, which invites
  subtracting it — but it prints it with a leading `..` because it is a sub-item *inside*
  basic earnings, not a component beside it. A Dane on holiday keeps drawing salary, as a
  Romanian does. Subtract it and Denmark appears the more supplement-heavy system, which is
  the opposite of the truth. The importer marks it `composition-subitem`, the engine refuses
  to sum it, and a test pins the reversal.

Two things this does not claim. The economic classification is an accounting vocabulary,
not the law's: what lands in `10.01.05` is not the set Art. 21 caps. And the execution
describes the *current* regime — the draft's ceiling has never applied to a single year.

## The grid against a measurement

Every Romanian number in this project came from a statute — a coefficient times a reference
value, which is what the law *says*. The Danish side has had measured earnings since the
first import, and the asymmetry sat as a limitation on nearly every page.

INS matrix **FOM121A** closes it for two sectors. It carries employee counts, the **salariul
brut de bază** and gross income, split by ownership, CAEN activity and ISCO major group —
so the public sector can be isolated and the *base* salary compared with the grid's own
quantity. `scripts/import_ins_ocupatii.py` reads it.

| 2024, proprietate publică | angajați | bază măsurată | mediana grilei (proiect) | |
| --- | --- | --- | --- | --- |
| Învățământ | 289 396 | 9 596 lei | 7 848 lei | **+22%** |
| Sănătate | 280 405 | 7 280 lei | 7 322 lei | **−1%** |

**The draft's health grid lands within one percent of what health workers are actually paid.
Its education grid sits 22% below.** Whatever else the draft does, in education it either
moves teachers down or leans hard on the transitional difference.

It also settles a caveat that had been asserted rather than measured. The Art. 33 bound is
stated against the 2022 grid printed in the annexes, and the reason is now a number: that
grid gives an education median of 5 525 lei against 9 596 measured in 2024 — **42% below**.
The annexes are not what anyone is paid.

Three limits ship with it, one of them blocking:

- **Ten ISCO major groups, not 1 049 positions.** It answers "what does a public-sector
  specialist in education earn", never "what does an auditor earn", and cannot weight the
  grid by position — that gap stays exactly where it was.
- **The grid counts positions; the survey counts people.** A grid median treats a post held
  by forty thousand teachers and one held by a single chief inspector as one vote each.
  Weighting the grid properly needs per-position headcount, which is the thing nobody
  publishes. The comparison is informative and is not an equality test.
- **No CAEN section O.** Sections A–S are covered, O — public administration and defence —
  is not. Education and health are in; ministries, police and the army are out.

The transport is worth recording. The data POST goes to `/tempo-ins/pivot` with a
colon-separated `encQuery` string, not to `/tempo-ins/matrix/{code}` with a JSON array —
five plausible shapes against the latter all return 400. transparenta.eu mirrors 1 898 INS
datasets but lists this one as `SYNCED` with zero observations, so it had to come from INS
directly. The contract was read off `github.com/mark-veres/tempo.py`.

## The four tax rates, finally verified

Four levies — CAS, CASS, income tax, CAM — sat in the draft's frame marked `assumed`, with
a note saying they came from no source in `./sources` and were "de verificat inainte de
publicare". They now quote OUG 79/2017 verbatim: **CAS 25%** (art. 138), **CASS 10%**
(art. 156), **impozit 10%** (art. 64), **CAM 2,25%** (art. 220³).

The detour is worth recording, because it is a trap. Fetching "Codul fiscal" from
legislatie.just.ro returns the **2015** text, and reading art. 138 there gives **26,3%**,
art. 156 gives **5,5%**, art. 64 gives **16%**, and CAM does not exist at all — the word
*asiguratorie* never appears. Those are the pre-2018 rates. OUG 79/2017 is what moved the
contributions onto the employee, so it is the amending act, not the consolidated code,
that states the numbers in force. A verification against the obvious source would have
confirmed the wrong figures with full confidence.

With provenance upgraded, 153/2017 gets its levies back and produces a net, which it could
not before: a law described as `in-force` may not carry guessed provenance, and rather than
mislabel its status the regime had shipped with no levies at all.

## How far Art. 33 could reach

Art. 33 preserves November 2026 income where the new pay would be lower. Whether it catches
any particular person cannot be computed — Romania publishes no individual income — but
half the question closes. The reference rises from 2 500 to 4 100 lei, so a post ends up
with a smaller base only if it falls below **61%** of its current standing. The worst fall
observed is **65%**. So **0 of 117** matched posts have a lower base under the draft.

That is not "nobody loses", and the page says so in a blocking limitation. The comparison
is against the **2022 grid printed in the annexes**, not against what is paid in November
2026 — annual increases since 2022 sit on top of those figures — and Art. 33 looks at
*total* income, supplements included. What is settled is the base-salary question against
the published grid. The real one stays open and cannot be closed with public data.

## Who moves up and who moves down

The payslip answers this one post at a time, which is the right shape for an argument
about a job and the wrong shape for an argument about a reform: a reader can always be
shown the post that makes their case. `engine/distribution.ts` asks it of the whole
matched grid, and the answer is not the one the median suggests.

| | share |
| --- | --- |
| scade peste 20% | 3% |
| scade 10–20% | 19% |
| scade 2–10% | 18% |
| **aproape neschimbat** | **13%** |
| urcă 2–10% | 15% |
| urcă 10–20% | 22% |
| urcă peste 20% | 11% |

The middle post keeps its place almost exactly — **+1,4%** — and only **13%** of posts
actually stay put. 39% fall, 48% rise. A reform that left the hierarchy alone would show
one bar in the middle; this one is U-shaped. Reporting only the median would miss the
churn entirely, and reporting only the tails would invent a story the middle contradicts.

By family, on the posts that could be matched: diplomacy falls (median −2,6%, 85% of its
posts losing), while defence and public order rise (+18%, none losing). The biggest single
falls are school support roles — *Pedagog școlar* at −35%, *Supraveghetor noapte* at −28%
— and the biggest rises are financial management — *Director financiar-contabil* at +73%,
*Director economic* at +56%.

Three things the page refuses to let the numbers imply, stated on it rather than here:

- **This is standing, not pay.** The reference moves from 2 500 to 4 100 lei, so a post
  that falls 10% in coefficient may still receive more lei. The ratio says who rose
  relative to everyone else.
- **It is 117 posts of 1 524** — the one-to-one links. Another 104 links join several
  posts on a side and have no single before-and-after, so they are counted and set aside
  rather than averaged into a move nobody made.
- **A family with one post is not a trend.** Anything under five matched posts is drawn as
  a dashed outline and labelled as too thin to support a conclusion.

## The grid is a five-year walk, and you can step through it

Art. 5 promises 1 to 8. Annex IX publishes a column per year and walks the dignitary
coefficients from 2026/2027 to 2031, so "the ratio is 1:8" and "the ratio is 1:7,39" are
both true and differ only by the year meant. `spanByPeriod` had computed this from the
start, but a reader could only ever see the two endpoints.

A year control now sits above the pages whose numbers move, and it is generated from the
data: `engine/phase.ts` reads the periods out of the regime, so an annex that phases
something differently changes the slider without an edit in code. The year goes into the
hash (`a=2031-12-01`), so a particular year is a link like everything else.

Stepping through it turns up something the endpoints hide:

| | 2026/2027 | 2028 | 2029 | 2030 | 2031 |
| --- | --- | --- | --- | --- | --- |
| Span | 1:7,39 | 1:7,39 | 1:7,39 | 1:7,62 | 1:8,00 |

Nothing moves for four years. The phased dignitary coefficients spend them below a post
that is not phased at all — *Manager TIC*, at 7,392 — so the eșalonare is invisible until
2030. That is only visible if you can walk the years one at a time.

## Is the supplement layer growing?

The execution importer pulls 2021–2025 and the page had been showing only the last year.
It is not growing. The share of public pay above base salary went **25,5% → 18,8%** over
those five years, down 6,7 percentage points, most of it since 2023.

That matters for how the 20% ceiling should be read. It is not a brake on something
accelerating; it lands on a layer that has been shrinking on its own, and it would already
bind on 40,4% of the wage bill the day it commenced.

## Who the 20% ceiling actually binds

Art. 21(2) caps supplements at 20% of the base wage bill **per ordonator principal de
credite and per funding source**. The fiscal importer used to record, as a *blocking*
limitation, that no open dataset published spending at that level — so the ceiling could
be illustrated and never evaluated.

`entityAnalytics` publishes exactly that level: spending per reporting entity, with
`report_type: PRINCIPAL_AGGREGATED` folding each subordinate into its principal, and
`funding_source_ids` splitting the second dimension. Two filters, and the ceiling becomes a
measurement. `scripts/import_plafon.py` reads it; `engine/cap.ts` shapes it.

| measured on | breach | share of the base wage bill behind them |
| --- | --- | --- |
| ordonator × sursă, as the law says — accounting "sporuri" | 159 of 4 407 | **20,3%** |
| ordonator × sursă — everything paid above base | 316 of 4 407 | **40,4%** |
| ordonator, sources merged — accounting "sporuri" | 56 of 3 287 | 19,4% |

Both controls stay on the page, because both change the answer:

- **Scope.** Merging funding sources hides breaches: 56 institutions look non-compliant
  that way, 159 pairs do when each source is measured on its own. The law measures the
  pairs.
- **Measure.** `10.01.05 + 10.01.06` is what the budget labels supplements; the wide
  reading takes everything above base pay that is not a reimbursed expense. Education sits
  at 4,0% narrow and 15,2% wide — the difference is `plata cu ora`, booked elsewhere. An
  institution can look compliant purely by choosing a paragraph, so the wide reading is the
  one that cannot be arranged away.

Named, on the wide reading: Sănătate 39,7%, ÎCCJ 31,6%, Municipiul București 30,2%,
Județul Iași 29,9%, PÎCCJ 24,5%, MAI 20,7%.

The same two caveats apply as everywhere else here: the economic classification is not the
Art. 21 set (the statute lifts overtime, night work, disability, three-shift health work,
Delta isolation, EU-fund administration and the performance premium out of the ceiling),
and the execution describes the current regime rather than the draft.

## The envelope, on the budget's own accounting

Envelope mode used to start from Eurostat's COFOG breakdown of compensation of employees.
It now starts from the execution reports: **title I in full — pay in cash, pay in kind,
and the employer's contributions — 161,4 mld lei for 2025, 9,2% of GDP.**

Three reasons the swap is not cosmetic:

- It is the accounting the law is written in. Art. 36 alin. (3) sets its target against
  personnel expenditure as the budget defines it, so the baseline and the target now share
  a denominator. Under Eurostat's D1 the same page read 11,2% and the target arithmetic was
  comparing two different definitions.
- It runs to the current year rather than lagging one.
- It splits by budget chapter, which is closer to the annexes than a COFOG function is.

Contributions are *included* here and *excluded* from the composition comparison on the
same page — deliberately, and for opposite reasons. The composition sits beside Danish
earnings, which exclude pension; the envelope answers what the state spends. Same source,
two questions, and each says which it is answering.

The chapter → occupational-family mapping stays approximate and still says so: defence and
public order are two budget chapters and one family in the annexes.

## Naming: institution and statute, or occupation and expertise

Denmark names a post by what the person does and what it requires — *engineer*,
*specialist consultant*, *department head*. The Romanian draft names it by the employer and
the legal status — *funcție publică de execuție, grad profesional superior, categoria
înalților funcționari publici*.

`data/crosswalks/ro-draft-2026-07-16--dk-stat-2026.json` puts the two side by side and,
where the naming logics actually differ, proposes the labour-market name. Every link
declares its basis, its confidence, and whether it is disputed; weak ones are labelled weak
on screen. The most important entry is the one with no Danish endpoint at all: IDA's tables
cover engineers and academics, so the bottom of the Romanian grid — *părinte social,
îngrijitor la domiciliu* — has nothing published to be compared against.

## Layout

```
schema/     regime.schema.json, crosswalk.schema.json — the contract
engine/     Pure TypeScript, zero runtime dependencies, vitest
app/        Thin UI over the engine. Built last.
scripts/    Python importers and probes. Committed and re-runnable.
data/       regimes/, crosswalks/, headcount/ — every number carries provenance
sources/    The Romanian documents. The Danish PDF is gitignored; see .gitignore.
docs/       METHODOLOGY.md, DATA_QUALITY_COEFFICIENTS.md
```

## Data honesty rules

1. Every number in `data/` names its source document and article or sheet cell, and declares
   whether it is `verbatim`, `derived`, or `assumed`. Nothing publishes while `assumed`.
2. Romania publishes no per-person microdata. Aggregation runs on filled-post counts, and the
   UI says so where the totals appear — not in a footnote.
3. Where a source has no answer, the output is `null` with a stated reason. Danish net pay is
   `null`: IDA's tables carry no tax schedule, and inventing one would break rule 1.

## Licence

Apache-2.0. The source documents in `sources/` are Romanian government publications and carry
their own terms.
