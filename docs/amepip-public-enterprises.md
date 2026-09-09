# AMEPIP public enterprise data reconnaissance

AMEPIP is a useful next shared-data candidate, but it should start as reconnaissance rather
than an importer. The public pages point to high-value public-enterprise data, while the main
dashboard is an embedded Power BI report whose row-level export, stable keys and reuse terms
still need to be documented.

## Decision

Treat AMEPIP/public-enterprise data as a `candidate` shared dataset.

Do not import rows into simulator payloads until the next slice proves:

- a stable enterprise identifier exists, preferably CUI;
- the row-level export path is official or explicitly documented;
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
| AMEPIP presentation | <https://amepip.gov.ro/prezentare/> | Institutional scope: AMEPIP collects, monitors and publishes financial and non-financial performance results of public enterprises. | Context only. |
| Dashboard announcement | <https://amepip.gov.ro/tablou-de-bord-pentru-a-monitorizarea-indicatorilor-cheie-de-performanta-ai-companiilor-de-stat/> | Describes dashboard coverage and states that financial indicators come from Ministry of Finance data. | Context and validation hint. |

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

1. Inventory downloadable report/annex files from the KPI and indemnity pages.
2. Record file type, sheet/table names, row counts, available identifiers and visible license or
   reuse text.
3. Build a tiny sample parser only if at least one source exposes row-level enterprise identity.
4. Validate CUI/name coverage against a second official source when financial fields are reused.
5. Decide whether the dataset moves from `candidate` to `planned`, or remains deferred because
   the public surface is aggregate-only or lacks reusable row-level provenance.

The slice should not scrape opaque Power BI internals as the source of truth. If Power BI is the
only row-level route, require a documented export/API path before adoption.
