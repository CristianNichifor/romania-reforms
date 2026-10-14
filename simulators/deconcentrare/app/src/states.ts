/**
 * Loading and error states of the page (UX-15, ux-guidelines § 5): the loader says when it
 * is slow, and a failed load says what failed and offers to try again. Markup is built as a
 * string from escaped text so the module stays testable without a DOM.
 */
export const LOADING = 'Se încarcă datele…';
export const LOADING_SLOW = 'Se încarcă datele… durează mai mult decât de obicei.';
export const RETRY = 'Reîncearcă';
/** After this many milliseconds the loader turns into its second stage. */
export const SLOW_AFTER_MS = 2000;

const escape = (text: string): string =>
  text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);

/** The error state: what failed, then a button the page wires to a reload. */
export function loadErrorMarkup(message: string): string {
  return (
    `<span>Nu s-au putut încărca datele: ${escape(message)}</span> ` +
    `<button type="button" class="retry">${RETRY}</button>`
  );
}

export const messageOf = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);
