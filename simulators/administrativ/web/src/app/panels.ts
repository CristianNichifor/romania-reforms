/**
 * The two side panels: resizable on a pointer, a bottom sheet on a phone.
 *
 * Both behaviours are the same problem — the panel and the map competing for the same
 * screen — so they live together rather than as a width helper in one place and a media
 * query in another. The panel owns its own geometry; `main.ts` only fills it with content.
 *
 * The widths were fixed at 292 px and 320 px, which is where the truncation came from: the
 * text was not overflowing a box that could hold it, the box was too small and said so by
 * clipping. Widening is therefore the fix, and letting the reader widen it is the fix that
 * survives the next panel of content being added.
 */

/** Below this the panels stop being columns beside the map and become sheets under it. */
export const SHEET_BREAKPOINT_PX = 900;

export const MIN_WIDTH_PX = 260;
/* Raised from 560. The panels carry more than they did — a candidate list, forced centres,
   saved versions, the representation table — and a reader who wants them wide should not be
   stopped at a width chosen when the detail panel held six rows. */
export const MAX_WIDTH_PX = 720;

/** Arrow-key step. A drag-only control cannot be used without a mouse. */
const KEY_STEP_PX = 16;

export type PanelEdge = 'left' | 'right';

export interface PanelOptions {
  element: HTMLElement;
  handle: HTMLElement;
  /** localStorage key for the reader's chosen width. */
  storageKey: string;
  defaultWidth: number;
  /** Which side of the panel the handle sits on: the edge that faces the map. */
  edge: PanelEdge;
}

export interface Panel {
  /** True while the viewport is narrow enough that the panel is a sheet. */
  isSheet: () => boolean;
  /** Open or collapse the sheet. No effect while the panel is a column. */
  setOpen: (open: boolean) => void;
  isOpen: () => boolean;
  /** Text on the sheet's peek bar. */
  setTitle: (title: string) => void;
  /** Accessible names, re-applied when the language changes. */
  setLabels: (resize: string, help: string) => void;
  /** Back to the built-in width. */
  reset: () => void;
  /** Fires whenever the width changes, so anything sized against it can follow. */
  onResize: (handler: (width: number) => void) => void;
}

/** Widths outside the band are clamped rather than refused: a drag should stop, not fail. */
export const clampWidth = (value: number): number =>
  Math.min(MAX_WIDTH_PX, Math.max(MIN_WIDTH_PX, Math.round(value)));

/**
 * A saved width, or null when there is nothing usable to read.
 *
 * Anything unparseable is discarded rather than thrown: a hand-edited or half-written
 * localStorage entry should cost the reader their custom width, not the panel. `Number('')`
 * is 0, so an empty string has to be rejected before the finite check rather than clamped
 * up to the minimum, which would look like a width somebody chose.
 */
export function parseStoredWidth(raw: string | null): number | null {
  if (raw === null || raw.trim() === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) ? clampWidth(value) : null;
}

/**
 * Where a drag lands.
 *
 * The controls sit on the left and grow rightwards; the detail panel sits on the right and
 * grows leftwards. Same gesture, opposite sign — which is the one thing in this module that
 * is easy to get backwards and impossible to see in a screenshot.
 */
export function widthAfterDrag(
  edge: PanelEdge,
  startWidth: number,
  pointerDelta: number,
): number {
  return clampWidth(startWidth + (edge === 'right' ? pointerDelta : -pointerDelta));
}

function storedWidth(key: string): number | null {
  try {
    return parseStoredWidth(window.localStorage.getItem(key));
  } catch {
    return null;
  }
}

function storeWidth(key: string, width: number): void {
  try {
    window.localStorage.setItem(key, String(width));
  } catch {
    // Private browsing, or a full quota. The panel still resizes; it just forgets.
  }
}

