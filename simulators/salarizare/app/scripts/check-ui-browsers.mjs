import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

for (const [filename, baselineKey] of [
  ['./check-civic-ui.mjs', 'CIVIC_BASELINE'],
  ['./check-merge-filters.mjs', 'CIVIC_MERGES_BASELINE'],
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
