/**
 * The parts of the panel chrome that can be wrong without looking wrong.
 *
 * The drag wiring itself needs a DOM and this project's test environment is node, so what is
 * covered here is the arithmetic and the parsing — which is where the bugs that survive a
 * screenshot live. A panel that drags the wrong way is obvious the first time anyone tries
 * it; a stored width of 0 that clamps up to the minimum and reads as a choice is not.
 */

import { describe, expect, it } from 'vitest';

import { budgetUrlFor } from '../src/app/links';
import {
  MAX_WIDTH_PX,
  MIN_WIDTH_PX,
  clampWidth,
  parseStoredWidth,
  widthAfterDrag,
} from '../src/app/panels';

describe('panel width', () => {
  it('holds a width inside the band unchanged', () => {
    expect(clampWidth(320)).toBe(320);
  });

  it('clamps rather than refusing, at both ends', () => {
    expect(clampWidth(10)).toBe(MIN_WIDTH_PX);
    expect(clampWidth(5000)).toBe(MAX_WIDTH_PX);
  });

  it('rounds to whole pixels, because a fractional width blurs the text in it', () => {
    expect(clampWidth(320.4)).toBe(320);
    expect(clampWidth(320.6)).toBe(321);
  });
});

describe('a width restored from storage', () => {
  it('reads back a width somebody chose', () => {
    expect(parseStoredWidth('412')).toBe(412);
  });

  it('is absent rather than zero when the entry is missing or empty', () => {
    // Number('') is 0, which would clamp up to the minimum and be indistinguishable from a
    // width the reader picked. Absent has to stay absent.
    expect(parseStoredWidth(null)).toBeNull();
    expect(parseStoredWidth('')).toBeNull();
    expect(parseStoredWidth('   ')).toBeNull();
  });

  it('discards a value that is not a number', () => {
    expect(parseStoredWidth('wide please')).toBeNull();
    expect(parseStoredWidth('NaN')).toBeNull();
    expect(parseStoredWidth('Infinity')).toBeNull();
  });

  it('clamps a stored value that is out of band', () => {
    expect(parseStoredWidth('9000')).toBe(MAX_WIDTH_PX);
    expect(parseStoredWidth('-40')).toBe(MIN_WIDTH_PX);
  });
});

describe('dragging a panel edge', () => {
  it('grows the left-hand panel when the pointer moves right', () => {
    expect(widthAfterDrag('right', 400, 60)).toBe(460);
    expect(widthAfterDrag('right', 400, -60)).toBe(340);
  });

  it('grows the right-hand panel when the pointer moves left', () => {
    // The sign flip: the detail panel is anchored to the right edge, so a leftward drag
    // makes it wider. Getting this backwards makes the panel shrink as you pull it open.
    expect(widthAfterDrag('left', 400, -60)).toBe(460);
    expect(widthAfterDrag('left', 400, 60)).toBe(340);
  });

  it('stops at the band rather than running past it', () => {
    expect(widthAfterDrag('right', 540, 400)).toBe(MAX_WIDTH_PX);
    expect(widthAfterDrag('left', 280, 400)).toBe(MIN_WIDTH_PX);
  });
});

describe('the transparenta.eu link', () => {
  it('builds the entity URL from the id the pipeline ships', () => {
    // Municipiul Sibiu, verified against the live site on 2026-09-07.
    expect(budgetUrlFor('4270740')).toBe('https://www.transparenta.eu/entities/4270740');
  });

  it('has no link where the payload has no id', () => {
    // A payload built before `uatCode` existed, and a UAT the source has no entity for.
    // Both must render as plain text rather than as a link to nowhere.
    expect(budgetUrlFor(undefined)).toBeNull();
    expect(budgetUrlFor(null)).toBeNull();
    expect(budgetUrlFor('')).toBeNull();
  });

  it('refuses an id that is not numeric', () => {
    // The ids are numeric; anything else is the payload disagreeing with its own schema,
    // and it is about to be interpolated into an href.
    expect(budgetUrlFor('4270740" onmouseover="x')).toBeNull();
    expect(budgetUrlFor('../../admin')).toBeNull();
  });
});
