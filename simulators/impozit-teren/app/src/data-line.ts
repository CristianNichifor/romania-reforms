/**
 * The "Date: <sursă>, <an>" line under the H1 (UX-5).
 *
 * Source and year are read from the document the page loads, so a caption can never disagree
 * with the figures under it; the markup only holds the empty paragraph.
 */
export function dataLine(source: string, period: string): string {
  return `Date: ${source}, ${period.replace(/(\d{4})-(\d{4})/, '$1–$2')}`;
}

/** The fiscal code's period, then the span of notarial-guide years the counties are priced from. */
export function dataLineFor(code: { period: string }, guideYears: Record<string, string>): string {
  const years = [...new Set(Object.values(guideYears))].sort();
  const guides =
    years.length === 0
      ? ''
      : years.length === 1
        ? `; grile notariale ${years[0]}`
        : `; grile notariale ${years[0]}–${years[years.length - 1]}`;
  return `${dataLine('Codul fiscal (Legea 227/2015)', code.period)}${guides}`;
}
