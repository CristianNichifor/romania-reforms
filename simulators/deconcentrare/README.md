# Deconcentrare — the state's county offices, on the eight development regions

The territorial deconcentrated services — a labour inspectorate, a public-health directorate, an
employment agency, a pension house, an agricultural payments centre — are still organised on the
county map, **one office per county per family**. There are **919** of them in the combined
evidence: 601 from the ANFP 2025 register, 318 complemented from the MFin portal list of public
entities.

This simulator applies to that layer the same move `justitie`'s `curti-apel-regiuni` variant
applies to the appellate courts: **one office per family per development region, eight instead of
forty-one.**

> **This is a tool for public debate, not an official proposal.** It counts offices, not
> decisions. It does not represent a government position.

## The headline

Of the 919 deconcentrated offices in evidence (ANFP + MFin portal):

| | offices |
| --- | ---: |
| in the 24 families proposed for regionalisation | **820** |
| after the merge, on eight regions | **179** |
| reduction | **78,2%** |
| already regional (finance, forestry, consumer protection, border police) | 23 |
| municipal, excluded | 9 |
| national / special, untouched (incl. the 42 prefects) | 67 |

The largest families are replicated in every county and collapse to eight: health insurance
(42→8), labour inspection (42→8), employment (41→8), social payments (41→8), agricultural
payments (41→8), public health (41→8), culture (41→8), agriculture (41→8), pensions (41→8),
statistics (41→8), sport (41→8), veterinary (42→8) — and now the police (39→8), ambulance
(40→8), ISU (38→8), school inspectorates (41→8), OCPI (41→8), DGASPC (40→8) and OSPA (24→8)
from the portal complement.

## Two sources, one scope field

The source here is the **ANFP list of institutions that manage public functions**, published
every year on [data.gov.ro](https://data.gov.ro). The 2025 edition is a clean four-column export
and — the reason it is usable — its own `TipInstitutie` column separates the central
administration from the **territorial deconcentrated services**. That classification is the
source's, not ours.

ANFP lists institutions managing **public functions**, so services with contractual staff appear
incompletely. The complement is the **MFin portal list of public entities** (snapshot
01.07.2026), imported by `import_portal_ep.py`: every family carries a `sources` field that
separates ANFP rows from portal rows, and a portal row for a (family, county) ANFP already
covers is dropped as a duplicate, not counted twice. Even together, the two sources lack the
county environment agencies, the ANPC/GNM county commissariats, the ANIF units and the ANAR
county systems — **the real number of offices to merge is higher, not lower.** What exactly is
missing, counted family by family: [`docs/coverage-gap.md`](docs/coverage-gap.md).

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
scripts/import_portal_ep.py     reads sources/lista-ep-portal-2026.csv.gz -> data/portal-ep-2026.json
scripts/build_deconcentrare.py  families x county x region, two sources -> data/deconcentrare.json
schema/                         JSON Schemas for all documents
sources/                        the ANFP 2025 export and the portal conversion, checksummed
data/                           generated, reproducible
docs/METHODOLOGY.md             the family table and the reconciliation
```

## Build

```sh
uv run python scripts/import_anfp.py
uv run python scripts/import_portal_ep.py
uv run python scripts/build_deconcentrare.py
uv run python scripts/validate_data.py
uv run pytest tests/test_deconcentrare.py
```

The build is deterministic: same source, byte-identical output.
