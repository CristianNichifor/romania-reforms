import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// A project site is served from /<repo>/, so the base must carry that prefix in CI.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: false },
});
