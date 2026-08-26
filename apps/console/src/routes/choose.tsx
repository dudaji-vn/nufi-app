import { createFileRoute } from '@tanstack/react-router';
import { useEffect } from 'react';

/**
 * The door at agents.nufi.me.
 *
 * A visitor arriving here has a NUFI session already; the only thing they have
 * to do is pick. So the page is a choice and nothing else — no navigation, no
 * console chrome, and one sentence per product that says what it is FOR, since
 * the names alone do not tell someone which one they want.
 */
export const Route = createFileRoute('/choose')({
  component: Choose,
});

const PRODUCTS = [
  {
    name: 'NUFI Studio',
    blurb: 'Build a flow on a canvas. Connect a model, a knowledge base and a tool, then run it.',
    href: '/enter/studio',
    external: false,
  },
  {
    name: 'NUFI Works',
    blurb: 'Put agents to work. Give a team a goal, approve what matters, and watch the spend.',
    href: import.meta.env.VITE_WORKS_URL ?? 'https://works.nufi.me',
    external: true,
  },
];

function Choose() {
  // index.html carries the console's title, and this page is served on a
  // different hostname. Left alone, the browser tab would tell a visitor at
  // agents.nufi.me that they are in the console.
  useEffect(() => {
    const previous = document.title;
    document.title = 'NUFI Agents';
    return () => {
      document.title = previous;
    };
  }, []);

  return (
    <section className="mx-auto max-w-3xl px-4 py-16 sm:py-24">
      <img src="/nufi-logo.svg" alt="NUFI" className="h-6 w-auto" />
      <h1 className="mt-8 text-3xl font-semibold tracking-tight">Agents</h1>
      <p className="mt-2 text-muted-foreground">
        Two ways to work with agents on NUFI. You are already signed in.
      </p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {PRODUCTS.map((p) => (
          <a
            key={p.name}
            href={p.href}
            {...(p.external ? {} : { rel: 'noreferrer' })}
            className="group rounded-xl border p-6 transition-colors hover:border-foreground/40 hover:bg-accent/40"
          >
            <h2 className="font-medium text-lg">{p.name}</h2>
            <p className="mt-2 text-muted-foreground text-sm leading-relaxed">{p.blurb}</p>
            <span className="mt-4 inline-block text-sm transition-colors group-hover:text-foreground text-muted-foreground">
              Open →
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
