// Charts start at zero, print their values and name their source (design screen 03, criterion 6).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { Regime } from '../../engine/types';
import StructureView from '../src/StructureView';
import { ColumnChart, GradeChart } from '../src/charts';

const data = resolve(dirname(fileURLToPath(import.meta.url)), '../../data');
const inForce = JSON.parse(readFileSync(resolve(data, 'regimes/ro-153-2017.json'), 'utf8')) as Regime;

describe('a column chart', () => {
  const html = renderToStaticMarkup(
    <ColumnChart bars={[{ label: 'a', value: 3 }, { label: 'b', value: 120 }]} yLabel="n" source="Anexa I" />,
  );

  it('starts its axis at zero', () => {
    expect(html).toMatch(/<text class="tick"[^>]*>0<\/text>/);
  });

  it('prints every value next to its bar, the small ones too', () => {
    expect(html).toMatch(/<text class="mark-label"[^>]*>3<\/text>/);
    expect(html).toMatch(/<text class="mark-label"[^>]*>120<\/text>/);
  });

  it('names its source under the marks', () => {
    expect(html).toMatch(/<\/svg><p class="chart-source">Sursă: Anexa I<\/p>/);
  });
});

describe('the grade chart', () => {
  it('prints the count on every grade', () => {
    const html = renderToStaticMarkup(
      <GradeChart
        grades={[{ gradeId: 'g1', label: 'Gradul 1', min: 1, max: 1.19, variants: 7 }]}
        gaps={[]}
        source="Art. 9"
      />,
    );
    expect(html).toMatch(/<text class="mark-label"[^>]*>7<\/text>/);
    expect(html).toContain('<p class="chart-source">Sursă: Art. 9</p>');
  });
});

describe('the structure view', () => {
  it('puts a source line under each of its four charts', () => {
    const html = renderToStaticMarkup(<StructureView regime={inForce} period={null} />);
    expect(html.match(/<p class="chart-source">Sursă: /g)).toHaveLength(4);
    expect(html).toContain(inForce.provenance.locator);
  });
});
