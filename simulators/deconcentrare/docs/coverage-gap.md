# Deconcentrated coverage — what ANFP does not list, and where to get it

The ANFP 2025 register lists institutions that manage **public functions**. Several
deconcentrated families whose staff are largely contractual appear incomplete or absent. This
documents the gap with numbers from the imported register itself, the sources checked, and the
decision on when an import becomes worth building. It is the data question behind the
`anfp-scope` limitation that travels with `deconcentrare.json`.

## What is missing, counted

Families present in the 2009–2010 snapshot of the *Registrul Național al Instituțiilor Publice*
in 20–41 counties, against their presence in ANFP 2025:

| Family | 2010 snapshot | ANFP 2025 | Note |
| --- | ---: | ---: | --- |
| Agenția pentru Protecția Mediului (APM) | 33 counties | **14** | the biggest undercount; APM staff are largely contractual |
| Comisariatele județene pentru protecția consumatorilor (ANPC) | 22 counties | **1** regional commissariat | only the regional Centru unit appears |
| Garda Națională de Mediu — comisariate județene | 23 counties | **0** | only the central institution appears |
| Oficiul de Cadastru și Publicitate Imobiliară (OCPI) | 40 counties | **0** | entirely absent |
| Agenția Națională de Îmbunătățiri Funciare (ANIF) | 33 counties | **0** | entirely absent |
| Oficiile de ameliorare și reproducție în zootehnie | 33 counties | **0** | entirely absent |
| Administrația Națională Apele Române — sisteme județene | ~40 | **0** | entirely absent |

The 601 offices counted in `deconcentrare.json` are therefore a **lower bound on the structure,
not on the argument**: the missing families are county-replicated like the counted ones, so the
real number of offices that a regionalisation would close is larger, not smaller.

## Sources checked

| Source | Status |
| --- | --- |
| ANFP register, data.gov.ro (XLSX, updated Feb 2026) | adopted — the current source of truth for public-function institutions |
| anpm.ro — county agencies list | unreachable from this session; the site also has no documented machine-readable list. Checked as a candidate, not adopted. |
| anpc.ro — county commissariats | same: HTML only, no stable export. Candidate. |
| MFin register of public institutions (buget) | candidate; the definitive source would be the Ministry of Finance list of budget-funded institutions, which includes contractual-staff services. Needs a stable, attributable export before it can feed an importer. |
| MMSC / MADR subordination lists (ministerial sites) | candidate per family; scattered, so only worth it once a consumer question needs one family. |

## Decision

Do not build a complement importer yet. The current register is internally consistent, carries
its scope limit as a `material` limitation on every consumer, and the missing families would
have to be scraped one by one from sources with no stable export — a fragile pipeline that
would quietly rot, which is worse than a declared gap.

Build the complement when one of these is true:

- a **row-level, attributable export** appears (MFin list with CUI per territorial unit, or a
  data.gov.ro dataset per family); then import it as a second source with its own provenance
  and a `sourceScope` field, so totals distinguish ANFP-covered from complemented rows rather
  than mixing them;
- a **consumer question** needs one specific family (e.g., what regionalising the 42 OCPI
  offices would save), in which case that family alone is worth the ministerial-site import.

Until then, the honest statement is the one the simulator already makes: *the real number of
offices to merge is higher, not lower.*
