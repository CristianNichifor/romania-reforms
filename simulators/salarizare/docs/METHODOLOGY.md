# Methodology

How a pay law becomes a JSON document, and what the engine is allowed to do with it.

## The bet

A pay regime is **data**. One schema, `schema/regime.schema.json`, describes the 2017
framework law, the July 2026 draft, the Danish state agreement and any proposal anyone wants
to argue for. The engine is a pure function over that data. Changing a coefficient means
editing JSON.

The test of the schema is not elegance. It is whether Romania and Denmark both fit without a
branch anywhere saying "if Danish". Where they did not fit, the schema changed — four times
so far, each recorded below.

## One multiplication

```
base = positionValue × reference.amount × reference.factor      (then rounded)
```

| | Romania | Denmark (state) |
| --- | --- | --- |
| `positionValue` | coefficient, e.g. 2,499 | frozen basic amount, e.g. 261 000 |
| `reference.amount` | *valoarea de referință*, 4 100 lei | 1 |
| `reference.factor` | 1 | *reguleringsprocent*, 1,265085 |
| `reference.baseDate` | 2026-12-01 | 2012-03-31 |
| moves annually | the reference | the factor |

Two systems, opposite halves held still. Verified against IDA's published figures:
261 000 × 1,265085 = 330 187 exactly as printed; pension 18,07% = 59 665; gross 389 852.

Rounding differs and is therefore per-item, not per-regime: Romania rounds **up** to whole lei
"in favour of the employee" (Art. 10(4)); the Danish basic-salary scale rounds to whole kroner
but the supplement tables keep two decimals.

## Where the obvious design broke

**1. Seniority is not one mechanism.** Romanian *gradații* compound: +7,5%, then +5% on the
result, and so on, reaching ×1,24519 at *gradația* 5. Danish scale grades each state their own
absolute amount, and a bachelor walks grades 1, 2, 4, 4, 5 — a path with a repeat, because
grade 4 lasts two years. So `ladder.kind` is `compoundingUplift` or `absoluteSteps`, and the
path belongs to the position, not the ladder.

There is a third case inside Romania alone: Annexes I and V publish a coefficient per
seniority band instead of using the *gradații* at all. Those positions carry `ladder: null`
and seniority as a variant dimension. See `docs/DATA_QUALITY_COEFFICIENTS.md`.

**2. `countsToCap` cannot be a boolean.** Article 15(18) exempts the EU-funds supplement from
the 20% ceiling to the extent it is settled from external non-reimbursable funds; 15(19) puts
the co-financed part, paid from Title I, back in. The same supplement is partly inside and
partly outside the cap, in a proportion that depends on the project. Hence
`countsToCap: "partial"` plus `capSplit.countsWhen`.

**3. Values are dated.** Annex IX phases dignitary coefficients across 2026/2027 → 2031. The
Danish regulation factor is reissued twice a year. The Romanian reference value is set
annually by government decision. One primitive — `ValueSeries`, a number or a dated step
function — covers all three, and every engine call resolves it against an explicit `asOf`.

**4. Caps are plural and of three kinds.** Share of base (Art. 21(2), 20%; Art. 22(6), 4%),
share of headcount (Art. 22(7), 30% of posts), and a growth bound on the reference value
itself (Art. 9(4), capped by nominal GDP growth). Denmark has none, and that emptiness is a
finding rather than missing data.

## Scope, and why a payslip cannot show the cap

Article 21(2) measures the 20% ceiling **per ordonator principal de credite, per funding
source** — not per person. A single payslip cannot breach it, and cannot comply with it
either.

So `CapUtilisation.authoritative` is `false` whenever `cap.scope.level` is not `person`, and
the UI must label the figure as notional: *what the ratio would be if everyone in the
institution had this profile*. The real number only exists in `aggregate()`, over filled-post
counts.

## Provenance and confidence

Every number carries `{ source, locator, confidence }`.

- `verbatim` — copied from the source. A cell reference or an article number.
- `derived` — computed from the source, with the formula in `note`.
- `assumed` — not in any source document. Romanian tax rates are currently `assumed`: they
  come from the Fiscal Code, which is not in `sources/`.

`scripts/validate_data.py` refuses to let a regime with `status: "in-force"` carry any
`assumed` provenance. Drafts and comparators may, so the gap stays visible instead of
blocking work.

## Limitations are data

Each regime carries `limitations[]`, keyed to the output field it affects. The Romanian one
declares seven, of which two are `blocking`:

- **Article 33's transitional pay difference** pegs everyone to their November 2026 income and
  enters the base for everything else. It needs individual November 2026 pay, which Romania
  does not publish. Every Romanian total here is a floor, not a forecast.
- **The two seniority mechanisms** contradict each other for teaching and judicial staff.

Danish net pay is `null`, not zero and not estimated: IDA's tables carry no tax schedule.

This is the reason limitations live in the data rather than in a README. A caveat that sits in
documentation gets separated from the number on its way to a screenshot.

## Position assimilation

Article 37 abrogates Law 153/2017; Article 32 requires everyone to be reassigned to a position
in the new annexes, and where their post no longer exists, to one chosen "according to duties
and conditions of appointment". The law mandates the exercise and publishes no mapping. Each
*ordonator* decides, so the same former title can land differently in two institutions.

The model separates two things that look alike:

**Within a regime** — `position.titles[]`. About a quarter of coded rows merge several former
titles onto one code and one coefficient. That merge is a fact of the source cell, so it lives
in the regime, together with `assimilation.rawTitleCell` verbatim and a `parse` field saying
how much to trust the split.

**Between regimes** — `data/crosswalks/`. A separate document with its own provenance and its
own `authority`, which for the Romanian assimilation can be `reconstructed` at best, never
`published`. A regime never depends on another regime to be read; deleting a crosswalk never
changes what a law says.

Links are typed by cardinality — `identity`, `rename`, `merge`, `split`, `regrade`, `new`,
`abolished` — because a nine-to-one merge and a rename are different claims about the world.
`abolished` matters most: a former title with no destination.

`resolvePosition()` returns *candidates*, never a single silently chosen answer. Assimilation
is many-to-one, so forward is usually determinate and backward usually is not; an ambiguous
resolution reaches the UI as several priced outcomes. Merges used in aggregation require
`weight` on each endpoint — collapsing nine titles into one position only yields an honest
wage-bill delta if the nine headcounts are weighted, and where weights are missing the engine
refuses to aggregate rather than assuming an even split.

## Comparing with Denmark

Levels are never compared. RON and DKK amounts are not placed side by side anywhere, and the
Danish regime carries a `blocking` limitation saying so.

What is compared is shape: the form of the seniority ladder, how much of pay is base versus
supplement, dispersion within a band, who sets the number — statute, government decision,
institution head, or local negotiation — and how far apart the extremes sit.

Even that needs a caveat the app states rather than buries: the Danish figures are the
*agreed floor*. Qualification, function and performance supplements are negotiated locally and
appear in no table, so measured Danish dispersion is understated against Romanian dispersion,
where the statute is nearly the whole story.
