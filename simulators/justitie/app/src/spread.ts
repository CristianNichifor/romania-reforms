/**
 * Courts that share an address — the appellate court, the tribunal and the judecătorie of a
 * county seat sit in the same courthouse, and București stacks four — are located at one
 * point, so their circles paint on top of one another and only the largest shows.
 *
 * The largest stays where the courthouse is; the others step out onto a small ring around it,
 * ordered by volume, so each is a separate, hoverable circle. The ring is a presentation
 * offset of a few kilometres, not a relocation: a court never moves out of its town.
 */

/** Radius of the ring, in degrees of latitude: about 3 km, a few pixels at the national zoom. */
export const SPREAD_DEGREES = 0.03;

export type Spreadable = { point: [number, number]; volume: number };

const key = (p: [number, number]): string => `${p[0]},${p[1]}`;

/** The same items, with coincident points spread onto a ring. Order is preserved. */
export const spread = <T extends Spreadable>(items: T[]): T[] => {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item.point);
    const g = groups.get(k);
    if (g) g.push(item);
    else groups.set(k, [item]);
  }
  const moved = new Map<T, [number, number]>();
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const byVolume = [...group].sort((a, b) => b.volume - a.volume);
    const [lon, lat] = byVolume[0]!.point;
    const ring = byVolume.slice(1);
    const stretch = 1 / Math.max(Math.cos((lat * Math.PI) / 180), 0.2);
    ring.forEach((item, i) => {
      const angle = (2 * Math.PI * i) / ring.length - Math.PI / 2;
      moved.set(item, [
        lon + Math.cos(angle) * SPREAD_DEGREES * stretch,
        lat + Math.sin(angle) * SPREAD_DEGREES,
      ]);
    });
  }
  return items.map((item) => {
    const p = moved.get(item);
    return p ? { ...item, point: p } : item;
  });
};
