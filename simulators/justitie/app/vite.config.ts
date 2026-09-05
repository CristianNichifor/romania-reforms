import { resolve } from 'node:path';
import { defineConfig } from 'vite';

// A project site is served from /<repo>/<simulator>/, so the base carries that prefix in CI.
// Unset locally, so `npm run dev` and a fork both work without editing this file.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  build: {
    outDir: 'dist',
    assetsInlineLimit: 0,
    target: 'es2022',
    // Two pages, not two apps. The map is 2,600 lines of MapLibre and the statistics page needs
    // none of it, so they are separate entry points rather than one bundle with a router —
    // a reader who opens the statistics does not download a mapping library to read a bar chart.
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        statistici: resolve(__dirname, 'statistici.html'),
      },
    },
  },
});
