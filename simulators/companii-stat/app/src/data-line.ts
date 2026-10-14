/**
 * The "Date: <sursă>, <an>" line under the H1 (UX-5).
 *
 * Source and year are read from the document the page loads, so a caption can never disagree
 * with the figures under it; the markup only holds the empty paragraph.
 */
export function dataLine(source: string, period: string): string {
  return `Date: ${source}, ${period.replace(/(\d{4})-(\d{4})/, '$1–$2')}`;
}

export function dataLineFor(doc: { period: string }): string {
  return dataLine('Ministerul Finanțelor, situațiile financiare ale companiilor de stat', doc.period);
}
