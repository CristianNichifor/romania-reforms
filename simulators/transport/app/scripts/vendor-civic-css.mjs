import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const release = 'https://github.com/CristianNichifor/civic-ui/releases/download/v0.2.0/civic-ui-0.2.0.tgz';
const sha256 = '9a78cb63fd9885febc5aa94eefbb3647f7dd5841fda5e7a6b2e78192b3d0c802';
const files = ['dist/styles.css', 'dist/foundations.css', 'dist/controls.css', 'LICENSE'];
const destination = new URL('../src/vendor/civic-ui/', import.meta.url);
const digest = data => createHash('sha256').update(data).digest('hex');

if (process.argv.includes('--update')) {
  const response = await fetch(release);
  assert.ok(response.ok, `Release download failed: ${response.status}`);
  const archive = Buffer.from(await response.arrayBuffer());
  assert.equal(digest(archive), sha256, 'Release archive checksum');
  const temporary = await mkdtemp(join(tmpdir(), 'land-civic-css-'));
  try {
    const path = join(temporary, 'release.tgz');
    await writeFile(path, archive);
    const hashes = {};
    await mkdir(destination, { recursive: true });
    for (const file of files) {
      // Read only the selected members, never extract archive paths onto the filesystem.
      const data = execFileSync('tar', ['-xOf', path, `package/${file}`]);
      const name = file.split('/').at(-1);
      hashes[name] = digest(data);
      await writeFile(new URL(name, destination), data);
    }
    await writeFile(new URL('provenance.json', destination), JSON.stringify({ release, sha256, files: hashes }, null, 2) + '\n');
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

const provenance = JSON.parse(await readFile(new URL('provenance.json', destination), 'utf8'));
assert.equal(provenance.release, release);
assert.equal(provenance.sha256, sha256);
assert.deepEqual(Object.keys(provenance.files).sort(), files.map(file => file.split('/').at(-1)).sort());
for (const [name, hash] of Object.entries(provenance.files)) {
  assert.equal(digest(await readFile(new URL(name, destination))), hash, `Vendored file changed: ${name}`);
}
console.log('Civic UI CSS provenance checks passed (no network needed for verification).');
