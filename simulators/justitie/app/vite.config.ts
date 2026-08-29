import { defineConfig } from 'vite';

// A project site is served from /<repo>/<simulator>/, so the base carries that prefix in CI.
// Unset locally, so `npm run dev` and a fork both work without editing this file.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  build: { outDir: 'dist', assetsInlineLimit: 0, target: 'es2022' },
});
