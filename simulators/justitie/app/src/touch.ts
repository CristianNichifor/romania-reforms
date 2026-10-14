/**
 * The map's hint, worded for the pointer the reader has. A tap selects a feature just as a hover
 * does (the browser sends the mouse events for it), but "treci cu mouse-ul" asks a phone reader
 * for something they cannot do.
 */
export function pointHint(noun: string): string {
  const touch = typeof matchMedia === 'function' && matchMedia('(hover: none)').matches;
  return touch ? `Atinge ${noun}.` : `Treci cu mouse-ul peste ${noun}.`;
}
