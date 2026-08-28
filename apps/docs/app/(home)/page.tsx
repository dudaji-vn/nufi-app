import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  BookMarked,
  Code,
  Compass,
  MessageSquare,
  Rocket,
  SlidersHorizontal,
  Users,
  Workflow,
} from 'lucide-react';

// The same icons the sidebar tabs use, so a section looks the same here as it
// does once you are inside it. These replaced emoji, which rendered at a
// different size on every platform and matched nothing else in the product.
type Card = {
  title: string;
  href: string;
  desc: string;
  icon: ReactNode;
};

const cards: Card[] = [
  {
    title: 'Overview',
    href: '/docs/overview',
    desc: 'What NUFI is and how it works. Read this first if you are new.',
    icon: <Compass className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'Using the app',
    href: '/docs/end-user',
    desc: 'Sign in, pick a model, work with agents, files, and teams.',
    icon: <MessageSquare className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'NUFI Studio',
    href: '/docs/studio',
    desc: 'Build a flow on a canvas and publish it as an endpoint your code can call.',
    icon: <Workflow className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'NUFI Works',
    href: '/docs/works',
    desc: 'Give a team of agents a goal, approve what matters, and watch the spend.',
    icon: <Users className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'Administer',
    href: '/docs/admin',
    desc: 'Configure the platform, manage users, roles, groups, and observe usage.',
    icon: <SlidersHorizontal className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'Deploy & operate',
    href: '/docs/deployment',
    desc: 'Stand up a production instance, then monitor, back up, and troubleshoot.',
    icon: <Rocket className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'Develop',
    href: '/docs/developer',
    desc: 'Run the stack locally, work in the codebases, add models, and ship.',
    icon: <Code className="size-6" strokeWidth={1.5} />,
  },
  {
    title: 'Reference',
    href: '/docs/reference',
    desc: 'Flat lookup tables — every port, environment variable, glossary.',
    icon: <BookMarked className="size-6" strokeWidth={1.5} />,
  },
];


export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col">
      <section className="px-6 py-20 md:py-28 max-w-6xl mx-auto w-full">
        <p className="text-sm uppercase tracking-[0.2em] text-fd-muted-foreground mb-4">
          NUFI · User Manual
        </p>
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-6 bg-gradient-to-br from-fd-foreground to-fd-muted-foreground bg-clip-text text-transparent">
          The AI app built for teams.
        </h1>
        <p className="text-lg md:text-xl text-fd-muted-foreground max-w-2xl mb-10">
          NUFI is a secure AI workspace — think Claude, ChatGPT,
          or Gemini, but for your organisation, with the models you
          choose, the budget controls you need, and a developer
          console for building on top.
        </p>
        {/*
          Both of these used to be wrong. "Read the docs" pointed at /docs,
          which showed the same six cards as the grid below it -- a reader who
          clicked it to start reading was handed the identical choice again.
          It now lands on Overview, which is a page you can actually read.

          "Open the app" pointed at /docs/end-user, a documentation section,
          while the top nav's "Open App" went to chat.nufi.me. Two controls,
          near-identical names, different destinations, and the prominent one
          was the wrong one.
        */}
        <div className="flex flex-wrap gap-3">
          <Link
            href="/docs/overview"
            className="inline-flex items-center rounded-lg bg-fd-primary px-5 py-2.5 text-sm font-medium text-fd-primary-foreground hover:opacity-90"
          >
            Start reading →
          </Link>
          <a
            href="https://chat.nufi.me"
            className="inline-flex items-center rounded-lg border border-fd-border bg-fd-card px-5 py-2.5 text-sm font-medium hover:bg-fd-accent"
          >
            Open NUFI
          </a>
        </div>
      </section>

      <section className="px-6 pb-24 max-w-6xl mx-auto w-full">
        <div className="grid sm:grid-cols-2 gap-5">
          {cards.map((c) => (
            <Link
              key={c.href}
              href={c.href}
              className="group rounded-xl border border-fd-border bg-fd-card p-6 transition hover:border-fd-primary/50 hover:bg-fd-accent"
            >
              <div
                className="mb-4 inline-flex size-11 items-center justify-center rounded-lg border border-fd-border bg-fd-background text-fd-muted-foreground transition group-hover:border-fd-primary/40 group-hover:text-fd-primary"
                aria-hidden
              >
                {c.icon}
              </div>
              <h2 className="text-lg font-semibold mb-2 group-hover:text-fd-primary">
                {c.title}
              </h2>
              <p className="text-sm text-fd-muted-foreground leading-relaxed">
                {c.desc}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section className="px-6 pb-24 max-w-6xl mx-auto w-full">
        <h2 className="text-2xl font-bold mb-6">What NUFI gives your team</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <Feature
            title="Pick any model"
            desc="Switch between frontier and open-source AI models per conversation. Your data, your choice."
          />
          <Feature
            title="Work with files"
            desc="Drop in PDFs, images, code. NUFI reads them and answers in context."
          />
          <Feature
            title="Build agents"
            desc="No-code AI assistants with tools, knowledge files, and custom instructions."
          />
          <Feature
            title="Flows and agent teams"
            desc="Build a pipeline on a canvas in NUFI Studio, or put a team of agents to work in NUFI Works."
          />
          <Feature
            title="Web search"
            desc="Let the AI fetch live information with cited sources."
          />
          <Feature
            title="API access"
            desc="Self-serve API keys for your scripts and integrations. Same models, same budget."
          />
          <Feature
            title="Per-team controls"
            desc="Admins set budgets, rate limits, model access — by role, group, or person."
          />
        </div>
      </section>
    </main>
  );
}

function Feature({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="rounded-xl border border-fd-border bg-fd-card p-5">
      <h3 className="font-semibold mb-2">{title}</h3>
      <p className="text-sm text-fd-muted-foreground leading-relaxed">
        {desc}
      </p>
    </div>
  );
}
