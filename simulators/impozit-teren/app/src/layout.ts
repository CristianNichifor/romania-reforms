/**
 * On a phone the page is one column: the sidebar, then the results. The sidebar ends with the
 * long "Ce nu putem calcula" fold and the sources, so a reader scrolled past every caveat
 * before seeing a single figure. Below the breakpoint those two sections move to the end of
 * the results; above it they return to the sidebar. The sidebar stays a box throughout, so
 * nothing that measures or screenshots `#panel` changes.
 */

export const NARROW = '(max-width: 60rem)';

export type Slots = {
  /** The sections that trail the sidebar, in order. */
  trailing: Element[];
  /** Where they live on a wide screen (the sidebar). */
  sidebar: Element;
  /** Where they go on a phone (the results column). */
  results: Element;
};

/** Move the trailing sections to the results on a phone, back to the sidebar otherwise. */
export const placeTrailing = (slots: Slots, narrow: boolean): void => {
  const target = narrow ? slots.results : slots.sidebar;
  for (const section of slots.trailing) {
    if (section.parentElement !== target) target.append(section);
  }
};

/** Wire the move to the viewport, following it as the window resizes. */
export const followViewport = (slots: Slots, media = globalThis.matchMedia): void => {
  if (typeof media !== 'function') return;
  const query = media(NARROW);
  placeTrailing(slots, query.matches);
  query.addEventListener?.('change', (e) => placeTrailing(slots, e.matches));
};
