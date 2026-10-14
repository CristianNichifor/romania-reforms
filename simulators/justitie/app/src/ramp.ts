/**
 * The five-step ramp the map grades with: blue (well under) through a pale middle to orange (well
 * over). It replaced a green-to-red ramp whose ends merge under red-green colour blindness;
 * ramp.test.ts simulates both deficiencies. The legend reads the same colours from tokens.css,
 * and the test keeps the two in step, because a MapLibre expression cannot read a CSS variable.
 */
export const RAMP: readonly [string, string, string, string, string] = [
  '#3b6fb6',
  '#8fb8de',
  '#e8e2c8',
  '#e8a05a',
  '#b35806',
];
