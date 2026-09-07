/**
 * Maps a reader has saved.
 *
 * A version is stored as its **URL hash** and nothing else. The hash already encodes every
 * parameter, every override and the view mode, and it is already the format the address bar,
 * the reference map and a shared link all speak — so a saved version, an exported file and a
 * pasted link are the same thing in three places rather than three formats to keep in step.
 *
 * The parsing here is deliberately forgiving in one direction and strict in the other. What
 * comes out of localStorage is treated as possibly corrupt and degrades to "no versions"
 * rather than throwing, because losing a saved list should not lose the map. What comes out
 * of an imported file is checked before it is trusted, because that is somebody else's data.
 */

export interface SavedVersion {
  name: string;
  /** ISO timestamp. */
  savedAt: string;
  /** The scenario, as a URL hash without its leading `#`. */
  hash: string;
  /** Resulting unit count when it was saved, so the list means something at a glance. */
  units: number | null;
}

export const STORAGE_KEY = 'administrativ:versions';

/** Marks an export as ours, so a wrong file is refused rather than half-read. */
export const EXPORT_FORMAT = 'administrativ-versions';
export const EXPORT_VERSION = 1;

export interface VersionsFile {
  format: typeof EXPORT_FORMAT;
  version: number;
  exported: string;
  versions: SavedVersion[];
}

function isVersion(value: unknown): value is SavedVersion {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.name === 'string' &&
    v.name.trim() !== '' &&
    typeof v.hash === 'string' &&
    typeof v.savedAt === 'string' &&
    (v.units === null || typeof v.units === 'number')
  );
}

/**
 * Versions out of storage. Anything unreadable yields an empty list.
 *
 * A half-written or hand-edited entry costs the reader that entry, not the page: this is
 * called during boot, and throwing here would replace the map with a blank screen over a
 * feature nobody had asked for yet.
 */
export function parseVersions(raw: string | null): SavedVersion[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isVersion);
  } catch {
    return [];
  }
}

export function serialiseVersions(versions: SavedVersion[]): string {
  return JSON.stringify(versions);
}

/**
 * Save under a name, replacing any version already using it.
 *
 * Names are the reader's handle on their own work, so saving "Varianta A" twice should update
 * it rather than leave two rows that cannot be told apart. Most recent first.
 */
export function upsertVersion(versions: SavedVersion[], next: SavedVersion): SavedVersion[] {
  const key = next.name.trim().toLowerCase();
  return [next, ...versions.filter((v) => v.name.trim().toLowerCase() !== key)];
}

export function removeVersion(versions: SavedVersion[], name: string): SavedVersion[] {
  const key = name.trim().toLowerCase();
  return versions.filter((v) => v.name.trim().toLowerCase() !== key);
}

export function toExportFile(versions: SavedVersion[], exportedAt: string): VersionsFile {
  return {
    format: EXPORT_FORMAT,
    version: EXPORT_VERSION,
    exported: exportedAt,
    versions,
  };
}

/**
 * Versions out of a file the reader chose, or null if it is not one of ours.
 *
 * Strict where `parseVersions` is forgiving: a file that does not announce itself as this
 * format is refused outright rather than mined for anything that happens to look like a
 * version. Silently importing half of a stranger's JSON is how a feature like this becomes a
 * way to break somebody's saved work.
 */
export function parseImport(text: string): SavedVersion[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null) return null;
  const file = parsed as Record<string, unknown>;
  if (file.format !== EXPORT_FORMAT) return null;
  // A newer file may carry fields this build does not know about; that is survivable, and
  // the per-entry check below decides what is actually usable. An older or unnumbered file
  // is not something to guess at.
  if (typeof file.version !== 'number') return null;
  if (!Array.isArray(file.versions)) return null;
  return file.versions.filter(isVersion);
}

/** Merge imported versions into the stored ones, imported entries winning on a name clash. */
export function mergeImported(
  existing: SavedVersion[],
  imported: SavedVersion[],
): SavedVersion[] {
  return imported.reduce((list, version) => upsertVersion(list, version), existing);
}

/**
 * A filename a person can find again.
 *
 * Diacritics and spaces survive a download on every platform this runs on, but a slash does
 * not, and neither does a name long enough to be truncated by the filesystem.
 */
export function exportFilename(now: string): string {
  const date = now.slice(0, 10);
  return `administrativ-versiuni-${date}.json`;
}
