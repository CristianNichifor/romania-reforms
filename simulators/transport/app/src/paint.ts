/**
 * The colour bands, and the MapLibre expression that applies them.
 *
 * Extracted from `main.ts` after the expression turned out to be malformed — not subtly, but
 * "MapLibre refuses to parse it and the entire map renders as bare background", for as long as
 * the page had existed. It survived because nothing could see it: the expression was built
 * inline inside `main()`, the failure surfaced only as a rejected promise in the browser, and
 * the deploy check verified that the data files returned HTTP 200. Files existing is not a map.
 *
 * So the bands and the expression live here, where a test can hand them to the same parser
 * MapLibre uses and assert both that it parses and that a journey time lands in the band a
 * reader would expect.
 */

/** One band of journey time, and the colour a commune in it takes. */
export interface Band {
  /** Upper bound in minutes, exclusive. The last band is unbounded. */
  upTo: number;
  colour: string;
  label: string;
}

/**
 * RdYlBu, not RdYlGn. The previous ramp ran green→red, which ColorBrewer marks as *not*
 * colour-blind safe: to the ~8% of men with deuteranopia or protanopia its two ends are the
 * same colour, and on this map the ends carry the whole meaning — "twenty minutes to your
 * county seat" against "two hours". Blue for green keeps it legible under every common
 * deficiency and ordered in greyscale. The popup states the number as the real backstop.
 */
export const BANDS: Band[] = [
  { upTo: 45, colour: '#2c7bb6', label: 'sub 45 min' },
  { upTo: 60, colour: '#abd9e9', label: '45–60 min' },
  { upTo: 90, colour: '#ffffbf', label: '60–90 min' },
  { upTo: 120, colour: '#fdae61', label: '90–120 min' },
  { upTo: Infinity, colour: '#d7191c', label: 'peste 120 min' },
];

/** A UAT with no journey at all — the delta communes, and Bucharest. */
export const NO_DATA = '#3a3f4d';

/**
 * Paint expression for one journey-time property.
 *
 * MapLibre's step is `["step", input, base, stop1, out1, stop2, out2, …]`: the base is the
 * output *below* the first stop, and everything after it comes in pairs. The version this
 * replaces passed NO_DATA as the base — painting every commune under 45 minutes grey — and then
 * appended the final colour as a lone trailing element, leaving an odd argument count that
 * MapLibre rejects outright.
 */
/**
 * Road colours, taken from the administrative map rather than reinvented — the two pages show
 * the same country and a reader moving between them should not have to relearn what a road
 * looks like. Its reasoning applies here unchanged: every hue is spoken for by the journey
 * bands, so roads separate by brightness instead, a bright core over a dark casing.
 */
export const ROAD_COLOUR = '#ffffff';
export const ROAD_COUNTY_COLOUR = '#9fc6ef';
export const ROAD_CASING_COLOUR = '#0a0d11';

/** National roads: width by class, so the hierarchy survives zooming out. */
export function majorRoadWidth(): unknown {
  return [
    'interpolate',
    ['linear'],
    ['zoom'],
    6,
    ['match', ['get', 'highway'], 'motorway', 2.2, 'trunk', 1.7, 1.1],
    11,
    ['match', ['get', 'highway'], 'motorway', 4.6, 'trunk', 3.6, 2.4],
  ];
}

/** County and communal roads: thinner, and faint until the reader zooms in. */
export function countyRoadWidth(): unknown {
  return ['interpolate', ['linear'], ['zoom'], 6, 0.7, 9, 1.5, 12, 2.6];
}

export function countyRoadOpacity(): unknown {
  return ['interpolate', ['linear'], ['zoom'], 6, 0.6, 9, 0.85, 12, 0.95];
}

export function countyRoadCasingOpacity(): unknown {
  return ['interpolate', ['linear'], ['zoom'], 6, 0.35, 9, 0.6];
}

/** A line whose speed OSM never recorded. Grey, not "slow" — absence is not a measurement. */
export const RAIL_UNTAGGED = '#6b7280';

/**
 * Rail line colour by signed speed, using CFR's own tariff bands (A 121–160, B 91–120,
 * C 51–90, D under 50). Same ramp as the journey map so the two read together.
 */
export function railLinePaint(): unknown {
  return [
    'case',
    ['<', ['get', 'maxspeed'], 0],
    RAIL_UNTAGGED,
    ['step', ['get', 'maxspeed'], BANDS[4].colour, 51, BANDS[3].colour, 91, BANDS[1].colour, 121, BANDS[0].colour],
  ];
}

/** Line width, thickening as the reader zooms in. */
export function railLineWidth(): unknown {
  return ['interpolate', ['linear'], ['zoom'], 6, 1.1, 10, 2.6];
}

/** Station dot radius, likewise. */
export function stationRadius(): unknown {
  return ['interpolate', ['linear'], ['zoom'], 6, 1.6, 11, 4];
}

export function journeyPaint(key: 'u' | 'p'): unknown {
  const steps: unknown[] = ['step', ['get', key], BANDS[0].colour];
  for (let i = 1; i < BANDS.length; i += 1) {
    steps.push(BANDS[i - 1].upTo, BANDS[i].colour);
  }
  return ['case', ['<', ['get', key], 0], NO_DATA, steps];
}

/**
 * Road colour by signed speed limit, for the `road-speeds.geojson` overlay.
 *
 * Same ramp as the journey map and the rail lines, and in the same direction: blue is the good
 * end. On the journey map that means few minutes; here it means a high limit. Keeping the
 * *meaning* of blue constant across three layers matters more than keeping the arithmetic
 * constant, because a reader switching layers reads the colour before the legend.
 *
 * The bands are chosen around what Romania actually signs — 50 through villages and 90 on the
 * open road are 38% and 21% of these kilometres between them — so the two dominant values fall
 * either side of a boundary and the village-versus-country pattern separates on sight.
 *
 * Untagged is `-1`, guarded before the step. A step expression has no concept of "missing":
 * without the guard, -1 would fall into the lowest band and 21 626 km of unrecorded road would
 * be drawn as the slowest in the country.
 */
export const SPEED_UNTAGGED = RAIL_UNTAGGED;

export interface SpeedBand {
  /** Lower bound in km/h, inclusive. */
  from: number;
  colour: string;
  label: string;
}

export const SPEED_BANDS: SpeedBand[] = [
  { from: 110, colour: BANDS[0].colour, label: '110+ km/h' },
  { from: 90, colour: BANDS[1].colour, label: '90–109 km/h' },
  { from: 70, colour: BANDS[2].colour, label: '70–89 km/h' },
  { from: 50, colour: BANDS[3].colour, label: '50–69 km/h' },
  { from: 0, colour: BANDS[4].colour, label: 'sub 50 km/h' },
];

export function roadSpeedPaint(): unknown {
  // Ascending stops, so the bands are reversed against the legend's fastest-first order.
  const ascending = [...SPEED_BANDS].reverse();
  const steps: unknown[] = ['step', ['get', 'kmh'], ascending[0].colour];
  for (let i = 1; i < ascending.length; i += 1) {
    steps.push(ascending[i].from, ascending[i].colour);
  }
  return ['case', ['<', ['get', 'kmh'], 0], SPEED_UNTAGGED, steps];
}

/** Thicker than the plain road layers: this one carries the information, not the context. */
export function roadSpeedWidth(): unknown {
  return ['interpolate', ['linear'], ['zoom'], 6, 1.1, 9, 2.2, 12, 3.6];
}
