import fs from 'node:fs';
import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const base = process.env.VITE_BASE ?? '/';
const basePath = base.endsWith('/') ? base : `${base}/`;

function dataFallbackPlugin(): Plugin {
  return {
    name: 'data-fallback',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url) return next();
        const [rawPath, query = ''] = req.url.split('?');
        const pathname = decodeURIComponent(rawPath);
        const normalized =
          basePath !== '/' && pathname.startsWith(basePath)
            ? `/${pathname.slice(basePath.length)}`
            : pathname;
        if (!normalized.startsWith('/data/')) return next();

        const publicDir = server.config.publicDir;
        const filePath = path.join(publicDir, normalized.slice(1));
        if (!filePath.startsWith(path.join(publicDir, 'data'))) return next();

        fs.stat(filePath, (err, stat) => {
          if (err || !stat.isFile()) return next();
          req.url = `${normalized}${query ? `?${query}` : ''}`;
          server.middlewares.handle(req, res, next);
        });
      });
    },
  };
}

// A project site is served from /<repo>/, so the base must carry that prefix in CI.
export default defineConfig({
  base,
  plugins: [dataFallbackPlugin(), react()],
  build: { outDir: 'dist', sourcemap: false },
});
