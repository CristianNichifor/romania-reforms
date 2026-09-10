# companii-stat — methodology

## 1. What is imported

From `sources/companii-stat-finnefin.xlsx`:

- `Indicatori calculati` — identity (`company_id`, `cui`, `company`, `registration_number`),
  activity (`CAEN(ONRC)`), `status`, and the year rows used only to establish the latest year.
- `Indicatori formular` — the full-time-equivalent headcount, `Număr de angajați cu echivalent
  normă întreagă`, taken at the **latest year each company reports it**.

One row per company. The ratio columns (ROA, ROE, leverage, …) are dropped: a consolidation
argument is about how many operators exist, not about their returns.

## 2. Clustering

Companies are grouped by the first four digits of `CAEN(ONRC)`. A company with no CAEN falls into
`????`. The cluster carries: company count, summed headcount over the companies that report one,
how many report one, and how many are micro (under 20 employees).

## 3. The regional scenario

The same rule as `deconcentrare`: **one operator per development region** for the network
utilities whose service area is a region or a basin.

| CAEN | activity | tier | companies | proposed |
| --- | --- | --- | ---: | ---: |
| 3600 | Captarea, tratarea și distribuția apei | regional | 295 | 8 |
| 3811 | Colectarea deșeurilor nepericuloase | regional | 139 | 8 |
| 8130 | Activități de întreținere peisagistică | regional | 84 | 8 |
| 0210 | Silvicultură și alte activități forestiere | regional | 53 | 8 |
| 4211 | Lucrări de construcții a drumurilor și autostrăzilor | regional | 50 | 8 |
| 3530 | Furnizarea de abur și aer condiționat | regional | 27 | 8 |
| 3700 | Colectarea și epurarea apelor uzate | regional | 11 | 8 |
| 4931 | Transporturi urbane de călători | local | 56 | 56 |
| 3511 | Producția de energie electrică | national | 22 | 22 |
| 2540 | Fabricarea armamentului și muniției | national | 14 | 14 |
| 5223 | Servicii anexe transporturilor aeriene | national | 19 | 19 |

Everything not listed is `other` and is reported, not merged.

**This table is a policy judgement, not a fact in the source.** It is marked `assumed` in
provenance and confined to one editable list. The test suite pins the parts that are not a
choice: the clusters must rebuild the company count, the headcount must stay a lower bound, and
electricity, weapons and airports must not be swept into regions.

## 4. Reconciliation

```
1 247 companies across 146 CAEN clusters
  659 of them in the 7 regional clusters        -> 56 regional operators (-91,5%)
  255 micro companies (under 20 employees)      -> candidates regardless of the rule
  699 report a headcount                        -> all employee sums are lower bounds
```

`sum(cluster.companies) == summary.companies` and the reduction recomputation are tests.

## 5. What this cannot say

- **No geography.** The source has no county per company; the scenario counts operators, it does
  not site them. A company may already be a de-facto regional operator and still be counted as a
  separate entity here.
- **Headcount is partial**, so employee totals understate the workforce and cannot support a
  cost or redundancy figure.
- **CAEN is the registered activity**, not necessarily what the company does today; dormant
  companies with a live status are counted.
- **Ownership and subsidy are not modelled.** The workbook is a portfolio of state companies; it
  does not say which are profitable, which are subsidised, or which are already in a merger.
