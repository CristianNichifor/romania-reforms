# Deconcentrare — the state's county offices, on the eight development regions

The territorial deconcentrated services — a labour inspectorate, a public-health directorate, an
employment agency, a pension house, an agricultural payments centre — are still organised on the
county map, **one office per county per family**. There are **601** of them in the 2025 register.

This simulator applies to that layer the same move `justitie`'s `curti-apel-regiuni` variant
applies to the appellate courts: **one office per family per development region, eight instead of
forty-one.**

> **This is a tool for public debate, not an official proposal.** It counts offices, not
> decisions. It does not represent a government position.

## The headline

Of the 601 deconcentrated offices in the ANFP 2025 register:

| | offices |
| --- | ---: |
| in the 16 families proposed for regionalisation | **549** |
| after the merge, on eight regions | **117** |
| reduction | **78,7%** |
| already regional (finance, forestry, consumer protection) | 43 |
| municipal, excluded | 9 |
| national / special, untouched | 18 |

The largest families are replicated in every county and collapse to eight: health insurance
(42→8), labour inspection (42→8), employment (41→8), social payments (41→8), agricultural
payments (41→8), public health (41→8), culture (41→8), agriculture (41→8), pensions (41→8),
statistics (41→8), sport (41→8), veterinary (42→8).

## The source is not the registry that circulates

The file known as *Registrul Național al Instituțiilor Publice* is a **2009–2010 snapshot**. It
still names `Ministerul Dezvoltării Regionale și Locuinței` (2008–2010), the `Autoritatea
Națională a Vămilor` (pre-2011), the `Garda Financiară` (pre-2013) and the `Autoritatea pentru
Străini` (pre-2010). A reform proposal built on it would be attacked on the vintage before the
argument was heard.

The source here is the **ANFP list of institutions that manage public functions**, published
every year on [data.gov.ro](https://data.gov.ro). The 2025 edition is a clean four-column export
and — the reason it is usable — its own `TipInstitutie` column separates the central
administration from the **territorial deconcentrated services**. That classification is the
source's, not ours.

It has one scope limit that matters: ANFP lists institutions managing **public functions**, so
services with contractual staff appear incompletely — 14 environment agencies and a single
consumer-protection commissariat, where the county structure is larger. **The real number of
offices to merge is higher, not lower.**

## The rule, in a paragraph

Every service whose name begins with one of the sixteen family prefixes in the build script is
grouped by the county it sits in. Each county is mapped to its development region — **read from
the map `justitie` already derived from `regions.geojson`, not re-entered here** — and the family
gets one office per region it reaches. Families already organised on regions (the eight regional
finance directorates, the forest guards, the regional consumer-protection commissariats) are
reported but not merged; municipal services (Bucharest and the sectors) are excluded and named.
Families are matched by an **explicit table, not fuzzy matching**, because the source spells the
same service several ways; every unmatched name is listed rather than dropped.

## Layout

```
scripts/import_anfp.py          reads sources/anfp-institutii-2025.xlsx -> data/institutii-2025.json
scripts/build_deconcentrare.py  families x county x region -> data/deconcentrare.json
schema/                         JSON Schemas for both documents
sources/                        the ANFP 2025 export, checksummed
data/                           generated, reproducible
docs/METHODOLOGY.md             the family table and the reconciliation
```

## Build

```sh
uv run python scripts/import_anfp.py
uv run python scripts/build_deconcentrare.py
uv run python scripts/validate_data.py
uv run pytest tests/test_deconcentrare.py
```

The build is deterministic: same source, byte-identical output.
