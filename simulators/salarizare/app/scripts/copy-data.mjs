// The regime documents are the app's input, and they live at the repo root because
// they are the deliverable, not an app asset. Copy rather than symlink so the build
// works identically on a CI runner and on Windows.
import { cp, mkdir, rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../..');
const target = resolve(here, '../public/data');

// Copy the whole tree rather than an enumerated list. Enumerating it meant every new
// data directory shipped as a 404 that surfaced as "Unexpected token '<'" — the fetch
// getting index.html back. It happened three times before this became a rule.
await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(resolve(repo, 'data'), target, { recursive: true });
console.log('copied data/ into app/public/data');
