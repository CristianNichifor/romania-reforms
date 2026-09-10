import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const packageName = '@cristiannichifor/civic-ui';
const artifact = 'https://github.com/CristianNichifor/civic-ui/releases/download/v0.3.0/civic-ui-0.3.0.tgz';
const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
assert.equal(manifest.dependencies[packageName], artifact, 'Civic UI must use the reviewed public release');
assert.equal(lock.packages[''].dependencies[packageName], artifact, 'Root lock must match the manifest');
const dependency = lock.packages[`node_modules/${packageName}`];
assert.equal(dependency.version, '0.3.0');
assert.equal(dependency.resolved, artifact);
// Checked against the SHA256SUMS published with the release, not copied out of the lockfile:
// 83cb4244c2ef1154cd4e2d86c621d30ddfae803eff6da20b9c092b000880814b  civic-ui-0.3.0.tgz
// A hash taken from the lockfile only proves npm downloaded the same thing twice.
assert.equal(dependency.integrity, 'sha512-1en/v9AOp2Yk9dvzSSbmHceYB1PyDkVcPxkXq81FViyLm0D78nZiyLBHSOfYcK/rCPNAD45YYtva/J3dNA8H+Q==');

for (const [filename, baselineKey] of [
  ['./check-civic-ui.mjs', 'CIVIC_BASELINE'],
  ['./check-merge-filters.mjs', 'CIVIC_MERGES_BASELINE'],
  ['./check-shared-controls.mjs', 'CIVIC_CONTROLS_BASELINE'],
]) {
  const script = fileURLToPath(new URL(filename, import.meta.url));
  let baseline = process.env[baselineKey];
  for (const browser of ['chromium', 'firefox', 'webkit']) {
    const result = spawnSync(process.execPath, [script], {
      env: { ...process.env, CIVIC_BROWSER: browser, ...(baseline ? { [baselineKey]: baseline } : {}) },
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'inherit'],
    });
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.error) throw result.error;
    if (result.status !== 0) process.exit(result.status || 1);
    // Compare subsequent engines with Chromium, or preserve a caller-supplied historical baseline.
    baseline ||= join(JSON.parse(result.stdout.trim()).output, 'results.json');
  }
}
