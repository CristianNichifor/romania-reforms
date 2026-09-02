/**
 * The test that would have caught a blank map.
 *
 * The paint expression was malformed for the whole life of the page and nothing noticed:
 * MapLibre rejected it, `addLayer` threw, the map drew nothing, and every check that existed —
 * a build that succeeded, a typecheck that passed, HTTP 200 on the data files — went on saying
 * the deploy was fine. These assertions run the expression through the same parser MapLibre
 * uses, so a broken one fails the build instead of the page.
 */
import { createExpression, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { describe, expect, it } from 'vitest';

import {
  BANDS,
  NO_DATA,
  RAIL_UNTAGGED,
  SPEED_BANDS,
  SPEED_UNTAGGED,
  journeyPaint,
  railLinePaint,
  railLineWidth,
  roadSpeedPaint,
  roadSpeedWidth,
  stationRadius,
} from './paint';

const COLOUR_SPEC = {
  type: 'color',
  'property-type': 'data-driven',
  expression: { interpolated: true, parameters: ['zoom', 'feature'] },
} as const;

function compile(key: 'u' | 'p') {
  const result = createExpression(journeyPaint(key), COLOUR_SPEC as never);
  if (result.result === 'error') {
    throw new Error(result.value.map((e: { message: string }) => e.message).join(' | '));
  }
  return (minutes: number) =>
    String(
      result.value.evaluate({ zoom: 6 }, {
        type: 'Feature',
        properties: { [key]: minutes },
      } as never),
    );
}

describe('journey paint expression', () => {
  it('parses — the assertion the blank map needed', () => {
    expect(() => compile('u')).not.toThrow();
    expect(() => compile('p')).not.toThrow();
  });

  it('gives a commune its own band rather than the one below', () => {
    const paint = compile('u');
    expect(paint(10)).toBe(BANDS[0].colour);
    expect(paint(50)).toBe(BANDS[1].colour);
    expect(paint(75)).toBe(BANDS[2].colour);
    expect(paint(100)).toBe(BANDS[3].colour);
    expect(paint(200)).toBe(BANDS[4].colour);
  });

  it('does not paint a fast commune as missing data', () => {
    // The specific old bug: NO_DATA was the base output, so everything under 45 minutes — the
    // best-served communes in the country — rendered as "no route at all".
    expect(compile('u')(10)).not.toBe(NO_DATA);
  });

  it('puts a boundary value in the upper band', () => {
    // `step` switches at the stop, so exactly 45 belongs to the 45–60 band, matching the
    // legend's "sub 45 min" for the one below it.
    expect(compile('u')(45)).toBe(BANDS[1].colour);
    expect(compile('u')(44.9)).toBe(BANDS[0].colour);
  });

  it('marks a UAT with no journey as missing rather than fast', () => {
    // Unroutable UATs carry -1. Without the guard they would fall in the base band and the
    // delta communes would read as the best-connected places in Romania.
    expect(compile('u')(-1)).toBe(NO_DATA);
  });

  it('reads the same for both timetable scenarios', () => {
    expect(compile('p')(75)).toBe(compile('u')(75));
  });

  it('has a band for every legend row and an unbounded last one', () => {
    expect(BANDS.length).toBeGreaterThan(1);
    expect(BANDS[BANDS.length - 1].upTo).toBe(Infinity);
    for (let i = 1; i < BANDS.length; i += 1) {
      expect(BANDS[i].upTo).toBeGreaterThan(BANDS[i - 1].upTo);
    }
  });
});

describe('rail layer expressions', () => {
  const compileColour = (expr: unknown) => {
    const r = createExpression(expr, COLOUR_SPEC as never);
    if (r.result === 'error') {
      throw new Error(r.value.map((e: { message: string }) => e.message).join(' | '));
    }
    return (speed: number) =>
      String(
        r.value.evaluate({ zoom: 6 }, { type: 'Feature', properties: { maxspeed: speed } } as never),
      );
  };

  it('the rail colour expression parses — the same trap, one layer over', () => {
    expect(() => compileColour(railLinePaint())).not.toThrow();
  });

  it('colours a line by the CFR band its speed falls in', () => {
    const paint = compileColour(railLinePaint());
    expect(paint(40)).toBe(BANDS[4].colour);
    expect(paint(80)).toBe(BANDS[3].colour);
    expect(paint(100)).toBe(BANDS[1].colour);
    expect(paint(160)).toBe(BANDS[0].colour);
  });

  it('shows an untagged line as unknown rather than as slow', () => {
    // Most of the network carries no maxspeed. Painting absence as "worst band" would invent
    // a measurement, and on a map that reads as a finding.
    expect(compileColour(railLinePaint())(-1)).toBe(RAIL_UNTAGGED);
  });

  it('the zoom interpolations parse', () => {
    const numberSpec = {
      type: 'number',
      'property-type': 'data-driven',
      expression: { interpolated: true, parameters: ['zoom', 'feature'] },
    };
    for (const expr of [railLineWidth(), stationRadius()]) {
      const r = createExpression(expr, numberSpec as never);
      expect(r.result).toBe('success');
    }
  });
});

describe('the whole style', () => {
  it('is accepted by the validator MapLibre itself runs', () => {
    // The check that would have caught this in one line. Expression-level tests guard the
    // expressions; this guards the layers they sit in, which is where the failure surfaced:
    // "layers[0].paint.fill-color[3]: Expected an even number of arguments."
    const geo = { type: 'geojson', data: { type: 'FeatureCollection', features: [] } };
    const errors = validateStyleMin({
      version: 8,
      sources: { uats: geo, counties: geo, rail: geo, stations: geo, speeds: geo },
      layers: [
        {
          id: 'uat-fill',
          type: 'fill',
          source: 'uats',
          paint: { 'fill-color': journeyPaint('u'), 'fill-opacity': 0.85 },
        },
        {
          id: 'rail-line',
          type: 'line',
          source: 'rail',
          paint: { 'line-color': railLinePaint(), 'line-width': railLineWidth() },
        },
        {
          id: 'station-dot',
          type: 'circle',
          source: 'stations',
          paint: { 'circle-radius': stationRadius(), 'circle-color': '#e8eaf0' },
        },
        {
          id: 'speeds-line',
          type: 'line',
          source: 'speeds',
          paint: { 'line-color': roadSpeedPaint(), 'line-width': roadSpeedWidth() },
        },
      ],
    } as never);
    expect(errors.map((e: { message: string }) => e.message)).toEqual([]);
  });
});

describe('road speed-limit layer', () => {
  const compile = (expr: unknown) => {
    const r = createExpression(expr, COLOUR_SPEC as never);
    if (r.result === 'error') {
      throw new Error(r.value.map((e: { message: string }) => e.message).join(' | '));
    }
    return (kmh: number) =>
      String(r.value.evaluate({ zoom: 6 }, { type: 'Feature', properties: { kmh } } as never));
  };

  it('parses — the trap that once left the whole map blank', () => {
    expect(() => compile(roadSpeedPaint())).not.toThrow();
  });

  it('puts the two limits Romania actually signs either side of a boundary', () => {
    // 50 through villages and 90 on the open road are 38% and 21% of these kilometres. If they
    // ever shared a colour the layer would stop showing the thing it exists to show.
    const paint = compile(roadSpeedPaint());
    expect(paint(50)).not.toBe(paint(90));
    expect(paint(50)).toBe(SPEED_BANDS[3].colour);
    expect(paint(90)).toBe(SPEED_BANDS[1].colour);
  });

  it('colours each band from its own floor upward', () => {
    const paint = compile(roadSpeedPaint());
    expect(paint(30)).toBe(SPEED_BANDS[4].colour);
    expect(paint(49)).toBe(SPEED_BANDS[4].colour);
    expect(paint(70)).toBe(SPEED_BANDS[2].colour);
    expect(paint(130)).toBe(SPEED_BANDS[0].colour);
  });

  it('draws an untagged road as unknown, not as the slowest in the country', () => {
    // 21 626 km carry no maxspeed, concentrated on small roads. Without the guard, -1 falls
    // into the bottom step and a quarter of the network reads as a finding about its speed.
    expect(compile(roadSpeedPaint())(-1)).toBe(SPEED_UNTAGGED);
    expect(compile(roadSpeedPaint())(-1)).not.toBe(SPEED_BANDS[4].colour);
  });

  it('blue stays the good end, as on the journey and rail layers', () => {
    // A reader switching layers reads the colour before the legend.
    const paint = compile(roadSpeedPaint());
    expect(paint(130)).toBe(BANDS[0].colour);
    expect(paint(30)).toBe(BANDS[4].colour);
  });

  it('the width interpolation parses', () => {
    const numberSpec = {
      type: 'number',
      'property-type': 'data-driven',
      expression: { interpolated: true, parameters: ['zoom', 'feature'] },
    };
    expect(createExpression(roadSpeedWidth(), numberSpec as never).result).toBe('success');
  });
});
