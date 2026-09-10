import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';

// A project site is served from /<repo>/<simulator>/, so the base carries that prefix in CI.
// Unset locally, so `npm run dev` and a fork both work without editing this file.

const dataDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'data');

// In dev, serve the simulator's data/ directly. Without this, a server started as bare
// `npx vite` (skipping the predev copy into public/data) answers a missing JSON with the
// app's own index.html and the page fails with a JSON parse error instead of loading.
function serveData(): Plugin {
  return {
    name: 'serve-simulator-data',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';
        if (req.method === 'GET' && url.startsWith('/data/')) {
          const file = join(dataDir, decodeURIComponent(url.slice('/data/'.length)));
          if (
            file.endsWith('.json') &&
            !relative(dataDir, file).startsWith('..') &&
            existsSync(file)
          ) {
            res.setHeader('Content-Type', 'application/json');
            res.end(readFileSync(file));
            return;
          }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  build: { outDir: 'dist', assetsInlineLimit: 0, target: 'es2022' },
  plugins: [serveData()],
});
