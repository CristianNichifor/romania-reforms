/**
 * The source and as-of under every chart (ux-guidelines § 4; backlog § 9 item 8).
 *
 * The page's header already says "Date: <sursă>, <an>" for the whole page, but the charts
 * come from two documents with two periods: the portal snapshot and the CSM annual reports.
 * A reader quoting one chart needs its own line, so every chart section carries a caption
 * read from the document that fed it. The markup holds only empty `data-source` paragraphs;
 * the words come from the data, like the header line, so a caption can never disagree with
 * the figures above it.
 */
import { dataLineFor } from './data-line';

export interface Sourced {
  publisher: string;
  period: string;
}

/** One line per source key, exactly the header's wording. */
export function chartCaptions(sources: Record<string, Sourced>): Record<string, string> {
  return Object.fromEntries(Object.entries(sources).map(([key, doc]) => [key, dataLineFor(doc)]));
}

/** The span of a set of annual editions, as a period: "2022-2025" for the data line to format. */
export function editionsPeriod(periods: string[]): string {
  const years = periods.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  if (!years.length) return '';
  return years[0] === years[years.length - 1] ? String(years[0]) : `${years[0]}-${years[years.length - 1]}`;
}

/** Writes each caption into every `[data-source="<key>"]` under `root`. Unknown keys stay empty and hidden. */
export function captionCharts(root: ParentNode, sources: Record<string, Sourced>): number {
  const captions = chartCaptions(sources);
  let written = 0;
  for (const node of root.querySelectorAll<HTMLElement>('[data-source]')) {
    const text = captions[node.dataset.source ?? ''];
    node.textContent = text ?? '';
    node.hidden = !text;
    if (text) written += 1;
  }
  return written;
}
