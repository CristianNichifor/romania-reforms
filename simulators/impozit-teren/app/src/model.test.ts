/**
 * Parity between the browser's arithmetic and the Python that produced the committed data.
 *
 * The page recomputes both taxes as the reader moves the assumptions, which means the model
 * is a second implementation of `build_valoare_teren.py` and `build_impozit.py`. Two
 * implementations of the same arithmetic drift silently — the page would keep rendering
 * confident numbers that no longer match the files they were checked against — so at the
 * Python's own settings the two must agree to the rounding.
 *
 * The data is read from `simulators/impozit-teren/data`, not from the copy the build makes
 * into `public/`, so this fails on a real disagreement rather than on a stale copy.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { DONOR_CATEGORY, combine, evaluate, fiscalRank, landValueParts, splitArea } from './model';
import type { FiscalCode, Locality, Settings } from './model';

const here = dirname(fileURLToPath(import.meta.url));
const read = (name: string) =>
  JSON.parse(readFileSync(resolve(here, `../../data/${name}`), 'utf-8'));

const code: FiscalCode = read('cod-fiscal-teren-2026.json');

/**
 * Agreement to a millionth, relative rather than absolute.
 *
 * A county's land is a ten-digit number of lei, so "within 500" is an arbitrary tolerance
 * that happens to pass for one county and fail for another: Alba's land value is published
 * in euro after a conversion from lei, and re-multiplying the rounded figure moves the total
 * by about 1 600 lei in 20 billion. That is float rounding, not disagreement. A real
 * difference in the arithmetic — a category dropped, a rate applied twice — moves things by
 * whole percentages, which this still catches with room to spare.
 */
function expectClose(actual: number, expected: number, label = ''): void {
  expect(Math.abs(actual - expected) / Math.abs(expected), label).toBeLessThan(1e-6);
}
/**
 * Every county the repository has built, found rather than listed.
 *
 * Listing them by hand meant a newly landed county was covered by no parity test at all until
 * someone remembered to add it here, which is exactly the moment the two implementations are
 * most likely to disagree. The edition is discovered the same way: nine counties are 2026 and
 * three are 2025, because the Ploiești and Galați chambers did not publish in step.
 */
const DATA = resolve(here, '../../data');
const editions = (prefix: string): Map<string, string> => {
  const found = new Map<string, string>();
  for (const name of readdirSync(DATA).sort()) {
    const match = new RegExp(`^${prefix}-([a-z]{2})-\\d{4}\\.json$`).exec(name);
    const county = match?.[1];
    if (county) found.set(county, name);
  }
  return found;
};
const VALUES = editions('valoare-teren');
const TAXES = editions('impozit');
const RENTS = editions('renta');
/** The rent file for a county, or undefined — the fixture needs its per-category yields. */
const rentOf = (county: string) => {
  const name = RENTS.get(county);
  return name ? read(name) : undefined;
};
const COUNTIES = [...VALUES.keys()].filter((county) => TAXES.has(county));

function fixture(county: string) {
  const value = read(VALUES.get(county)!);
  const tax = read(TAXES.get(county)!);
  const settings: Settings = {
    share: 1,
    value: 'central',
    fiscal: 'central',
    rate: tax.assumptions.lvtRatePercent,
    // From the tax file, like every other yield here. This was a literal 5 while the
    // built-land band was assumed; it is now derived in randament-teren-construit-2026.json
    // and a literal would make the parity check pass against a number Python stopped using.
    landYield: tax.assumptions.builtYieldPercent?.central ?? 5,
    // From the tax file rather than a literal: the measured farmland yield is county-specific
    // and the whole point of the parity check is that the browser uses the same one Python did.
    landYieldAgricultural: tax.assumptions.agriculturalYieldPercent?.central ?? 5,
    landYieldByCategory: Object.fromEntries(
      Object.entries(rentOf(county)?.assumptions?.yieldByCategoryPercent ?? {}).map(
        ([code, band]) => [code, (band as { central: number }).central],
      ),
    ),
    // From the tax file for the same reason as the yields: Python's default is 1 and a
    // literal here would keep passing if that default ever moved.
    collectionRate: tax.assumptions.collectionRate ?? 1,
    ronPerEur: tax.assumptions.ronPerEur,
  };
  return { localities: value.localities as Locality[], tax, settings };
}

