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
**255 companies have under 20 employees** and are candidates for absorption or liquidation
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

Two limitations travel with every number:

- **Headcount is a lower bound.** Only 698 of 1 247 companies report a usable full-time-equivalent
  headcount, so every employee total is over what the register contains, never an estimate. One
  reported value is excluded as an entry error and named in the data's `dataQuality` section:
  *Utilități și Servicii Publice Murighiol SRL* reports 10 776 employees in 2023 and none in the
  four years before, in a commune of about 3 000 inhabitants.
- **There is no geography.** The source gives no county per company, so the scenario counts
  regional operators, it does not place them on a map.

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
