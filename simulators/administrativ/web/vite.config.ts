import { defineConfig } from 'vite';

// Each simulator is served from a path under /<repo>/, so assets need that prefix. It is
// supplied by CI rather than hardcoded, so `npm run dev` and a user fork both work without
// editing this file.
const base = process.env.VITE_BASE ?? '/';

export default defineConfig({
  base,
  build: {
    outDir: 'dist',
    // The data payload is already compact and fingerprinted by content; inlining anything
    // would only make the entry chunk bigger for no gain.
    assetsInlineLimit: 0,
    target: 'es2022',
  },
  worker: { format: 'es' },
});
