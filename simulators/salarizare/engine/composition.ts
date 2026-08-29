/**
 * Putting the Romanian and Danish pay compositions on one axis.
 *
 * Both sides describe what was actually paid: Denmark from Danmarks Statistik's LONSOFF
 * components, Romania from the budget execution filed against the economic classification.
 * That makes a comparison possible, but not yet fair, because the two totals are drawn
 * around different things.
 *
 * Two items come out of the Danish side before anything is compared:
 *
 *   * **Pension**, 13,5% of Danish earnings. It is the employer's contribution, and the
 *     Romanian figure deliberately excludes its counterpart — title 10.03 — so that the
 *     two describe pay rather than the cost of employing someone.
 *   * **Paid sickness**, 5,7%. Romania pays sick leave from a different budget title
 *     altogether, so it never appears in the Romanian numerator.
 *
 * One item that looks like it should come out, and must not: **holiday pay**. Danmarks
 * Statistik prints it at around 12%, which invites subtracting it — but it prints it with
 * a leading ".." because it is a sub-item *inside* basic earnings, not a component beside
 * it. A Dane on holiday keeps drawing salary, exactly as a Romanian does. Subtracting it
 * would strip twelve points off Danish base pay that were only ever counted once, and it
 * would invert the answer: Romania would appear the more base-heavy system when it is the
 * less. The importer marks it `composition-subitem` so nothing here can sum it by accident.
 *
 * On the Romanian side one item comes out: delegation and secondment allowances, which
 * reimburse a cost rather than pay for work, and have no Danish counterpart at all.
 */

/** The shared vocabulary. `seniority` exists only on the Romanian side — see below. */
export type Component =
  | 'basic'
  | 'seniority'
  | 'conditions'
  | 'overtime'
  | 'irregular'
  | 'fringe';

/** Order is fixed so the same component keeps the same colour and position everywhere. */
export const COMPONENTS: Component[] = [
  'basic',
  'seniority',
  'conditions',
  'overtime',
  'irregular',
  'fringe',
];

export const COMPONENT_LABELS: Record<Component, string> = {
  basic: 'Salariu de bază',
  seniority: 'Spor de vechime',
  conditions: 'Sporuri de condiții',
  overtime: 'Ore suplimentare',
  irregular: 'Plăți neregulate',
  fringe: 'Beneficii și hrană',
};

/**
 * Everything a source may report. Only the `Component` keys enter the comparison; the
 * rest are named here so that dropping them is a decision recorded in the type, rather
 * than a key that silently never arrives.
 */
export type Shares = Partial<
  Record<Component | 'pension' | 'sickness' | 'holiday' | 'other', number>
>;

/** What was set aside before comparing, so the page can list it instead of hiding it. */
export interface Excluded {
  key: 'pension' | 'sickness' | 'other';
  label: string;
  /** Share of that side's original published total. */
  share: number;
  reason: string;
}

const EXCLUSIONS: Array<Omit<Excluded, 'share'>> = [
  {
    key: 'pension',
    label: 'Pensie plătită de angajator',
    reason:
      'Contribuția angajatorului la pensie. Partea românească exclude titlul 10.03, ' +
      'corespondentul ei, ca ambele cifre să descrie plata, nu costul angajării.',
  },
  {
    key: 'sickness',
    label: 'Zile de boală plătite',
    reason:
      'România plătește concediul medical din alt titlu bugetar, deci suma nu apare ' +
      'niciodată în numărătorul românesc.',
  },
  {
    key: 'other',
    label: 'Delegare și detașare',
    reason:
      'Decontarea unei cheltuieli, nu plata unei munci — și fără corespondent danez.',
  },
];

export interface Slice {
  component: Component;
  /** Share of comparable pay: the six components, renormalised to one. */
  share: number;
}

export interface Side {
  slices: Slice[];
  /** Everything that is not base salary — the supplement layer, in one number. */
  supplements: number;
  /** What was taken out first, and why. Only non-zero entries appear. */
  excluded: Excluded[];
  /**
   * Holiday pay as the source published it. Carried for display only; it is already
   * inside `basic` and must never be added to it or taken out of it.
   */
  holidayInsideBasic: number;
}

export interface CompositionComparison {
  ro: Side;
  dk: Side;
  /**
   * How many times larger Romania's supplement layer is. `null` when the Danish side
   * has no data, so the page shows nothing rather than a division by zero.
   */
  timesLarger: number | null;
}

function build(shares: Shares): Side {
  const kept = COMPONENTS.map((component) => ({
    component,
    raw: shares[component] ?? 0,
  }));
  const total = kept.reduce((sum, k) => sum + k.raw, 0);

  const excluded = EXCLUSIONS.map((e) => ({ ...e, share: shares[e.key] ?? 0 })).filter(
    (e) => e.share > 0,
  );
  const holidayInsideBasic = shares.holiday ?? 0;

  // A caller with no data for a side gets an empty side, never a bar of NaN.
  if (total <= 0) {
    return { slices: [], supplements: 0, excluded, holidayInsideBasic };
  }

  const slices = kept.map(({ component, raw }) => ({ component, share: raw / total }));
  const basic = slices.find((s) => s.component === 'basic')?.share ?? 0;
  return { slices, supplements: 1 - basic, excluded, holidayInsideBasic };
}

export function compareComposition(ro: Shares, dk: Shares): CompositionComparison {
  const roSide = build(ro);
  const dkSide = build(dk);
  return {
    ro: roSide,
    dk: dkSide,
    timesLarger:
      dkSide.slices.length && dkSide.supplements > 0
        ? roSide.supplements / dkSide.supplements
        : null,
  };
}