describe.each(COUNTIES)('%s rent parity', (county) => {
  /**
   * The browser's rent against the rent Python committed, county by county.
   *
   * Until the yield was split this was covered only indirectly — the page multiplied one total
   * by one number and so did the builder, so they could hardly disagree. Two yields on two
   * halves is real arithmetic on both sides, and the halves are computed independently in
   * TypeScript and in Python, so this is now the assertion that keeps them honest.
   */
  it('reproduces the land rent build_renta.py wrote', () => {
    const name = RENTS.get(county);
    if (!name) return;
    const rent = read(name);
    const { localities, settings } = fixture(county);
    const { totals } = evaluate(localities, code, settings);
    expectClose(totals.rent, rent.summary.landRentRon.central, `${county} rent`);
    // Against the stored totals, not against the stored percent. `fullRentRatePercent` is
    // rounded to four decimals, so comparing to it can only ever be as tight as half its last
    // digit — and Prahova landed 3e-9 the wrong side of that. The ratio of the two totals is
    // the same quantity without the rounding, so this is both exact and the thing meant.
    expectClose(
      (100 * totals.rent) / totals.value,
      (100 * rent.summary.landRentRon.central) / rent.summary.landValueRon.central,
      `${county} blended yield`,
    );
  });
});

describe.each(COUNTIES)('%s', (county) => {
  const { localities, tax, settings } = fixture(county);

  it('reproduces the land value the Python wrote', () => {
    const { totals } = evaluate(localities, code, settings);
    expectClose(totals.value, tax.summary.landValueRon.central);
  });

  it('reproduces the Fiscal Code tax the Python wrote', () => {
    const { totals } = evaluate(localities, code, settings);
    expectClose(totals.fiscal, tax.summary.fiscalCodeRon.central);
  });

  it('reproduces the taxable base and what it would collect', () => {
    // The taxable base is a second valuation, over a second set of hectares, in a second
    // language — exactly the shape that drifts silently. It is also the number a revenue
    // claim rests on, so it gets the same parity treatment as the value itself.
    const { totals } = evaluate(localities, code, settings);
    expectClose(totals.taxable, tax.summary.taxableValueRon.central, `${county} taxable`);
    expectClose(totals.collected, tax.summary.lvtCollectedRon.central, `${county} collected`);
  });

  it('cannot tax more land than the county has', () => {
    // The invariant that catches a scope wired to the wrong field: private land is a subset,
    // so its value is bounded by the whole, and a taxable base equal to the total would mean
    // the ownership split never arrived rather than that the county is wholly private.
    const { totals } = evaluate(localities, code, settings);
    expect(totals.taxable).toBeGreaterThan(0);
    expect(totals.taxable).toBeLessThan(totals.value);
  });

  it('reproduces the revenue-neutral rate, which is the headline', () => {
    const { totals } = evaluate(localities, code, settings);
    expect(totals.neutral).toBeCloseTo(tax.summary.revenueNeutralRatePercent.central, 3);
  });

  it('agrees locality by locality, not just in the total', () => {
    // A total can be right while two communes are wrong in opposite directions, and the page
    // ranks localities against each other — so the per-row agreement is the one that matters.
    const { rows } = evaluate(localities, code, settings);
    const expected = new Map<string, { fiscalCodeRon: { central: number } }>(
      tax.localities.map((row: { siruta: string }) => [row.siruta, row as never]),
    );
    expect(rows.length).toBe(tax.localities.length);
    for (const row of rows) {
      const want = expected.get(row.siruta);
      expect(want, row.name).toBeDefined();
      expect(row.fiscalCodeRon, row.name).toBeCloseTo(want!.fiscalCodeRon.central, -1);
    }
  });

  it('reads the low and high bands the way the Python does', () => {
    for (const band of ['low', 'high'] as const) {
      const { totals } = evaluate(localities, code, { ...settings, fiscal: band, value: band });
      expectClose(totals.fiscal, tax.summary.fiscalCodeRon[band], band);
      expectClose(totals.value, tax.summary.landValueRon[band], band);
    }
  });
});

