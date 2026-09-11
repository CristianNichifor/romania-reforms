# deconcentrare — methodology

## 1. What is counted

Every row of the ANFP 2025 register whose `TipInstitutie` starts with
`TERITORIAL - SERVICIU PUBLIC DECONCENTRAT`. In 2025 that is **601 rows**. Those rows are
complemented by **318 kept rows** from the MFin portal list of public entities, after dropping
portal rows for a `(family, county)` pair ANFP already covers. The combined evidence counts
**919 offices**.

Each row is assigned to a **family** by an explicit prefix table in
`scripts/build_deconcentrare.py` — not by fuzzy matching, because the sources write the same
service several ways (`DIRECȚIA SANITAR-VETERINARĂ`, `... SANITAR -VETERINARĂ`,
`... SANITAR- VETERINARĂ`). A fuzzy matcher would fix those and quietly merge others. Every
unmatched source name is written to the relevant quality list and counted; tests make a source
refresh that adds a family surface instead of dropping rows.

A name containing `MUNICIPAL`, `MUNICIPIULUI` or `SECTOR` is **excluded**: Bucharest and the
sectors do not regionalise through a county. Those nine names are listed in `municipalNames`.

## 2. The families

| family | tier | offices today | proposed | regions reached |
| --- | --- | ---: | ---: | ---: |
| Casa de Asigurări de Sănătate | regional | 42 | 8 | 8 |
| Inspectoratul Teritorial de Muncă | regional | 42 | 8 | 8 |
| Agenția Județeană pentru Ocuparea Forței de Muncă | regional | 41 | 8 | 8 |
| Agenția Județeană pentru Plăți și Inspecție Socială | regional | 41 | 8 | 8 |
| APIA — Centrul Județean | regional | 41 | 8 | 8 |
| Direcția de Sănătate Publică | regional | 41 | 8 | 8 |
| Direcția Județeană pentru Cultură | regional | 41 | 8 | 8 |
| Direcția pentru Agricultură Județeană | regional | 41 | 8 | 8 |
| Casa Județeană de Pensii | regional | 41 | 8 | 8 |
| Direcția Județeană/Regională de Statistică | regional | 41 | 8 | 8 |
| Direcția Județeană de Sport și Tineret | regional | 41 | 8 | 8 |
| Direcția Sanitar-Veterinară și pentru Siguranța Alimentelor | regional | 42 | 8 | 8 |
| Inspectoratul Teritorial pentru Calitatea Semințelor | regional | 30 | 7 | 7 |
| Agenția pentru Protecția Mediului | regional | 14 | 6 | 6 |
| Direcția Județeană pentru Familie și Tineret | regional | 7 | 5 | 5 |
| Agenția pentru Întreprinderi Mici și Mijlocii și Turism | regional | 3 | 3 | 3 |
| Comisariatul Regional pentru Protecția Consumatorilor | regional-de-facto | 1 | 1 | 1 |
| Direcția Generală Regională a Finanțelor Publice | regional-de-facto | 8 | 8 | 8 |
| Garda Forestieră | regional-de-facto | 9 | 9 | 8 |
| Administrația Națională a Rezervelor de Stat și Probleme Speciale | special | 22 | 22 | 8 |
| Administrația Rezervației Biosferei Delta Dunării | special | 1 | 1 | 1 |
| Casa Asigurărilor de Sănătate a Apărării, Ordinii Publice și Siguranței Naționale | special | 1 | 1 | 1 |
| Centrul Național de Formare Profesională a Personalului ANOFM | special | 1 | 1 | 1 |
| Inspectoratul pentru Situații de Urgență | regional | 38 | 8 | 8 |
| Inspectoratul școlar județean | regional | 41 | 8 | 8 |
| Instituția prefectului | special | 42 | 42 | 8 |
| Oficiul de Studii Pedologice și Agrochimice | regional | 24 | 8 | 8 |
| Serviciul de ambulanță județean | regional | 40 | 8 | 8 |
| DGASPC — asistență socială și protecția copilului | regional | 40 | 8 | 8 |
| Oficiul de Cadastru și Publicitate Imobiliară | regional | 41 | 8 | 8 |
| Poliția județeană | regional | 39 | 8 | 8 |
| Poliția de Frontieră — inspectorate teritoriale | regional-de-facto | 5 | 5 | 4 |
| Jandarmeria județeană | regional | 8 | 6 | 6 |

Tiers:

- **regional** — one office per county today, proposed one per development region. These are the
  820 offices the headline reduces to 179.
- **regional-de-facto** — already organised on regions (finance, forestry, consumer protection).
  Reported for the total, not merged.
- **special** — national or territorial units that are not a county family (state reserves, the
  Danube Delta, military health insurance, the ANOFM training centre). Untouched.

## 3. The regions are `justitie`'s, not new ones

The county → region map is read from `simulators/justitie/data/curti-apel-regiuni.json`, which
`build_curti_apel.py` derived by polygonising `regions.geojson` and probing each boundary line.
That reproduces the composition of Legea 315/2004 — **2, 4, 5, 6, 6, 6, 6, 7 counties** — without
anyone typing it. This simulator does not re-derive it, because the argument is precisely that
one country is cut the same way for courts and for everything else; a second, independent map
could drift.

A test asserts the two sets of regions are identical, name for name.

## 4. Reconciliation

```
919  deconcentrated offices in evidence
−  9  municipal (Bucharest, sectors)          -> municipalNames
= 910 matched to a family                     -> summary.matchedOffices
      820 in the 24 regional families         -> reduced to 179
       90 already regional or special

ANFP-only baseline kept in summary.anfp:
601 total, 592 matched, 549 in regional families, 117 proposed.
```

`summary.matchedOffices + summary.municipalExcluded == summary.deconcentratedOfficesTotal` is a
test, so the headline cannot be quoted without the rows that build it.

## 5. What this cannot say

- **The seat of a merged directorate is not in the source.** The model counts offices, it does
  not place them on a map.
- **ANFP and MFin still miss families.** The portal complement fills police, ambulance, ISU,
  school inspectorates, OCPI, DGASPC, OSPA and some gendarmerie rows. County environment
  agencies, ANPC/GNM commissariats, ANIF units and ANAR county systems remain named coverage
  gaps. The true reduction is larger, not smaller.
- **Headcount is not modelled.** The register has no employee counts, so the merge is a count of
  offices, not of posts or cost.
- **Naming variants are grouped by rule.** The explicit table is auditable; the unmatched list
  is the check that it stays complete.
