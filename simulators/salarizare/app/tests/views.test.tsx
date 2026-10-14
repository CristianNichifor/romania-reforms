// Each view renders from the committed data (RR-6). Rendered to static markup, so the views
// are exercised without a DOM library; the data is read from the repository like the engine
// tests read it.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { applyProposal } from '../../engine/proposal';
import type { Proposal } from '../../engine/proposal';
import { DEFAULT_SCENARIO } from '../../engine/scenario';
import type { Crosswalk, Regime } from '../../engine/types';
import HomeView from '../src/HomeView';
import MergesView from '../src/MergesView';
import PayslipView from '../src/PayslipView';
import ProposalView from '../src/ProposalView';
import StructureView from '../src/StructureView';

const data = resolve(dirname(fileURLToPath(import.meta.url)), '../../data');
const load = <T,>(path: string): T => JSON.parse(readFileSync(resolve(data, path), 'utf8')) as T;

const draft = load<Regime>('regimes/ro-draft-2026-08-20.json');
const inForce = load<Regime>('regimes/ro-153-2017.json');
const proposal = load<Proposal>('proposals/propunere-v1.json');
const assimilation = load<Crosswalk>('crosswalks/ro-153-2017--ro-draft-2026-08-20.json');
const rates = { dkkToRon: 0.67, eurToRon: 5.0, date: '2026-08-27' };
const noop = () => undefined;

describe('views render from the committed data', () => {
  it('Payslip shows the person and the calculation per regime', () => {
    const html = renderToStaticMarkup(
      <PayslipView
        regimes={[inForce, draft]}
        scenario={{ ...DEFAULT_SCENARIO, view: 'payslip' }}
        onChange={noop}
        rates={rates}
        assimilation={assimilation}
        inForce={inForce}
      />,
    );
    expect(html).toContain('Persoana');
  });

  it('Structure describes the grid', () => {
    const html = renderToStaticMarkup(<StructureView regime={draft} period={null} />);
    expect(html).toContain('Ce arată grila');
    expect(html).toContain('Ce nu poate calcula acest instrument');
  });

  it('Proposal lists every patch', () => {
    const html = renderToStaticMarkup(
      <ProposalView
        ministry={draft}
        proposal={proposal}
        scenario={{ ...DEFAULT_SCENARIO, view: 'propunere' }}
        onScenario={noop}
        onOpen={noop}
      />,
    );
    expect(html).toContain('Corecturile');
    for (const patch of proposal.patches) expect(html).toContain(patch.title);
  });

  it('Merges draws a card per merged position', () => {
    const ours = applyProposal(draft, proposal).regime;
    const html = renderToStaticMarkup(
      <MergesView
        draft={draft}
        ours={ours}
        inForce={inForce}
        crosswalk={assimilation}
        groups={null}
        danish={[]}
        rates={rates}
        scenario={{ ...DEFAULT_SCENARIO, view: 'functii' }}
        onScenario={noop}
      />,
    );
    expect(html).toMatch(/<h3>[^<]+<\/h3>/);
  });
});

describe('the data line under the H1 (UX-5)', () => {
  it('follows the home H1 and names the MMFTSS package the footer cites', () => {
    const html = renderToStaticMarkup(
      <HomeView
        ministry={draft}
        inForce={inForce}
        denmark={null}
        dataLine="Date: MMFTSS, pachetul public din 20.08.2026; IDA (Danemarca), 01.04.2026"
        statusBadge="Date reale"
        onOpen={noop}
      />,
    );
    expect(html).toMatch(/<\/h1><p class="purpose">.*?<\/p><p class="data-line">Date: MMFTSS, pachetul public din 20\.08\.2026/);
  });
});
