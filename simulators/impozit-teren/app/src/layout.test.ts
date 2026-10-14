/**
 * Two layout faults from the UX review. On a wide screen the sticky sidebar is one viewport
 * tall, and below it the page background showed as a black gap beside long results. On a
 * phone the sidebar's long "Ce nu putem calcula" fold and the sources came before any result.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { placeTrailing } from './layout';

const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');
const wide = css.slice(css.indexOf('@media (min-width: 60.01rem)'), css.indexOf('#panel {'));

describe('the sidebar column on wide screens', () => {
  it('is painted to the bottom of the page by the body', () => {
    expect(wide).toMatch(/body \{\s*background:\s*linear-gradient\(\s*90deg,\s*var\(--panel\) 0 min\(24rem, 92vw\)/);
  });
});

/** A minimal element tree: parentElement, append, children in order. */
type Node = { name: string; parentElement: Node | null; children: Node[]; append(n: Node): void };
const node = (name: string): Node => {
  const n: Node = {
    name,
    parentElement: null,
    children: [],
    append(child) {
      child.parentElement?.children.splice(child.parentElement.children.indexOf(child), 1);
      child.parentElement = n;
      n.children.push(child);
    },
  };
  return n;
};

describe('the one-column layout on phones', () => {
  const build = () => {
    const sidebar = node('panel');
    const results = node('main');
    const controls = node('controls');
    const fold = node('fold');
    const sources = node('footer');
    const table = node('table');
    sidebar.append(controls);
    sidebar.append(fold);
    sidebar.append(sources);
    results.append(table);
    return { sidebar, results, fold, sources, controls, table };
  };
  const as = (t: ReturnType<typeof build>) =>
    ({ trailing: [t.fold, t.sources], sidebar: t.sidebar, results: t.results }) as unknown as Parameters<
      typeof placeTrailing
    >[0];

  it('puts the fold and the sources after the results', () => {
    const t = build();
    placeTrailing(as(t), true);
    expect(t.sidebar.children.map((c) => c.name)).toEqual(['controls']);
    expect(t.results.children.map((c) => c.name)).toEqual(['table', 'fold', 'footer']);
  });

  it('returns them to the sidebar on a wide screen, in order', () => {
    const t = build();
    placeTrailing(as(t), true);
    placeTrailing(as(t), false);
    expect(t.sidebar.children.map((c) => c.name)).toEqual(['controls', 'fold', 'footer']);
    expect(t.results.children.map((c) => c.name)).toEqual(['table']);
  });

  it('is idempotent', () => {
    const t = build();
    placeTrailing(as(t), false);
    expect(t.sidebar.children.map((c) => c.name)).toEqual(['controls', 'fold', 'footer']);
  });
});
