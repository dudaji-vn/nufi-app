import Image from 'next/image';
import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  ArrowRight,
  BookMarked,
  Bot,
  Code,
  Compass,
  FileText,
  KeyRound,
  MessageSquare,
  Rocket,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  Workflow,
} from 'lucide-react';

// The same icons the sidebar sections use, so a section looks the same here
// as it does once you are inside it. Each section also carries its own hue,
// used only on the icon tile: enough to tell eight cards apart at a glance,
// not enough to fight the text.
type Section = {
  title: string;
  href: string;
  desc: string;
  icon: ReactNode;
  tile: string;
};

const sections: Section[] = [
  {
    title: 'Overview',
    href: '/docs/overview',
    desc: 'What NUFI is and how the pieces fit. Read this first if you are new.',
    icon: <Compass className="size-5" strokeWidth={1.75} />,
    tile: 'bg-sky-500/10 text-sky-600 dark:text-sky-300',
  },
  {
    title: 'Using the app',
    href: '/docs/end-user',
    desc: 'Sign in, chat, attach files, build agents, share with a team.',
    icon: <MessageSquare className="size-5" strokeWidth={1.75} />,
    tile: 'bg-violet-500/10 text-violet-600 dark:text-violet-300',
  },
  {
    title: 'NUFI Studio',
    href: '/docs/studio',
    desc: 'Build a flow on a canvas and publish it as an endpoint your code can call.',
    icon: <Workflow className="size-5" strokeWidth={1.75} />,
    tile: 'bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-300',
  },
  {
    title: 'NUFI Works',
    href: '/docs/works',
    desc: 'Give a team of agents a goal, approve what matters, and watch the spend.',
    icon: <Users className="size-5" strokeWidth={1.75} />,
    tile: 'bg-rose-500/10 text-rose-600 dark:text-rose-300',
  },
  {
    title: 'Administer',
    href: '/docs/admin',
    desc: 'Configure the platform, manage roles and groups, read the audit log.',
    icon: <SlidersHorizontal className="size-5" strokeWidth={1.75} />,
    tile: 'bg-amber-500/10 text-amber-600 dark:text-amber-300',
  },
  {
    title: 'Deploy & operate',
    href: '/docs/deployment',
    desc: 'Stand up a production instance, then monitor, back up, and troubleshoot.',
    icon: <Rocket className="size-5" strokeWidth={1.75} />,
    tile: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
  },
  {
    title: 'Develop',
    href: '/docs/developer',
    desc: 'Run the stack locally, work in each app, add models, and ship a release.',
    icon: <Code className="size-5" strokeWidth={1.75} />,
    tile: 'bg-teal-500/10 text-teal-600 dark:text-teal-300',
  },
  {
    title: 'Reference',
    href: '/docs/reference',
    desc: 'Every port, every environment variable, and the glossary.',
    icon: <BookMarked className="size-5" strokeWidth={1.75} />,
    tile: 'bg-slate-500/10 text-slate-600 dark:text-slate-300',
  },
];

// Three doors, one per kind of reader. The manual is long; this is the part
// of the front page that answers "where do I start?" without a search.
type Path = {
  eyebrow: string;
  title: string;
  desc: string;
  href: string;
  cta: string;
  icon: ReactNode;
  links: { label: string; href: string }[];
};

const paths: Path[] = [
  {
    eyebrow: 'For everyone',
    title: 'Use the app',
    desc: 'Sign in, ask a question, work with your documents, build an assistant, and share it with your team.',
    href: '/docs/end-user',
    cta: 'Open the user guide',
    icon: <MessageSquare className="size-5" strokeWidth={1.75} />,
    links: [
      { label: 'Sign in and your account', href: '/docs/end-user/sign-in' },
      { label: 'Basic and Advanced mode', href: '/docs/end-user/advanced-mode' },
      { label: 'Chat with a document', href: '/docs/end-user/guides/chat-with-a-document' },
    ],
  },
  {
    eyebrow: 'For administrators',
    title: 'Run it for your organisation',
    desc: 'Install NUFI on your own hardware or on Railway, set budgets and roles, and keep it healthy.',
    href: '/docs/deployment',
    cta: 'Open the deployment guide',
    icon: <Rocket className="size-5" strokeWidth={1.75} />,
    links: [
      { label: 'Installation', href: '/docs/deployment' },
      { label: 'The admin panel', href: '/docs/admin' },
      { label: 'Security controls', href: '/docs/overview/security' },
    ],
  },
  {
    eyebrow: 'For developers',
    title: 'Build on it',
    desc: 'Call the gateway from your code, run the stack locally, and change any of the apps.',
    href: '/docs/developer',
    cta: 'Open the developer guide',
    icon: <Code className="size-5" strokeWidth={1.75} />,
    links: [
      { label: 'Connect NUFI to your code', href: '/docs/end-user/guides/connect-nufi-to-your-code' },
      { label: 'Run the stack locally', href: '/docs/developer/run-locally' },
      { label: 'Add or change a model', href: '/docs/developer/models' },
    ],
  },
];

