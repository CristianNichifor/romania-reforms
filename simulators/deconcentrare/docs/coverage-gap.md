# Deconcentrated coverage — what the two sources together still do not list

The evidence now runs on **two sources**: the ANFP 2025 register (public functions) and the
MFin portal list of public entities (snapshot 01.07.2026, the `portal` scope on every family).
This documents what remains missing even after the complement, and how the complement was
built. It is the data question behind the `anfp-scope` and `portal-scope` limitations that
travel with `deconcentrare.json`.

## What the portal complement added

| Family | portal rows | note |
| --- | ---: | --- |
| Poliția județeană | 39 | county inspectorates; the 5 border-police inspectorates are reported as already regional |
| Serviciul de ambulanță | 40 | |
| ISU | 38 | the portal lists fewer than one per county |
| Inspectoratul școlar | 41 | |
| OCPI | 41 | entirely absent from ANFP |
| DGASPC | 40 | sector rows excluded as municipal |
| OSPA | 24 | |
| Jandarmeria județeană | 8 | only the inspectorates, not the mobile groupings |
| Instituția prefectului | 42 | reported as special — the prefect stays |

Rows for families ANFP already covers (DSV, forest guards, regional finance) are deduplicated
per (family, county): 54 portal rows dropped as duplicates of ANFP offices, never counted twice.

## What is still missing from both sources

Families present in the 2009–2010 snapshot of the *Registrul Național al Instituțiilor Publice*
in 20–41 counties, against their presence in ANFP 2025 **and** in the MFin portal:

| Family | ANFP 2025 | portal 2026 | Note |
| --- | ---: | ---: | --- |
| Agenția pentru Protecția Mediului (APM) | 14 | **0** | county agencies absent from both; only the national agency appears |
| Comisariatele județene ANPC | 1 | **0** | only central/regional units appear |
| Garda Națională de Mediu — comisariate județene | 0 | **0** | only the central institution appears |
| Oficiul de Cadastru (OCPI) | 0 | **41** | resolved by the complement |
| Agenția Națională de Îmbunătățiri Funciare (ANIF) | 0 | **0** | only the central agency appears |
| Oficiile de ameliorare și reproducție în zootehnie | 0 | **0** | entirely absent |
| Apele Române — sisteme județene | 0 | **0** | only the basin administrations appear |

The 919 offices counted in `deconcentrare.json` are therefore still a **lower bound on the
structure, not on the argument**: the missing families are county-replicated like the counted
ones, so the real number of offices that a regionalisation would close is larger, not smaller.

## Sources checked

| Source | Status |
| --- | --- |
| ANFP register, data.gov.ro (XLSX, updated Feb 2026) | adopted — public-function institutions |
| MFin portal, „Lista entităților publice” (XLS, 01.07.2026) | adopted — the complement; committed as a converted csv.gz with the original's SHA-256 recorded |
| gov.ro — institutions list | central institutions only; not a row-level source |
| Wikipedia list of institutions under the Government | uncited; background only |
| firme-on-line.ro | third-party directory; not attributable |
| anpm.ro / anpc.ro county lists | HTML only, no stable export — still not adopted |

## Decision

The complement is built, as this file's original decision prescribed: a second source with its
own provenance and a `sourceScope` per family (`sources.anfp` / `sources.portal`), so totals
distinguish ANFP-covered from complemented rows. The remaining five families (APM, ANPC, GNM,
ANIF county units, ANAR county systems, zootehnie) still lack any row-level, attributable
export — each is a small ministerial-site list, and the honest statement stays the one the
simulator already makes: *the real number of offices to merge is higher, not lower.*