describe('the assumptions the reader moves', () => {
  const { localities, settings } = fixture('bc');

  it('takes extra intravilan land from arable rather than inventing it', () => {
    // Raising the share has to conserve land. The failure this guards is an intravilan
    // multiplier that grows the county — which would raise the land value for free.
    for (const share of [1, 1.5, 3, 10]) {
      const totalHa = localities.reduce((sum, l) => sum + l.totalHa, 0);
      let accounted = 0;
      for (const locality of localities) {
        const { intravilanHa, movedFromDonor } = splitArea(locality, share);
        const others = Object.entries(locality.areaHa)
          .filter(([code]) => code !== 'CC')
          .reduce(
            (sum, [code, ha]) => sum + (code === DONOR_CATEGORY ? ha - movedFromDonor : ha),
            0,
          );
        expect(movedFromDonor).toBeLessThanOrEqual(locality.areaHa[DONOR_CATEGORY] ?? 0);
        accounted += intravilanHa + others;
      }
      // Forest is outside both taxes, so the accounted area is the total less forest.
      expect(accounted).toBeLessThanOrEqual(totalHa + 1);
    }
  });

  it('raises both taxes when more land is treated as intravilan', () => {
    const base = evaluate(localities, code, settings).totals;
    const more = evaluate(localities, code, { ...settings, share: 2 }).totals;
    expect(more.value).toBeGreaterThan(base.value);
    expect(more.fiscal).toBeGreaterThan(base.fiscal);
  });

  it('scales the tax with the rate and leaves the neutral rate alone', () => {
    const base = evaluate(localities, code, settings).totals;
    const doubled = evaluate(localities, code, { ...settings, rate: settings.rate * 2 }).totals;
    expectClose(doubled.lvt, base.lvt * 2);
    expect(doubled.neutral).toBeCloseTo(base.neutral, 6);
  });
});