const guides = [
  {
    title: 'Chat with a document',
    desc: 'Upload a PDF and get answers, summaries and translations from it.',
    href: '/docs/end-user/guides/chat-with-a-document',
    icon: <FileText className="size-5" strokeWidth={1.75} />,
  },
  {
    title: 'Build a knowledge assistant',
    desc: 'An agent that answers from your own documents, shared with the team.',
    href: '/docs/end-user/guides/build-a-knowledge-assistant',
    icon: <Bot className="size-5" strokeWidth={1.75} />,
  },
  {
    title: 'Set up a team workspace',
    desc: 'Create a team, invite people, and share knowledge, agents and prompts.',
    href: '/docs/end-user/guides/set-up-a-team-workspace',
    icon: <Users className="size-5" strokeWidth={1.75} />,
  },
  {
    title: 'Connect NUFI to your code',
    desc: 'Generate an API key in the console and make your first request.',
    href: '/docs/end-user/guides/connect-nufi-to-your-code',
    icon: <KeyRound className="size-5" strokeWidth={1.75} />,
  },
];

const features = [
  {
    title: 'The models you choose',
    desc: 'Frontier or open-source, cloud or on your own hardware, switched per conversation.',
  },
  {
    title: 'Checked on every message',
    desc: 'Injection attempts, personal data and hidden data channels are caught before and after the model, on every request.',
  },
  {
    title: 'Your documents, in context',
    desc: 'Attach a file to a message, or give an agent a knowledge base it answers from every time.',
  },
  {
    title: 'Agents, flows, and agent teams',
    desc: 'Build an assistant in the app, a pipeline in NUFI Studio, or a team that runs work in NUFI Works.',
  },
  {
    title: 'Shared with the right people',
    desc: 'Teams and groups share knowledge, agents and prompts; access adds up, never leaks.',
  },
  {
    title: 'Budgets and keys',
    desc: 'Administrators set limits by role, group or person. Developers issue their own keys against the same budget.',
  },
];

