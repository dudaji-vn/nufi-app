import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// NuFi Box marketing site — a small Vite + React SPA. Built to static assets
// in `dist/` and served by `server.ts` (bun + Hono) with an SPA fallback.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
