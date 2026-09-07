/**
 * Saved versions.
 *
 * The failure that matters here is not a crash but a quiet loss: a reader who saved four maps
 * and finds three, or who imports a file and loses what they had. So the tests lean on the
 * boundaries — corrupt storage, a stranger's JSON, a name saved twice — rather than on the
 * happy path, which is one line.
 */

import { describe, expect, it } from 'vitest';

import {
  EXPORT_FORMAT,
  exportFilename,
  mergeImported,
  parseImport,
  parseVersions,
  removeVersion,
  serialiseVersions,
  toExportFile,
  upsertVersion,
  type SavedVersion,
} from '../src/app/versions';

const version = (name: string, hash = 'x=9000', units = 250): SavedVersion => ({
  name,
  savedAt: '2026-09-07T10:00:00.000Z',
  hash,
  units,
});

describe('reading versions out of storage', () => {
  it('round-trips', () => {
    const list = [version('Varianta A'), version('Fără prag')];
    expect(parseVersions(serialiseVersions(list))).toEqual(list);
  });

  it('treats absent storage as no versions', () => {
    expect(parseVersions(null)).toEqual([]);
    expect(parseVersions('')).toEqual([]);
  });

  it('degrades to no versions rather than throwing on corrupt storage', () => {
    // Called during boot. Throwing here would replace the map with a blank screen over a
    // feature the reader had not even used yet.
    expect(parseVersions('{ not json')).toEqual([]);
    expect(parseVersions('"a string"')).toEqual([]);
    expect(parseVersions('{"versions":[]}')).toEqual([]);
  });

  it('keeps the readable entries and drops only the broken ones', () => {
    const raw = JSON.stringify([
      version('good'),
      { name: '', savedAt: 'x', hash: 'y', units: null },
      { name: 'no hash', savedAt: 'x', units: 1 },
      { name: 'bad units', savedAt: 'x', hash: 'y', units: 'lots' },
      { ...version('units may be null'), units: null },
    ]);
    expect(parseVersions(raw).map((v) => v.name)).toEqual(['good', 'units may be null']);
  });
});

describe('saving under a name', () => {
  it('puts the newest first', () => {
    const list = upsertVersion([version('first')], version('second'));
    expect(list.map((v) => v.name)).toEqual(['second', 'first']);
  });

  it('replaces rather than duplicating when a name is reused', () => {
    // Two rows called "Varianta A" cannot be told apart, so saving over it is the intent.
    const list = upsertVersion([version('Varianta A', 'old')], version('Varianta A', 'new'));
    expect(list).toHaveLength(1);
    expect(list[0]!.hash).toBe('new');
  });

  it('matches names case- and whitespace-insensitively', () => {
    const list = upsertVersion([version('Varianta A')], version('  varianta a  ', 'new'));
    expect(list).toHaveLength(1);
    expect(list[0]!.hash).toBe('new');
  });

  it('removes by name the same way', () => {
    expect(removeVersion([version('A'), version('B')], ' a ')).toHaveLength(1);
  });
});

describe('importing a file', () => {
  it('round-trips an export', () => {
    const list = [version('A'), version('B')];
    const file = toExportFile(list, '2026-09-07T10:00:00.000Z');
    expect(file.format).toBe(EXPORT_FORMAT);
    expect(parseImport(JSON.stringify(file))).toEqual(list);
  });

  it("refuses a file that is not ours rather than mining it", () => {
    // Silently importing whatever in a stranger's JSON looks version-shaped is how this
    // feature becomes a way to overwrite somebody's saved work.
    expect(parseImport('{"versions":[{"name":"a","savedAt":"b","hash":"c","units":1}]}')).toBeNull();
    expect(parseImport('[]')).toBeNull();
    expect(parseImport('not json at all')).toBeNull();
    expect(parseImport(JSON.stringify({ format: 'something-else', version: 1, versions: [] }))).toBeNull();
  });

  it('refuses a file with no schema version', () => {
    expect(parseImport(JSON.stringify({ format: EXPORT_FORMAT, versions: [] }))).toBeNull();
  });

  it('drops unusable entries but keeps the file', () => {
    const file = { format: EXPORT_FORMAT, version: 1, exported: 'x', versions: [version('ok'), { name: 'bad' }] };
    expect(parseImport(JSON.stringify(file))?.map((v) => v.name)).toEqual(['ok']);
  });

  it('merges into what is already saved, the import winning a name clash', () => {
    const merged = mergeImported([version('A', 'mine'), version('B', 'mine')], [version('A', 'theirs')]);
    expect(merged).toHaveLength(2);
    expect(merged.find((v) => v.name === 'A')!.hash).toBe('theirs');
    expect(merged.find((v) => v.name === 'B')!.hash).toBe('mine');
  });
});

describe('the export filename', () => {
  it('carries the date so two exports do not look identical', () => {
    expect(exportFilename('2026-09-07T10:00:00.000Z')).toBe('administrativ-versiuni-2026-09-07.json');
  });
});
