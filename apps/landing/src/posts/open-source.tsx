import type { ReactNode } from 'react';
import { PostByline } from '../components/blog/post-context';
import { Icon } from '../components/icon';
import { SectionLink } from '../components/section-link';
import { BoxStackArt } from '../components/post-art';

// NuFi Box · How it works. Every name, version and license below was read from the box's own
// install files (deploy/box/docker-compose*.yml, install-box.sh, sandbox/Dockerfile) and each
// project's LICENSE. Bump this post when a pinned version moves.

type Row = { name: string; version: string; license: string; job: ReactNode };

function PartsTable({ rows }: { rows: Row[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Project</th>
            <th>Version on the box</th>
            <th>License</th>
            <th>What it does here</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td>
                <strong>{r.name}</strong>
              </td>
              <td>{r.version}</td>
              <td>{r.license}</td>
              <td>{r.job}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CHAT: Row[] = [
  {
    name: 'LibreChat',
    version: 'v0.8.6-rc1 (our fork)',
    license: 'MIT',
    job: 'The chat everyone in the office opens. Accounts, teams, conversations, file uploads.',
  },
  {
    name: 'LibreChat RAG API',
    version: 'pinned by digest',
    license: 'MIT',
    job: 'Splits your documents into passages, embeds them, and finds the ones that match a question.',
  },
  {
    name: 'PostgreSQL + pgvector',
    version: 'PostgreSQL 16',
    license: 'PostgreSQL License',
    job: 'Stores the passage vectors, plus the data for the model gateway, Studio and Works.',
  },
  {
    name: 'MongoDB',
    version: '4.4',
    license: 'SSPL (source-available, see below)',
    job: 'Stores users, conversations and settings for the chat.',
  },
];

const MODELS: Row[] = [
  {
    name: 'Ollama',
    version: '0.33.3',
    license: 'MIT',
    job: 'Runs the language model and the embedding model on the box\'s own GPU (the Apple chip on a Mac).',
  },
  {
    name: 'Qwen2.5 7B Instruct',
    version: 'default model',
    license: 'Apache-2.0 (open weights)',
    job: 'Writes the answers. You can pick another model at install time.',
  },
  {
    name: 'BGE-M3',
    version: 'default embeddings',
    license: 'MIT (open weights)',
    job: 'Turns text into vectors so a question can find the right passage, in English, Korean or Vietnamese.',
  },
  {
    name: 'LiteLLM',
    version: 'v1.83.10',
    license: 'MIT (open-source core)',
    job: 'One front door for every model call, with keys, limits and our guardrails built in.',
  },
];

const AGENTS: Row[] = [
  {
    name: 'Langflow',
    version: '1.11.2 (our fork)',
    license: 'MIT',
    job: 'NuFi Studio: build an agent or a flow by dragging boxes. Optional, install with --no-studio to leave it out.',
  },
  {
    name: 'Paperclip',
    version: 'our fork',
    license: 'MIT',
    job: 'NuFi Works: a team of agents that take tasks and write code. Optional, added with --with-works.',
  },
  {
    name: 'gVisor',
    version: 'runsc, checksum-pinned',
    license: 'Apache-2.0',
    job: 'A second kernel between an agent\'s code and the box. Every Works sandbox runs behind it.',
  },
  {
    name: 'tinyproxy',
    version: 'on Alpine 3.20',
    license: 'GPL-2.0',
    job: 'The one way out of the sandbox network. It forwards only to addresses on your list.',
  },
  {
    name: 'OpenAI Codex CLI',
    version: '0.154.0',
    license: 'Apache-2.0',
    job: 'A coding agent that runs inside the sandbox.',
  },
  {
    name: 'OpenCode',
    version: '1.18.31',
    license: 'MIT',
    job: 'A second coding agent, works with the model on the box.',
  },
];

const NETWORK: Row[] = [
  {
    name: 'Caddy',
    version: '2.10.0',
    license: 'Apache-2.0',
    job: 'The HTTPS front door. One hostname, TLS from day one.',
  },
  {
    name: 'Tailscale (client)',
    version: 'v1.102.3',
    license: 'BSD-3-Clause',
    job: 'The encrypted mesh that lets a laptop at home reach the box.',
  },
  {
    name: 'Headscale',
    version: 'v0.29.3',
    license: 'BSD-3-Clause',
    job: 'The mesh coordinator, when you run it yourself instead of using ours.',
  },
  {
    name: 'Samba',
    version: '4.23.8',
    license: 'GPL-3.0',
    job: 'The shared drive. Drop a file in a department folder and the box reads it.',
  },
  {
    name: 'Avahi',
    version: 'from the OS',
    license: 'LGPL-2.1',
    job: 'Announces the box on the office network as nufi.local.',
  },
];

const FLOOR: Row[] = [
  {
    name: 'Docker Engine + Compose',
    version: 'from the OS',
    license: 'Apache-2.0',
    job: 'Runs every part above as its own container.',
  },
  {
    name: 'Ubuntu',
    version: '24.04 LTS',
    license: 'mostly GPL / free licenses',
    job: 'The operating system we install on and the base of the sandbox image.',
  },
  {
    name: 'Node.js, Bun, React, Hono',
    version: 'Node 22, Bun 1.4',
    license: 'MIT',
    job: 'What our own pieces (the owner console and the helpers) are built with.',
  },
];

export function OpenSourceBody() {
  return (
    <>
      <p className="eyebrow">NuFi Box · How it works</p>
      <h1>Everything inside the box, by name</h1>
      <p className="standfirst">
        What open source is actually inside NuFi Box? It's a fair thing to ask about anything that sits on your
        network. Here is the full list, read straight from the files the box installs from. Every project, the version we run, its license, and the job it
        does. Plus the two places where the answer isn't simply "open source".
      </p>
      <PostByline />

      <p>
        Anyone who approves software for a company network ends up asking it. Somebody has to sign off on every piece
        of software that lands there, and "it's an AI appliance" doesn't get through that
        meeting. They want names. They want to look each project up, check the license with their legal team, and see
        whether it has a history of security problems.
      </p>
      <p>
        We think that's exactly right, and it's why we built the box this way. Almost nothing on it is ours. The chat,
        the model runtime, the database, the mesh, the sandbox: each one is a well-known open-source project with its
        own public code, its own issue tracker and its own security record. What we wrote is the glue, the installer and
        the defaults. If you can't inspect a private AI box, it's just another promise. So here is the inside.
      </p>

      <figure className="post-fig">
        <BoxStackArt />
        <figcaption>
          The box in five layers. Each name is a project with public code you can read and audit. One of them,
          MongoDB, comes with a catch, explained below.
        </figcaption>
      </figure>

      <p>
        One rule shapes this whole list: every third-party image is pinned to an exact version, and some to a digest.
        Nothing on the box pulls "latest". When you install a box this month and another one next month, they run the
        same bits, and a version only moves when we move it on purpose. That's also why the versions below are real:
        they're the ones in the install files today.
      </p>

      <h2>01 · Chat and your documents</h2>
      <p>
        This is the part people see. Someone opens the chat in a browser, asks about the leave policy, and gets an
        answer with the handbook passage attached. Under it, the documents are cut into passages, turned into vectors
        and kept in Postgres, all on the box's own drive.
      </p>
      <PartsTable rows={CHAT} />

      <h2>02 · The models</h2>
      <p>
        The model runs on the box. No prompt goes to an outside API unless you choose the cloud option at install time,
        and the installer warns you when you do. The default is a 7B model because it fits on one consumer GPU and
        answers document questions well. If you have a bigger card, pick a bigger model; the rest of the box doesn't
        care which one it is.
      </p>
      <PartsTable rows={MODELS} />

      <h2>03 · Agents and the sandbox</h2>
      <p>
        Studio and Works are the agent side of the box. Both are forks of open-source projects that we rebranded and
        wired into the box's single sign-on. The interesting part is the sandbox. When an agent writes and runs code, it
        does it inside a container that sits behind gVisor, with a read-only file system and a network whose only exit
        is a tiny proxy that forwards to the addresses you list. Leave the list empty and there is no exit at all.
      </p>
      <PartsTable rows={AGENTS} />

      <h2>04 · Getting in: network and files</h2>
      <p>
        The office reaches the box by name on the local network. Someone working from home joins the encrypted mesh
        and reaches it the same way. Files arrive through an ordinary shared drive, so nobody has to learn a new upload
        screen: drop the PDF in the HR folder and a minute later the box can answer from it.
      </p>
      <PartsTable rows={NETWORK} />

      <h2>05 · The floor it all stands on</h2>
      <PartsTable rows={FLOOR} />

      <h2>The two exceptions</h2>
      <p>We'd rather point these out ourselves than have your legal team find them.</p>
      <ul>
        <li>
          <strong>MongoDB is source-available, not open source.</strong> Its license (SSPL) lets you read the code and
          run it on your own box freely. It is not approved by the Open Source Initiative, because it puts conditions
          on offering MongoDB as a hosted service to others. For a box that sits in your own building, that condition
          doesn't apply. We still list it honestly, and we're looking at an open-source replacement for the chat's
          database.
        </li>
        <li>
          <strong>Claude Code is not open source.</strong> The Works sandbox can also run Anthropic's Claude Code as a
          coding agent, but only if you connect your own Claude account. It's a proprietary tool under Anthropic's
          commercial terms. It's optional, it's off unless you turn it on, and Codex CLI and OpenCode cover the same job
          with open licenses.
        </li>
      </ul>
      <p>
        The model weights deserve a short note too. Qwen2.5 7B and BGE-M3 are "open weights": anyone can download,
        run and fine-tune them under Apache-2.0 and MIT. The data they were trained on isn't published, which is normal
        for models today. If your policy needs a specific model, the box will run whatever Ollama can load.
      </p>

      <h2>What we wrote ourselves</h2>
      <p>
        Being honest about the list means naming our own parts too. We wrote the installer and the <code>nufi-box</code>{' '}
        command that updates and checks the box, the owner console where the box's admin changes settings, the
        background job that watches the shared drive and feeds new files into the index, the scheduler for routine
        jobs, and the guardrail rules inside the model gateway. These are small. Their whole job is to tie the projects above
        into one machine you can plug in.
      </p>

      <div className="pull">
        A private AI box should be one you can open. Every part above has a public repo, so your security team can
        look at the same code we did.
      </div>

      <p>
        If you're running a review and need more, like exact image digests, the full dependency list of one component,
        or a software bill of materials for a specific release, ask us. We'd rather answer the hard questions before
        the box goes in than after.
      </p>

      <div className="cta-box">
        <h2>Running a security review?</h2>
        <p>Tell us what your team needs to check. We'll send the versions, licenses and digests for your box.</p>
        <SectionLink id="contact" className="btn btn--primary">
          Talk to us <Icon name="arrow" />
        </SectionLink>
      </div>
    </>
  );
}