export function createPanel(options: PanelOptions): Panel {
  const { element, handle, storageKey, defaultWidth, edge } = options;

  const media = window.matchMedia(`(max-width: ${SHEET_BREAKPOINT_PX}px)`);
  const resizeHandlers: ((width: number) => void)[] = [];

  let width = storedWidth(storageKey) ?? defaultWidth;
  let open = false;

  const announce = (): void => {
    for (const handler of resizeHandlers) handler(width);
  };

  /**
   * A sheet has no width of its own — it spans the viewport — so the inline width is removed
   * rather than overridden. Leaving it set and beating it with `!important` in the stylesheet
   * works until something else reads `element.style.width` and gets a number that is not on
   * screen.
   */
  const applyWidth = (): void => {
    if (media.matches) {
      element.style.removeProperty('width');
      handle.removeAttribute('aria-valuenow');
      return;
    }
    element.style.width = `${width}px`;
    handle.setAttribute('aria-valuenow', String(width));
    announce();
  };

  const applyMode = (): void => {
    element.dataset.sheet = media.matches ? 'true' : 'false';
    element.dataset.open = String(open);
    handle.setAttribute('role', media.matches ? 'button' : 'separator');
    if (media.matches) {
      handle.setAttribute('aria-expanded', String(open));
      handle.removeAttribute('aria-orientation');
      handle.removeAttribute('aria-valuemin');
      handle.removeAttribute('aria-valuemax');
    } else {
      handle.removeAttribute('aria-expanded');
      handle.setAttribute('aria-orientation', 'vertical');
      handle.setAttribute('aria-valuemin', String(MIN_WIDTH_PX));
      handle.setAttribute('aria-valuemax', String(MAX_WIDTH_PX));
    }
    applyWidth();
  };

  const setWidth = (next: number): void => {
    width = clampWidth(next);
    storeWidth(storageKey, width);
    applyWidth();
  };

  // --- dragging ------------------------------------------------------------------------

  let dragPointer: number | null = null;
  let dragStartX = 0;
  let dragStartWidth = 0;

  handle.addEventListener('pointerdown', (event: PointerEvent) => {
    if (media.matches) return;
    dragPointer = event.pointerId;
    dragStartX = event.clientX;
    dragStartWidth = width;
    handle.setPointerCapture(event.pointerId);
    element.dataset.dragging = 'true';
    event.preventDefault();
  });

  handle.addEventListener('pointermove', (event: PointerEvent) => {
    if (dragPointer !== event.pointerId) return;
    setWidth(widthAfterDrag(edge, dragStartWidth, event.clientX - dragStartX));
  });

  const endDrag = (event: PointerEvent): void => {
    if (dragPointer !== event.pointerId) return;
    dragPointer = null;
    handle.releasePointerCapture(event.pointerId);
    delete element.dataset.dragging;
  };
  handle.addEventListener('pointerup', endDrag);
  handle.addEventListener('pointercancel', endDrag);

  handle.addEventListener('dblclick', () => {
    if (media.matches) return;
    setWidth(defaultWidth);
  });

  // --- keyboard and tapping ------------------------------------------------------------

  handle.tabIndex = 0;
  handle.addEventListener('keydown', (event: KeyboardEvent) => {
    if (media.matches) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setOpen(!open);
      }
      return;
    }
    const grow = edge === 'right' ? 'ArrowRight' : 'ArrowLeft';
    const shrink = edge === 'right' ? 'ArrowLeft' : 'ArrowRight';
    if (event.key === grow) setWidth(width + KEY_STEP_PX);
    else if (event.key === shrink) setWidth(width - KEY_STEP_PX);
    else if (event.key === 'Home') setWidth(defaultWidth);
    else return;
    event.preventDefault();
  });

  // A tap on the peek bar opens the sheet. Guarded against firing at the end of a drag,
  // which on a touchscreen is the same gesture until the pointer stops moving.
  handle.addEventListener('click', () => {
    if (!media.matches) return;
    setOpen(!open);
  });

  const setOpen = (next: boolean): void => {
    open = next;
    element.dataset.open = String(open);
    if (media.matches) handle.setAttribute('aria-expanded', String(open));
  };

  media.addEventListener('change', () => {
    // Crossing the breakpoint collapses the sheet: a panel that was a column a moment ago
    // would otherwise reappear covering the map it was sitting beside.
    open = false;
    applyMode();
  });

  applyMode();

  return {
    isSheet: () => media.matches,
    setOpen,
    isOpen: () => open,
    setTitle: (title: string) => {
      const slot = handle.querySelector('.panel-title');
      if (slot) slot.textContent = title;
    },
    setLabels: (resize: string, help: string) => {
      handle.setAttribute('aria-label', resize);
      handle.title = help;
    },
    reset: () => setWidth(defaultWidth),
    onResize: (handler) => {
      resizeHandlers.push(handler);
      handler(width);
    },
  };
}
