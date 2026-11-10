import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from '@tanstack/react-router';
import { createAppRouter } from './router';
import './styles.css';

const el = document.getElementById('root');
if (!el) throw new Error('#root not found');

// #root already holds the prerendered page (scripts/prerender.ts) — that is what crawlers, LLM fetchers and
// no-JS readers get. The app renders the same page and replaces it in one commit. (Not hydrateRoot: the router's
// server-mode markup differs from its client tree, so hydration would fail; full SSR would need TanStack's
// dehydration setup, which a static marketing site doesn't need.)
createRoot(el).render(
  <StrictMode>
    <RouterProvider router={createAppRouter()} />
  </StrictMode>,
);
