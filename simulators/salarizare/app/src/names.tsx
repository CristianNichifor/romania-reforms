import type { Regime } from '../../engine/types';

/**
 * The source sheets hang footnote markers on names — "Farmacist primar*1)", "Rector*)",
 * "Director unitate de învățământ*) **)" — and the importer keeps them verbatim, because a
 * name is a locator. The regime files carry no footnote text, so the marker can only be
 * shown as what it is: a note in the source table, not something this tool can quote.
 */
const MARKER = /\s*(\*+\d*\))/g;

export function splitFootnotes(name: string): { base: string; markers: string[] } {
  const markers = Array.from(name.matchAll(MARKER), (m) => m[1]);
  const base = name.replace(MARKER, '').replace(/\s{2,}/g, ' ').trim();
  return { base, markers };
}

/**
 * A position's name as the reader should see it: the words, with each source mark drawn
 * as the superscript note it is, in the place the sheet put it, so the text reads the same.
 */
export function PositionName({ name, code }: { name: string; code?: string }) {
  const parts = name.split(/(\*+\d*\))/);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <sup
            key={i}
            className="footnote-mark"
            aria-label={`notă ${part} din tabelul sursă, al cărei text nu este în datele acestui instrument`}
            title="Notă din tabelul sursă; textul ei nu este în datele acestui instrument."
          >
            {part}
          </sup>
        ) : (
          part
        ),
      )}
      {code && (
        <>
          {' '}
          <code className="position-code" title="codul poziției în anexa sursă">
            {code}
          </code>
        </>
      )}
    </>
  );
}

/** A regime by its law or its country, not its file id; the id when nothing is loaded yet. */
export function regimeLabel(id: string, regimes: Record<string, Regime>): string {
  const name = regimes[id]?.name;
  return name ? name.split(/[(,]/)[0].replace(/\s+privind\b.*$/, '').trim() : id;
}
