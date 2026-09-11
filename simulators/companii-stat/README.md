# companii-stat — the state's companies, by activity

The state does not own one company portfolio. It owns a few hundred water operators, a
hundred-plus waste operators, dozens of landscaping firms, thermal plants and road builders,
each in its own commune, town or county — and beside them the strategic national holdings
(electricity, weapons, airports) that are a different argument.

This groups the **1 247 companies** in the indicator workbook by four-digit CAEN and applies the
rule `deconcentrare` applies to the deconcentrated services: for the **network utilities whose
service area is a region or a basin**, one operator per development region.

> **This is a tool for public debate, not an official proposal.** Which activities count as
> regionalisable is a policy judgement, marked `assumed`; the counts are from the source.

## The headline

| | companies | → | proposed |
| --- | ---: | ---: | ---: |
| Water (3600) | 295 | → | 8 |
| Waste (3811) | 139 | → | 8 |
| Landscaping (8130) | 84 | → | 8 |
| Forestry (0210) | 53 | → | 8 |
| Roads (4211) | 50 | → | 8 |
| Thermal (3530) | 27 | → | 8 |
| Wastewater (3700) | 11 | → | 8 |
| **7 regional clusters** | **659** | → | **56** |

A **91,5%** reduction in the number of operating entities in those seven activities. Separately,
**561 companies have under 20 employees** and are candidates for absorption or liquidation
regardless of the regional rule.

## What stays out

The tier table is one editable list in `build_companii_stat.py`:

- **national** — electricity (22), weapons (14), airports (19). Consolidating these is a
  different argument, not a regional one.
- **local** — urban transport (56). A city service, not a basin.
- **other** — building administration, construction, cleaning, real estate, security: reported,
  not merged.

## The source, and its two limits

The workbook (`datecompanii_ind-finnefin.xlsx`) has three sheets: financial ratios per company
and year (2019–2024), non-financial indicators, and the KPI dictionary. This simulator keeps
identity, CAEN, status and **headcount**; the ratios are dropped.

The key limitations travel with every number:

- **Headcount and financials are official-first, lower bounds still.** The headcount comes
  first from the MFin 2025 statements (via the documented companiidestat.ro API, CC BY 4.0),
  and only where MFin has no row, from the workbook form — 1 107 of 1 247 companies end up with
  a headcount. Revenue, net result and debt cover the companies MFin has a row for; totals over
  them are lower bounds. One workbook value stays excluded as an entry error and is named in the
  data's `dataQuality` section: *Utilități și Servicii Publice Murighiol SRL* reports 10 776
  employees in 2023 and none in the four years before, in a commune of about 3 000 inhabitants —
  the MFin statement for the same company reads 14, and that official figure stands.
- **County is registration geography, not service geography.** The companiidestat.ro registry
  carries a county for every company, and the regional operator lists use it to group companies
  by development region. That county is the registered seat, not necessarily the service area,
  so the grouping remains a policy approximation rather than a map of infrastructure.
- **Owner, subsidy and financial joins are partial.** Owners come from AMEPIP Anexa 3; subsidies
  come from the SFA annexes; financials come from MFin 2025 statements. Missing rows stay missing
  and totals over those fields are lower bounds.

## Layout

```
scripts/import_soe.py             workbook -> data/companii-2025.json (identity, CAEN, headcount)
scripts/build_companii_stat.py    clusters + regional scenario -> data/companii-stat.json
schema/                           JSON Schemas for both documents
sources/                          the workbook, checksummed
data/                             generated, reproducible
docs/METHODOLOGY.md               the tier table and the reconciliation
```

## Build

```sh
uv run python scripts/import_soe.py
uv run python scripts/build_companii_stat.py
uv run python scripts/validate_data.py
uv run pytest tests/test_companii_stat.py
```
