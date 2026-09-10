# The eight-region rule — where the consolidation applies, and why

This is the shared policy context for three simulators in this repository: **`justitie`**
(courts and prosecutors), **`deconcentrare`** (the state's territorial services) and
**`companii-stat`** (state companies). It folds together the earlier strategy notes, the EU /
OECD benchmark, and the ecosystem synthesis into one document that stays current with what the
simulators actually model.

## 1. The rule

**One office or operator per family of services per development region — eight instead of
forty-one.** Romania already has eight NUTS2 development regions (Legea 315/2004: 2, 4, 5, 6, 6,
6, 6, 7 counties). They are statistical shells: no service is organised on them. Meanwhile the
state keeps one county office for every function, and one company per town for every utility.

The rule is not a territorial reform. It does not abolish counties, does not elect regions, and
does not touch what the constitution makes local. It moves the *state's own offices* onto the
map that already exists.

## 2. Where the rule already applies in this repository

| Layer | Today | On eight regions | Reduction |
| --- | ---: | ---: | ---: |
| Appellate courts (`curti-apel-regiuni` variant) | 15 | 8 | — |
| Prosecutor offices at the appellate tier | 15 | 8 | — |
| Deconcentrated services, 16 families (`deconcentrare`) | 549 | 117 | **78,7%** |
| Network utilities, 7 activities (`companii-stat`) | 659 | 56 | **91,5%** |
| Micro state companies (under 20 employees) | 255 | absorbed/liquidated | — |

The `deconcentrare` families: health insurance (42→8), labour inspection (42→8), employment
(41→8), social payments (41→8), agricultural payments (41→8), public health (41→8), culture
(41→8), agriculture (41→8), pensions (41→8), statistics (41→8), sport (41→8), veterinary (42→8),
seed quality (30→7), environment (14→6), family and youth (7→5), SMEs and tourism (3→3).

The `companii-stat` network activities: water (295→8), waste (139→8), landscaping (84→8),
forestry (53→8), roads (50→8), thermal (27→8), wastewater (11→8).

The source for the deconcentrated layer is the **ANFP 2025 register** on data.gov.ro, not the
fixed-width "Registrul Național al Instituțiilor Publice" that circulates — that file is a
2009–2010 snapshot. ANFP's scope limit matters: it lists institutions managing *public
functions*, so contractual-staff services are under-represented and the real reduction is
larger, not smaller.

## 3. What the benchmark shows

The EU/OECD comparison behind the strategy:

- **Ministries.** The efficient small and medium states run **11–14 mission-based ministries**
  (Sweden 11, Estonia 11, Netherlands 12, Finland 12, Latvia/Lithuania/Czechia/Hungary ~14).
  Romania has **18**; Poland's 27 is the cautionary outlier. Target: **13–15**, split by
  mission, not by sector lobby. Digitalisation belongs in a Government agency under the PM, not
  in a ministry.
- **The meso tier.** Three durable models: a strong elected region (Poland, France, Greece,
  Czechia, Italy, Spain), a deliberately thin tier (Lithuania abolished counties in 2010;
  Latvia and Estonia keep statistics-only regions), or a state-deconcentrated region (Hungary's
  *járás*, France's prefect, Poland's *voivode*). Romania's gap is the fourth option nobody
  copies: a statistical NUTS2 shell **with** 41 county replicas of every service still doing
  the work.
- **Municipalities.** Fragmentation is only ever broken by coercive, one-shot, statute-based
  mergers in a political window (Denmark 270→98, Greece 1 033→325, Estonia 213→79, Latvia
  119→43, Ireland 114→31). Voluntary schemes (Czechia, Slovakia) fail. Romania's 3 181 LAUs are
  modelled in `administrativ`, not here.
- **Agencies.** Sweden separates policy from ~200 delivery agencies; the UK's 2010–2015
  consolidation of arm's-length bodies and Slovakia's "Better State" agency mergers show that
  agency consolidation works even where territorial mergers are blocked. The lesson: merge
  *delivery* by market, keep *regulators* independent, share back-office, and run a standing
  review.

## 4. The recommended architecture (Option B — pragmatic)

1. **Keep the 41 counties** as NUTS3 and electoral units.
2. **Move all deconcentrated services to the 8 regions** — one regional directorate per family
   (this is what `deconcentrare` counts).
3. **Create a regional state representative** per region (the French prefect model) coordinating
   the eight regional directorates; county prefects become deputies.
4. **Consolidate the network utilities to one regional operator each** (`companii-stat`), and
   absorb or liquidate the micro companies.
5. **Cut ministries 18 → 13–15** by mission: Finance absorbs EU funds; Economy merges with
   Energy; Transport absorbs the infrastructure side of development; Agriculture merges with
   Environment, Water and Forests; Labour re-absorbs Family and Youth; Education absorbs
   Research; Culture absorbs Sport.
6. **Merge central agencies by market** — a single transport authority, a single health and food
   authority, a single social-benefits agency, a single cadastre and land agency — keeping the
   regulators (ANRE, ANCOM, ANPC, ASF and peers) legally independent.

Deliberately untouched: emergency services (ISU, ambulance), police and gendarmerie, justice
and prosecution (beyond the court map the judicial reform already proposes), defence, and the
independent regulators.

Sequencing, borrowing the best cases:

| Phase | Model | Action |
| --- | --- | --- |
| 0–1 yr | Slovakia | freeze new entities; agency/back-office consolidation; standing review |
| 1–3 yr | France/Poland | regionalise deconcentrated services into 8 regions (Option B) |
| 1–3 yr | — | water, waste, thermal and micro-SOEs to regional operators |
| 3–5 yr | Hungary | recentralise schools and hospitals where capacity is weak |
| 5–10 yr | Denmark/Greece | municipal mergers; counties become regional units (Option A, if the window opens) |
| continuous | Estonia | digital shared services and interoperability |

## 5. The hit list (highest impact, lowest political cost first)

| Priority | Action | Entities affected |
| --- | --- | ---: |
| 1 | Eight regional water operators | 295 → 8 |
| 2 | Eight regional waste operators | 139 → 8 |
| 3 | Absorb or liquidate micro companies (<20 employees) | 255 → ~0 |
| 4 | Regionalise the 16 deconcentrated families | 549 → 117 |
| 5 | Merge municipal markets and property companies | 88 → ~40 |
| 6 | Merge county road companies | 50 → 8 |
| 7 | Energy generation consolidation | 22 → ~6 |
| 8 | Regional airports holding | 19 → 4 |
| 9 | ROMARM subsidiaries into divisions | 14 → 3 |

## 6. Sources

- ANFP 2025 register of public-function institutions — data.gov.ro
- CSM, *Raport privind starea justiției* (courts and caseloads; `justitie`)
- State-company indicator workbook, 2019–2024 (`companii-stat`)
- Administrative divisions and reforms: Denmark 2007, Greece Kallikratis 2010, Estonia 2017,
  Latvia 2021, Ireland 2014, Poland 1999, France 2014, Lithuania 2010, Hungary 2013 — per the
  benchmark notes in the strategy source documents.
