/**
 * Loading and error states (design screens, criterion 7).
 *
 * The loader is visible at once and, after two seconds, stops repeating its first line; the
 * error state names what failed and offers to try again. Retrying reloads the page: the
 * registry is one fetch, and the honest retry is to run it again from the start.
 */
export const LOADER_STAGE_MS = 2000;

export const RETRY_LABEL = 'Reîncearcă';

/** Which of the two loader texts applies after `elapsedMs`. */
export function loaderText(elapsedMs: number, first: string, later: string): string {
  return elapsedMs >= LOADER_STAGE_MS ? later : first;
}

/** Switch the loader's text after the stage delay; returns the function that cancels it. */
export function stageLoader(el: HTMLElement, later: string): () => void {
  const timer = setTimeout(() => {
    el.textContent = later;
  }, LOADER_STAGE_MS);
  return () => clearTimeout(timer);
}

const escapeHtml = (text: string): string =>
  text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] ?? c);

/** The error state's markup: the message, then a retry button. */
export function errorStateHtml(message: string): string {
  return (
    `<span>Nu s-au putut încărca datele: ${escapeHtml(message)}</span> ` +
    `<button type="button" class="civic-button retry">${RETRY_LABEL}</button>`
  );
}

/** Turn the loader into the error state and wire the retry button. */
export function showError(el: HTMLElement, message: string, retry: () => void = () => location.reload()): void {
  el.innerHTML = errorStateHtml(message);
  el.classList.add('error');
  el.setAttribute('role', 'alert');
  el.querySelector<HTMLButtonElement>('button.retry')?.addEventListener('click', retry);
}
