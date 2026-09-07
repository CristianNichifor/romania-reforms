/**
 * The published map.
 *
 * A visitor arriving at a bare URL should see a map somebody stands behind, not whatever the
 * sliders happen to default to. Those are different claims, and only the author can make the
 * second one — so this file holds the scenario they chose, and `published` says whether they
 * have chosen one yet.
 *
 * **While `published` is false the app behaves exactly as it did before**: the defaults load,
 * unbadged, and nothing claims to be a reference. That is deliberate. Badging the defaults as
 * a considered proposal would put words in the author's mouth, and this is a tool whose whole
 * value rests on not doing that.
 *
 * To publish: tune the map in the browser, copy the URL, and paste its hash into `hash` below
 * with a version and a date. The scenario is decoded from that string rather than transcribed
 * field by field, so what ships is exactly the map that was looked at.
 */

import type { Params, Pin, ViewMode } from '../model/types';

export interface Reference {
  /** False until an author has chosen a map. Nothing is badged while it is false. */
  published: boolean;
  /** Shown beside the badge, e.g. "v1". */
  version: string;
  /** ISO date the scenario was settled, shown to the reader. */
  date: string;
  /**
   * The scenario's URL hash, exactly as copied from the address bar.
   *
   * Stored as the hash rather than as decoded fields so there is one format, one decoder and
   * one thing to get wrong — and so a published map can be reproduced by pasting the string
   * back into a browser.
   */
  hash: string;
}

/**
 * Whether two scenarios describe the same map.
 *
 * Language and selection are deliberately excluded. Reading the reference map in English, or
 * clicking a commune to see its figures, does not make it your version of the map — and a
 * badge that flipped on either would be crying wolf, which is worse than no badge.
 */
export function sameMap(a: ComparableScenario, b: ComparableScenario): boolean {
  if (a.mode !== b.mode) return false;
  const keys = Object.keys(a.params) as (keyof Params)[];
  if (keys.some((key) => a.params[key] !== b.params[key])) return false;
  if (a.forced.length !== b.forced.length) return false;
  if (a.forced.some((v, i) => v !== b.forced[i])) return false;
  if (a.pins.length !== b.pins.length) return false;
  return a.pins.every((pin, i) => pin.uat === b.pins[i]?.uat && pin.seat === b.pins[i]?.seat);
}

export interface ComparableScenario {
  params: Params;
  mode: ViewMode;
  pins: Pin[];
  forced: number[];
}

export const REFERENCE: Reference = {
  published: false,
  version: 'v1',
  date: '',
  hash: '',
};
