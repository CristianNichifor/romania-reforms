import type { Lang } from './i18n';

/** Both languages of the empty state (RR-10). English copy is agent-written: needs human review. */
export const NOHIT_STRINGS: Record<Lang, (query: string) => string> = {
  ro: (query) =>
    `Niciun post pentru „${query}” în grila proiectului. Denumirile sunt cele din anexe, ` +
    'iar multe posturi reale sunt comasate sub un titlu care nu le conține: încearcă cuvântul cel ' +
    'mai general din meserie (de exemplu „asistent” în loc de „asistent medical principal”) sau ' +
    'alege o secțiune din meniu.',
  en: (query) =>
    `No post for "${query}" in the draft's grid. The titles are those of the annexes, ` +
    'and many real posts are merged under a title that does not contain them: try the most ' +
    'general word of the trade (for instance "asistent" instead of "asistent medical principal") ' +
    'or pick a section from the menu.',
};

/**
 * The empty state of the home search (design screen 03, criterion 7): it names what was
 * searched and says what to try next, instead of a generic "nothing found".
 */
export default function NoHit({ query, lang = 'ro' }: { query: string; lang?: Lang }) {
  return (
    <p className="home-nohit empty-state" role="status">
      {NOHIT_STRINGS[lang](query.trim())}
    </p>
  );
}
