import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { TanStackRouterVite } from '@tanstack/router-plugin/vite';
import path from 'node:path';

const SERVER_PORT = process.env.SERVER_PORT ?? '3000';

export default defineConfig({
  plugins: [
    TanStackRouterVite({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '~': path.resolve(__dirname, './src'),
      '~server': path.resolve(__dirname, './server'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/rpc': `http://localhost:${SERVER_PORT}`,
      '/_health': `http://localhost:${SERVER_PORT}`,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
