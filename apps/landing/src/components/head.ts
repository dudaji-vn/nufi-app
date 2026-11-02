import { useEffect } from 'react';

// Preferred canonical domain for the site (independent of which host serves it).
const CANONICAL_ORIGIN = 'https://box.nufi.me';

function upsertMeta(attr: 'name' | 'property', key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
}

function upsertCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!el) {
    el = document.createElement('link');
    el.rel = 'canonical';
    document.head.appendChild(el);
  }
  el.href = href;
}

// Sets the document title + per-page description / Open Graph / canonical for an
// SPA route. Static defaults live in index.html for non-JS crawlers; this keeps
// browser tabs, history and JS-running crawlers in sync per route.
export function useHead(title: string, description: string) {
  useEffect(() => {
    document.title = title;
    upsertMeta('name', 'description', description);
    upsertMeta('property', 'og:title', title);
    upsertMeta('property', 'og:description', description);
    upsertMeta('name', 'twitter:title', title);
    upsertMeta('name', 'twitter:description', description);
    const url = CANONICAL_ORIGIN + window.location.pathname;
    upsertMeta('property', 'og:url', url);
    upsertCanonical(url);
  }, [title, description]);
}
