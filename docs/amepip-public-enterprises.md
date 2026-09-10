# AMEPIP public enterprise data reconnaissance

AMEPIP is a useful shared-data family, but it should enter through official report
attachments rather than the embedded dashboard. The source inventory found CUI-level rows in
several PDFs, so the family can move from candidate to planned. The public Power BI dashboard
still needs an explicit export/API and reuse path before it can be a source of truth.

## Decision

Treat AMEPIP/public-enterprise data as a `planned` shared dataset.

Do not import rows into simulator payloads until the next slice preserves:

- a stable enterprise identifier exists, preferably CUI;
- the row-level file path is official or explicitly documented;
- the source URL, retrieval date, dashboard/report vintage, checksum and reuse limitation can
  be carried beside the rows;
- aggregates can be reconciled against another official source where financial indicators are
  reused.

## Sources checked

| Source | URL | Useful data | Current use |
| --- | --- | --- | --- |
| AMEPIP dashboard | <https://amepip.gov.ro/en/tablou-de-bord/> | Embedded Power BI dashboard for public enterprises. AMEPIP pages describe financial, non-financial and corporate-governance indicators. | Candidate source; not an importer source until export and reuse terms are explicit. |
| KPI evaluation report | <https://amepip.gov.ro/raport-evaluare-kpi/> | 2024 public-enterprise evaluation report and annexes for central/local financial and non-financial indicators, plus listing-readiness recommendations. | Best first target for source-shape review because the annexes are named release artifacts. |
| CA/CS indemnities | <https://amepip.gov.ro/indemnizatii-ca-cs/> | Monthly board, supervisory-board and director compensation reports. | Candidate for public-pay comparisons if enterprise keys are stable. |
| Companiile de stat API | <https://companiidestat.ro/date/> | Documented read-only JSON API with CUI-keyed company files, financials, salaries, subsidies and AMEPIP-derived fields. | Comparison/reference source under CC BY 4.0; official AMEPIP/MFin attachments remain source of truth for imports. |
| AMEPIP presentation | <https://amepip.gov.ro/prezentare/> | Institutional scope: AMEPIP collects, monitors and publishes financial and non-financial performance results of public enterprises. | Context only. |
| Dashboard announcement | <https://amepip.gov.ro/tablou-de-bord-pentru-a-monitorizarea-indicatorilor-cheie-de-performanta-ai-companiilor-de-stat/> | Describes dashboard coverage and states that financial indicators come from Ministry of Finance data. | Context and validation hint. |

## Source inventory

Committed inventory:
`packages/public_enterprise_governance/data/amepip-source-inventory-2025-2026.json`.

Inspected on 2026-09-10:

| Source family | Documents | Row-level CUI | Useful result |
| --- | ---: | --- | --- |
| KPI report and addendum | 2 | No | Methodology/context only. |
| KPI Annex 1, central financial indicators | 1 | Yes | 170 company indicator blocks with CUI/APT/year/indicator fields. |
| KPI Annex 2, central non-financial indicators | 1 | Yes | 170 company indicator blocks with CUI/APT/year/governance/ESG fields. |
| KPI Annex 3, local financial indicators | 1 | Yes | 1,212 local-company indicator blocks with CUI/APT/year/indicator fields. |
| Listing Annex 4 | 1 | Yes | About 208 CUI-level listing-readiness rows. |
| Listing Annexes 5-6 | 2 | No visible CUI | Recommendation context only until joined through an official CUI crosswalk. |
| CA/CS compensation reports | 2 | Yes | July has about 139 enterprise rows; August parses to 833 nominal/person rows. |

Decision: use the August 2025 nominal central-enterprise compensation report as the first
parser target because it directly supports the `salarizare` public-pay comparison and has CUI,
APT, enterprise, person, role and fixed/variable compensation fields.

## Beneficial fields

- Enterprise identity: CUI, name, authority, ownership level, central/local classification.
- Financial performance: revenue, profit/loss, debt, arrears, subsidies, assets, equity and
  profitability indicators.
- Governance: board size, board/supervisory/director indemnities, mandate state, listed-company
  governance indicators.
- Non-financial performance: service/output indicators, ESG indicators and employee counts if
  published with enterprise identity.
- Listing/readiness: flags or recommendations from AMEPIP KPI annexes for enterprises that meet
  market-admission or financial-listing criteria.

## Why it belongs in shared data

This source family could serve more than one simulator:

- `salarizare`: compare public-enterprise board/director compensation against public-pay reform
  assumptions.
- `achizitii-deschise`: connect public enterprise buyers or suppliers to ownership/governance
  and fiscal-risk context.
- `local-finance`: identify local public enterprises that may shift fiscal pressure outside the
  local-authority budget line.

## First implementation slice

1. Done: inventory downloadable report/annex files from the KPI and indemnity pages.
2. Done: record file type, source URLs, SHA-256 hashes, row estimates, available identifiers
   and visible license/reuse limitations.
3. Done: decide that CUI-level PDFs justify moving the dataset to `planned`.
4. Done: build a small parser for the August 2025 nominal compensation PDF source. The
   committed sample keeps 50 rows and summary metrics over all 833 parsed source rows.
5. Done: define the full mart schema, release-asset policy and `salarizare` consumer contract.
   The importer can generate the full mart, but the generated row-level file stays out of git.
6. Done: build `public-enterprise-administrative-footprint-2024-2026`, a release-asset-backed
   authority/UAT/county aggregate from the documented companiidestat.ro API. This is a
   comparison/reference layer under CC BY 4.0 attribution, not a replacement for official
   AMEPIP/MFin provenance.
7. Done: expose the aggregate in `administrativ` through `public-enterprise-footprint.json`,
   aligned to the browser UAT index and containing only numeric arrays and summary metadata.
   The app does not load company, CUI or person rows.
8. Done: keep the full package aggregate out of git as a checksum-pinned `data-v1` release
   asset; keep the compact `administrativ` sidecar committed because it is the app payload.
9. Next: rebuild the same administrative footprint contract from official AMEPIP annexes and
   MFin/data.gov.ro statements, using companiidestat.ro as validation/discovery instead of
   primary source.
10. Later: publish the compensation mart as a checksum-pinned release asset only when a compact
   `salarizare` comparison payload is ready to consume it without loading nominal rows in the
   browser.

The slice should not scrape opaque Power BI internals as the source of truth. If Power BI is the
only row-level route, require a documented export/API path before adoption.

`companiidestat.ro` can accelerate validation because it exposes a documented public API over
CUI rosters, AMEPIP-derived fields, MFin financials and subsidies. The administrative footprint
slice ingests it only as a labelled comparison/reference aggregate, with `sourceUrl`, hashes,
retrieval date, `license=CC BY 4.0` and attribution carried in the output. Official AMEPIP and
MFin files remain the target source of truth for a future replacement import.