export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col">
      {/* ---------------------------------------------------------- hero */}
      <section className="relative overflow-hidden">
        <div className="nufi-hero-bg" aria-hidden />
        <div className="relative mx-auto grid w-full max-w-6xl gap-12 px-6 pb-20 pt-16 md:pt-24 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:pb-28">
          <div>
            <p className="mb-4 text-xs font-medium uppercase tracking-[0.22em] text-fd-muted-foreground">
              NUFI · User manual
            </p>
            <h1 className="mb-5 text-4xl font-bold tracking-tight md:text-6xl">
              The AI app built for{' '}
              <span className="bg-gradient-to-r from-fd-primary to-fuchsia-500 bg-clip-text text-transparent dark:to-fuchsia-300">
                teams.
              </span>
            </h1>
            <p className="mb-8 max-w-xl text-lg leading-relaxed text-fd-muted-foreground md:text-xl">
              A secure AI workspace for your organisation: the models you
              choose, security checks on every message, budgets your
              administrators control, and a developer console for building on
              top.
            </p>
            {/*
              "Start reading" lands on Overview, a page you can actually read,
              not on /docs, which would repeat the section grid below. "Open
              NUFI" goes to the live app, the same place as the top nav.
            */}
            <div className="flex flex-wrap gap-3">
              <Link
                href="/docs/overview"
                className="inline-flex items-center gap-2 rounded-lg bg-fd-primary px-5 py-2.5 text-sm font-medium text-fd-primary-foreground shadow-sm transition hover:opacity-90"
              >
                Start reading
                <ArrowRight className="size-4" />
              </Link>
              <a
                href="https://chat.nufi.me"
                className="inline-flex items-center rounded-lg border border-fd-border bg-fd-card px-5 py-2.5 text-sm font-medium transition hover:bg-fd-accent"
              >
                Open NUFI
              </a>
            </div>
            <ul className="mt-10 flex flex-wrap gap-x-6 gap-y-2 text-sm text-fd-muted-foreground">
              <li className="inline-flex items-center gap-2">
                <ShieldCheck className="size-4 text-fd-primary" strokeWidth={1.75} />
                Guardrails on every request
              </li>
              <li className="inline-flex items-center gap-2">
                <Rocket className="size-4 text-fd-primary" strokeWidth={1.75} />
                Self-hosted or managed
              </li>
              <li className="inline-flex items-center gap-2">
                <KeyRound className="size-4 text-fd-primary" strokeWidth={1.75} />
                One account, every surface
              </li>
            </ul>
          </div>

          {/* A real conversation from chat.nufi.me in a window frame. The
              screenshot is the same file the user guide uses, so the front
              page and the manual never show two different products. */}
          <div className="relative">
            <div className="nufi-hero-glow" aria-hidden />
            <div className="relative overflow-hidden rounded-xl border border-fd-border bg-fd-card shadow-2xl shadow-black/10 dark:shadow-black/40">
              <div className="flex items-center gap-1.5 border-b border-fd-border bg-fd-muted/60 px-3 py-2">
                <span className="size-2.5 rounded-full bg-fd-border" />
                <span className="size-2.5 rounded-full bg-fd-border" />
                <span className="size-2.5 rounded-full bg-fd-border" />
                <span className="ml-3 rounded-md bg-fd-background px-2 py-0.5 text-[11px] text-fd-muted-foreground">
                  chat.nufi.me
                </span>
              </div>
              <Image
                src="/screenshots/chat-conversation.png"
                alt="A conversation in the NUFI app"
                width={1440}
                height={900}
                priority
                className="block w-full"
              />
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- paths */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-20">
        <SectionHeading
          eyebrow="Start here"
          title="Three ways in"
          desc="Pick the one that sounds like you. Each door opens on the part of the manual written for that job."
        />
        <div className="grid gap-5 md:grid-cols-3">
          {paths.map((p) => (
            <div
              key={p.href}
              className="flex flex-col rounded-2xl border border-fd-border bg-fd-card p-6 transition hover:border-fd-primary/40"
            >
              <div className="mb-4 inline-flex size-10 items-center justify-center rounded-lg bg-fd-primary/10 text-fd-primary">
                {p.icon}
              </div>
              <p className="text-xs font-medium uppercase tracking-wider text-fd-muted-foreground">
                {p.eyebrow}
              </p>
              <h3 className="mt-1 text-lg font-semibold">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-fd-muted-foreground">
                {p.desc}
              </p>
              <ul className="mt-5 space-y-2 border-t border-fd-border pt-4 text-sm">
                {p.links.map((l) => (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      className="inline-flex items-center gap-1.5 text-fd-foreground/80 hover:text-fd-primary"
                    >
                      <span className="size-1 rounded-full bg-fd-primary/60" aria-hidden />
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
              <Link
                href={p.href}
                className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-medium text-fd-primary hover:underline"
              >
                {p.cta}
                <ArrowRight className="size-4" />
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------ sections */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-20">
        <SectionHeading
          eyebrow="The manual"
          title="Everything, in reading order"
          desc="The same eight sections as the sidebar. Prev and Next walk you through them from front to back."
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {sections.map((s) => (
            <Link
              key={s.href}
              href={s.href}
              className="group flex flex-col rounded-xl border border-fd-border bg-fd-card p-5 transition hover:-translate-y-0.5 hover:border-fd-primary/40 hover:shadow-lg hover:shadow-black/5 dark:hover:shadow-black/30"
            >
              <div
                className={`mb-4 inline-flex size-10 items-center justify-center rounded-lg ${s.tile}`}
                aria-hidden
              >
                {s.icon}
              </div>
              <h3 className="font-semibold group-hover:text-fd-primary">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-fd-muted-foreground">
                {s.desc}
              </p>
            </Link>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------- guides */}
      <section className="border-y border-fd-border bg-fd-muted/40">
        <div className="mx-auto w-full max-w-6xl px-6 py-20">
          <SectionHeading
            eyebrow="Guides"
            title="Get something done"
            desc="Step-by-step playbooks for the jobs people actually come here for."
          />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {guides.map((g) => (
              <Link
                key={g.href}
                href={g.href}
                className="group rounded-xl border border-fd-border bg-fd-card p-5 transition hover:border-fd-primary/40"
              >
                <div className="mb-3 inline-flex size-9 items-center justify-center rounded-lg border border-fd-border bg-fd-background text-fd-muted-foreground transition group-hover:border-fd-primary/40 group-hover:text-fd-primary">
                  {g.icon}
                </div>
                <h3 className="font-semibold group-hover:text-fd-primary">{g.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-fd-muted-foreground">
                  {g.desc}
                </p>
              </Link>
            ))}
          </div>
          <Link
            href="/docs/end-user/guides"
            className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-fd-primary hover:underline"
          >
            All guides
            <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>

      {/* ------------------------------------------------------ features */}
      <section className="mx-auto w-full max-w-6xl px-6 py-20">
        <SectionHeading
          eyebrow="What you get"
          title="What NUFI gives your team"
          desc="The parts of the product the manual keeps coming back to."
        />
        <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div key={f.title} className="flex gap-3">
              <span
                className="mt-2 size-1.5 flex-none rounded-full bg-fd-primary"
                aria-hidden
              />
              <div>
                <h3 className="font-semibold">{f.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-fd-muted-foreground">
                  {f.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------- footer */}
      <section className="border-t border-fd-border">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-fd-muted-foreground">
          <p>NUFI documentation. Describes the hosted app at chat.nufi.me and the same software on your own hardware.</p>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <a href="https://chat.nufi.me" className="hover:text-fd-foreground">The app</a>
            <a href="https://console.nufi.me" className="hover:text-fd-foreground">Console</a>
            <a href="https://agents.nufi.me" className="hover:text-fd-foreground">Studio and Works</a>
          </div>
        </div>
      </section>
    </main>
  );
}

function SectionHeading({
  eyebrow,
  title,
  desc,
}: {
  eyebrow: string;
  title: string;
  desc: string;
}) {
  return (
    <div className="mb-8 max-w-2xl">
      <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-fd-primary">
        {eyebrow}
      </p>
      <h2 className="text-2xl font-bold tracking-tight md:text-3xl">{title}</h2>
      <p className="mt-2 text-fd-muted-foreground">{desc}</p>
    </div>
  );
}
