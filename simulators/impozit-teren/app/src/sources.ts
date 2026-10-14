/**
 * Where each county's numbers come from, said beside the county (RR-8).
 *
 * The value of a county is its notarial guide applied to the 2014 land fund. Most chambers have
 * a 2026 guide; a few are still priced from an older one, and a table that printed them side by
 * side without saying so would compare prices two years apart as if they were the same market.
 * A county with no guide at all is valued by the national estimate, and says that too.
 */

/** County code (lower case) to the year of its notarial guide. */
export type GuideYears = Record<string, string>;

/** The newest `valoare-teren-<county>-<year>.json` per county, as copy-data.mjs picks it. */
export function guideYearsFrom(names: readonly string[]): GuideYears {
  const years: GuideYears = {};
  for (const name of [...names].sort()) {
    const match = /^valoare-teren-([a-z]{1,2})-(\d{4})\.json$/.exec(name);
    if (match) years[match[1]!] = match[2]!;
  }
  return years;
}

/** Counties the national estimate values without a guide of their own. */
export function estimatedCounties(
  national: { counties_valued: Array<{ county: string; basis: string }> } | null,
): Set<string> {
  return new Set(
    (national?.counties_valued ?? [])
      .filter((row) => row.basis === 'predicted')
      .map((row) => row.county.toLowerCase()),
  );
}

/** The guide year, flagged when older than the newest guide, and the estimate badge. */
export function countySourceBadges(
  county: string,
  years: GuideYears,
  estimated: ReadonlySet<string>,
): string {
  const year = years[county];
  const newest = Object.values(years).sort().at(-1);
  const parts: string[] = [];
  if (year) {
    parts.push(
      year === newest
        ? `<span class="source-year" title="Anul grilei notariale">grila ${year}</span>`
        : `<span class="source-year older" title="Anul grilei notariale: mai vechi decât ${newest}">grila ${year}</span>`,
    );
  }
  if (estimated.has(county)) {
    parts.push(
      '<span class="badge-estimated" title="Valoare estimată, nu citită dintr-o grilă">estimat</span>',
    );
  }
  return parts.join('');
}

const SEVERITY_LABELS: Record<string, string> = {
  blocking: 'blocant',
  material: 'important',
  note: 'de reținut',
};

/** A limitation's severity as the page prints it; the data keeps the English key. */
export function severityLabel(severity: string): string {
  return SEVERITY_LABELS[severity] ?? severity;
}