describe('land rent', () => {
  const { localities, settings } = fixture('bc');

  it('is the two halves at their own yields, and the capture is the tax out of it', () => {
    // Not stock × one yield any more. Farmland's return is measured and building land's is
    // assumed, they differ by a factor of three, so the total rent is the sum of two products
    // and the county's effective yield is a blend weighted by how much of it is farmland.
    const { totals } = evaluate(localities, code, settings);
    const built = localities.reduce(
      (sum, l) => sum + landValueParts(l, settings).built * settings.ronPerEur,
      0,
    );
    const agricultural = localities.reduce(
      (sum, l) => sum + landValueParts(l, settings).agricultural * settings.ronPerEur,
      0,
    );
    // Per cadastral code now, not one agricultural lump: arable and pasture are measured
    // apart and forest borrows arable's band, so the rent is a sum over codes.
    let expected = (built * settings.landYield) / 100;
    let accounted = 0;
    for (const locality of localities) {
      for (const [code, amount] of Object.entries(landValueParts(locality, settings).byCode)) {
        const band = settings.landYieldByCategory[code] ?? settings.landYieldAgricultural;
        expected += (amount * settings.ronPerEur * band) / 100;
        accounted += amount * settings.ronPerEur;
      }
    }
    expected += (Math.max(0, agricultural - accounted) * settings.landYieldAgricultural) / 100;
    expectClose(totals.rent, expected);
    expectClose(totals.fiscalCapture, (100 * totals.fiscal) / totals.rent);
    expectClose(built + agricultural, totals.value);
  });

  it('lands the blended yield inside the set of yields it is made of', () => {
    // The check that the split is actually doing something. It used to assert the blend sat
    // strictly between the farmland yield and the built-land one, which held only because the
    // built-land yield was assumed at 5% and was therefore the largest number in the county by
    // construction. Derived, it is 2,53%, and two counties now have a category above it:
    // Neamț's forest yields 3,52% and Vrancea's 5,22%, because those chambers price forest at
    // a sixth of what Iași does and a yield is rent over price. So the invariant is the one
    // that was always the real one — a weighted mean lies within the range of its inputs.
    const { totals } = evaluate(localities, code, settings);
    const blended = (100 * totals.rent) / totals.value;
    const applied = [
      settings.landYield,
      settings.landYieldAgricultural,
      ...Object.values(settings.landYieldByCategory),
    ];
    expect(blended).toBeGreaterThanOrEqual(Math.min(...applied) - 1e-9);
    expect(blended).toBeLessThanOrEqual(Math.max(...applied) + 1e-9);
  });

  it('moves the capture the other way when the yield moves', () => {
    // Less rent out of the same land means the same tax is a bigger bite of it. The direction
    // is the point: a reader lowering the yield should see today's tax look heavier, not
    // lighter, and an inverted ratio would be invisible in the total.
    const base = evaluate(localities, code, settings).totals;
    const thin = evaluate(localities, code, {
      ...settings,
      landYield: settings.landYield / 2,
    }).totals;
    expect(thin.rent).toBeLessThan(base.rent);
    expect(thin.fiscalCapture).toBeGreaterThan(base.fiscalCapture);
  });

  it('makes a full land value tax the blended yield', () => {
    // A rate on value equal to the *effective* yield takes the whole rent. With one yield that
    // was the parameter itself; with two it is the blend, which is why the page computes it
    // from the totals rather than printing the control back at the reader.
    const base = evaluate(localities, code, settings).totals;
    const blended = (100 * base.rent) / base.value;
    const full = evaluate(localities, code, { ...settings, rate: blended }).totals;
    expectClose(full.lvtCapture, 100);
  });
});

describe('locality rank', () => {
  it('puts Bacău at rank I and a town at rank III', () => {
    expect(fiscalRank('municipii', 'Bacău', 'central')).toBe('I');
    expect(fiscalRank('municipii', 'Moinesti', 'central')).toBe('II');
    expect(fiscalRank('orase', 'Buhusi', 'central')).toBe('III');
  });

  it('gives a commune two ranks, because its seat and its villages differ', () => {
    expect(fiscalRank('comune', 'Cleja', 'low')).toBe('V');
    expect(fiscalRank('comune', 'Cleja', 'high')).toBe('IV');
  });
});

describe('toate județele, added up', () => {
  const parts = COUNTIES.map((county) => {
    const { localities, settings } = fixture(county);
    return evaluate(localities, code, settings);
  });
  const all = combine(parts);

  it('adds every county the Python priced, at that county own rates', () => {
    // The sum against the files, not against a re-run of the browser: each county is priced at
    // its own exchange rate and its own measured farmland yield, and the whole reason this
    // function exists is that applying one county's rates to another's hectares is wrong.
    const expected = COUNTIES.reduce(
      (sum, county) => sum + fixture(county).tax.summary.landValueRon.central,
      0,
    );
    expectClose(all.totals.value, expected);
    expect(all.rows.length).toBe(parts.reduce((n, part) => n + part.rows.length, 0));
  });

  it('recomputes the rates from the sums rather than averaging them', () => {
    // A mean of forty-two revenue-neutral rates answers "what is the typical county's rate".
    // The page asks what the country's land raises against what it is worth, which is the
    // ratio of the two totals — and the two differ, so this is a real distinction.
    expect(all.totals.neutral).toBeCloseTo((100 * all.totals.fiscal) / all.totals.value, 9);
    expect(all.totals.fiscalCapture).toBeCloseTo((100 * all.totals.fiscal) / all.totals.rent, 9);
    const mean = parts.reduce((sum, part) => sum + part.totals.neutral, 0) / parts.length;
    expect(Math.abs(all.totals.neutral - mean)).toBeGreaterThan(1e-6);
  });
});
