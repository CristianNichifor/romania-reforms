import { describe, expect, it } from 'vitest';

import { captionCharts, chartCaptions, editionsPeriod } from './chart-source';

const csm = { publisher: 'Consiliul Superior al Magistraturii', period: '2025' };

describe('chart captions', () => {
  it('use the header line wording for every source', () => {
    expect(chartCaptions({ portal: csm, editions: { ...csm, period: '2022-2025' } })).toEqual({
      portal: 'Date: Consiliul Superior al Magistraturii, 2025',
      editions: 'Date: Consiliul Superior al Magistraturii, 2022–2025',
    });
  });

  it('span the editions from the oldest to the newest year', () => {
    expect(editionsPeriod(['2024', '2022', '2025', '2023'])).toBe('2022-2025');
    expect(editionsPeriod(['2025'])).toBe('2025');
    expect(editionsPeriod([])).toBe('');
  });

  it('write each caption into its placeholders and hide the ones without a source', () => {
    const make = (source: string) => ({ dataset: { source }, textContent: 'x', hidden: false }) as unknown as HTMLElement;
    const nodes = [make('portal'), make('portal'), make('editions'), make('unknown')];
    const root = { querySelectorAll: () => nodes } as unknown as ParentNode;
    expect(captionCharts(root, { portal: csm, editions: { ...csm, period: '2022-2025' } })).toBe(3);
    expect(nodes.map((n) => n.textContent)).toEqual([
      'Date: Consiliul Superior al Magistraturii, 2025',
      'Date: Consiliul Superior al Magistraturii, 2025',
      'Date: Consiliul Superior al Magistraturii, 2022–2025',
      '',
    ]);
    expect(nodes.map((n) => n.hidden)).toEqual([false, false, false, true]);
  });
});
