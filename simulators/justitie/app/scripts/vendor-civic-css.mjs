import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const release = 'https://github.com/CristianNichifor/civic-ui/releases/download/v0.4.0/civic-ui-css-0.4.0.tgz';
const sha256 = '269dc6d01f4da09707521229111ac55011f78f55518a7c8d73d660503ed84de7';
const files = ['native.css', 'styles.css', 'foundations.css', 'controls.css', 'LICENSE', 'NATIVE.md'];
const destination = new URL('../src/vendor/civic-ui/', import.meta.url);
const digest = data => createHash('sha256').update(data).digest('hex');

if (process.argv.includes('--update')) {
  const response = await fetch(release);
  assert.ok(response.ok, `Release download failed: ${response.status}`);
  const archive = Buffer.from(await response.arrayBuffer());
  assert.equal(digest(archive), sha256, 'Release archive checksum');
  const temporary = await mkdtemp(join(tmpdir(), 'justice-civic-css-'));
  try {
    const path = join(temporary, 'release.tgz');
    await writeFile(path, archive);
    const hashes = {};
    await mkdir(destination, { recursive: true });
    for (const name of files) {
      // Select known archive members instead of extracting arbitrary archive paths.
      const data = execFileSync('tar', ['-xOf', path, name]);
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
assert.deepEqual(Object.keys(provenance.files).sort(), [...files].sort());
for (const [name, hash] of Object.entries(provenance.files)) {
  assert.equal(digest(await readFile(new URL(name, destination))), hash, `Vendored file changed: ${name}`);
}
console.log('Civic UI CSS provenance verified without network access.');
