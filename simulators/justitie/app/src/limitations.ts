// The data-limitations list on the statistics page: how each caveat's severity and summary read.

/** How a severity reads on the page (ux-guidelines § 3): the data keys are not Romanian. */
export const SEVERITY: Record<'blocking' | 'material' | 'note', string> = {
  blocking: 'blocant',
  material: 'important',
  note: 'de reținut',
};

/**
 * A caveat's first sentence, for its summary line, and what follows it.
 *
 * The summary used to be the caveat's id with its dashes turned to spaces ("portalul nu e
 * arhiva"): a data key, without diacritics. The first sentence is the caveat's own words, and
 * head + ' ' + rest is the original text, so nothing is reworded.
 */
export function lead(text: string): { head: string; rest: string } {
  const match = /^(.+?[.!?])\s+(?=[A-ZĂÂÎȘȚ„«(])/su.exec(text);
  if (!match) return { head: text, rest: '' };
  return { head: match[1] ?? text, rest: text.slice(match[0].length) };
}
