import { PostByline } from '../components/blog/post-context';
import { PostVideo } from '../components/blog/post-video';
// Engineering · AI-native platform · part 1. All numbers come from the real run and the simulation in
// the hands-on (runs/*.md, sim_results.md); the simulation is labelled wherever it appears.

const RUN = '/blog/ai-native';

export function LlmSchedulingBody() {
  return (
    <>
      <p className="eyebrow">Engineering · AI-native platform</p>
      <h1>When everyone asks the LLM at once</h1>
      <p className="standfirst">
        An AI-native platform shares a few GPUs between engineers, agents and overnight jobs. We flooded a model until
        the most urgent request couldn't get through, put a small scheduler in front of it, and simulated what the same
        choice means for a whole fab.
      </p>
      <PostByline />

      <p>
        02:10 at a large memory fab. An SPC chart goes out of control, and a root-cause agent starts investigating on
        its own: which lots, which chamber, what changed. It needs the language model <em>now</em>. But at 02:00 the
        nightly job queued three thousand shift reports, and engineers on the other sites are still asking questions.
        Every one of those requests goes to the same GPUs.
      </p>
      <p>
        Who goes first? On most platforms the honest answer is "whoever asked first". That is fine for a web server. It
        is the wrong answer when one of the requests is the reason a production line might be held for the night.
      </p>
      <p className="pull">
        In an AI-native platform, GPU time and tokens are the scarce shared resource. If nothing decides who gets them,
        the loudest workload wins, not the most important one.
      </p>

      <PostVideo
        src={`${RUN}/video.mp4`}
        poster={`${RUN}/video-poster.jpg`}
        caption="The whole post in 90 seconds: the real laptop run, then the fab-scale simulation. English and Korean captions."
      />

      <h2>01 · What "AI-native" actually means</h2>
      <p>
        Most companies start with AI <em>bolted on</em>: a chatbot next to the data platform, each team with its own
        model key, data exported to the AI by hand. AI-native is a different shape:
      </p>
      <ul>
        <li>
          <strong>AI is a first-class user of the platform</strong>, like a person or an application. It has an
          identity, permissions and a budget.
        </li>
        <li>
          <strong>Models are shared infrastructure</strong>: one serving pool and one front door, not a GPU island per
          team.
        </li>
        <li>
          <strong>Data is served to agents as products</strong>, with its meaning attached (a semantic layer or
          ontology), not as raw tables.
        </li>
        <li>
          <strong>Agents act on events</strong>: an alarm on a real-time stream starts an investigation within seconds.
        </li>
        <li>
          <strong>Every call is governed, measured and scheduled</strong>: who called, which model, how many tokens,
          how urgent.
        </li>
      </ul>
      <p>
        The last point is the one that gets skipped, and it is the one this post is about. Once agents run unattended,
        they don't ask a model one question; an investigation is dozens of calls in a row. Load stops being "people
        typing" and becomes "software calling software". Something has to decide the order.
      </p>

      <h2>02 · What you have to decide</h2>
      <p>Scheduling an LLM platform comes down to five decisions. You make them whether or not you write them down.</p>
      <ul>
        <li>
          <strong>Admission.</strong> How many requests run on the GPU at once. Past that, a request waits in line or
          gets a polite "not now" (HTTP <code>429 Retry-After</code>).
        </li>
        <li>
          <strong>Budgets.</strong> Tokens per minute per team or workload, so one batch job can't take everything.
        </li>
        <li>
          <strong>Priority.</strong> Urgent (an agent investigating an excursion) › interactive (an engineer waiting
          for an answer) › batch (reports that can finish by morning).
        </li>
        <li>
          <strong>Preemption.</strong> Whether urgent work may pause batch work that is already running. That costs
          something: the paused request has to re-read its prompt later.
        </li>
        <li>
          <strong>Batching and routing.</strong> Keep GPUs efficient by running many sequences together, and send a
          request to the replica that already holds its context.
        </li>
      </ul>
      <p>
        Around that core sit the other parts of an AI-native platform: one governed front door for every model and
        tool call (identity, quotas, audit, nothing leaves the site), data served as products with meaning attached,
        real-time triggers from the event stream, on-premise models, and observability for the AI platform itself.
        Each deserves its own post. This one stays on the GPUs.
      </p>
      <p className="q">
        Our take: the first thing to build is not a bigger GPU cluster. It is the line in front of it.
      </p>

      <h2>03 · We tried it on a laptop</h2>
      <p>
        We wanted to see the failure, not describe it. So we put a small model on one laptop (llama3.2:3b on Ollama, at
        most four requests in parallel, on a MacBook Pro M4 Pro) and sent it a fab-shaped load for two minutes. The
        load had engineers asking questions (one every two seconds on average), a nightly batch (twelve workers writing
        long reports) and, at the 40-second mark, a root-cause agent making five calls in a row, each waiting for the
        previous answer. Every client gave up after 60 seconds.
      </p>
      <p>
        Then we ran the exact same load twice, with the same random seed. The first time, everything went straight to
        the model. The second time, it went through a small gate we wrote, about 250 lines of Python. The gate
        has three rules: urgent before interactive before batch; a token budget per workload; and no more than four
        requests on the model at once.
      </p>
      <figure>
        <img
          src={`${RUN}/direct-dashboard.png`}
          alt="Dashboard during the run without scheduling: 32 interactive, 10 batch and the urgent request all waiting for the model"
          loading="lazy"
        />
        <figcaption>
          Real run, no scheduling, 54 s in. The urgent request (top row) waits in the same line as 42 others. Unedited
          screenshot of the live dashboard, cropped.
        </figcaption>
      </figure>
      <figure>
        <img
          src={`${RUN}/gated-dashboard.png`}
          alt="Dashboard during the run with priority and budgets: urgent first token in 2.7 s, batch requests turned away"
          loading="lazy"
        />
        <figcaption>
          Real run, priority + token budgets, same moment. The agent's first token arrives in 2.7 s; batch requests over
          budget are turned away and retry later (the red squares). Unedited, cropped.
        </figcaption>
      </figure>
      <figure>
        <img
          src={`${RUN}/compare.png`}
          alt="Bar charts: urgent investigation did not finish vs 31 s; engineer questions answered 24 vs 70 of 78; batch tokens 4,139 vs 1,560"
          loading="lazy"
        />
        <figcaption>Real run, same 120-second load, seed 7. Full table below.</figcaption>
      </figure>
      <p>
        Without scheduling, the agent's very first call timed out after 60 seconds, so the investigation never
        started. 54 of 78 engineer questions timed out too. With the gate, the agent finished all five steps in{' '}
        <strong>31 seconds</strong> (its slowest first token took 4.0 s), and <strong>70 of 78</strong> engineer
        questions were answered. The batch paid for it: the gate turned it away 449 times and it got through less
        than half the tokens it did without scheduling.
      </p>
      <figure>
        <img
          src={`${RUN}/real-table.png`}
          alt="Results table of both real runs by workload: requests, ok, turned away, timed out, first-token p50 and p95"
          loading="lazy"
        />
        <figcaption>Real run results. "Requests" includes the batch clients' retries after a 429.</figcaption>
      </figure>
      <p>Three things surprised us.</p>
      <ul>
        <li>
          <strong>Scheduling fixed the order, not the capacity.</strong> Engineers still waited about 41 seconds at the
          median, because one laptop can't keep up with that load. A scheduler decides <em>who</em> waits. Only more
          GPU, or shorter answers, decides <em>how long</em>.
        </li>
        <li>
          <strong>Saying "not now" is a feature.</strong> The batch clients backed off and retried when they got a
          429, and that is what kept the shared model usable. In a fab that work moves to quiet hours, or to its own
          pool.
        </li>
        <li>
          <strong>You can't manage a queue you can't see.</strong> Our first dashboard showed "0 waiting" in the middle
          of the flood, because without a scheduler the queue lives inside the model server. We now count "admitted,
          no answer yet" for every workload. Queue depth and time-to-first-token per workload are the first metrics an
          AI platform needs.
        </li>
      </ul>

      <h2>04 · At fab scale (simulation)</h2>
      <p>
        A laptop says nothing about absolute numbers in a fab. So we wrote a small simulator of one realistic serving
        unit: a 70B-class model in FP8 on two H200 GPUs. We didn't measure its speed ourselves. We derived it from NVIDIA's
        published NIM benchmark for Llama 3.3 70B on 2 × H200: about 60 tokens per second for one request alone,
        about 33 per request at a hundred in parallel, and roughly 11,000 prompt tokens per second.
      </p>
      <p>
        The night we simulated: 80 engineers asking questions (one every three minutes each, with retrieved context in
        every prompt), 3,000 nightly report jobs queued at 02:00, and at 02:10 the root-cause agent running a 30-step
        investigation. The load is our assumption, and it's written on every chart. We compared three scheduling
        rules.
      </p>
      <figure>
        <img
          src={`${RUN}/sim_policy_bars.png`}
          alt="Simulation bar charts for three rules: RCA investigation 21.2, 2.4, 4.0 min; engineer wait p95 1,551 s, 0.7 s, 0.2 s; batch reports done 3000, 920, 3000"
          loading="lazy"
        />
        <figcaption>
          SIMULATION, not a measurement. One 2 × H200 serving unit; speeds from NVIDIA's NIM benchmark; load assumptions
          printed on the chart.
        </figcaption>
      </figure>
      <ul>
        <li>
          <strong>First come, first served:</strong> the agent's first step waited about 18 minutes behind the batch,
          and the whole investigation took <strong>21.2 minutes</strong>. Engineers waited 14 minutes at the median.
        </li>
        <li>
          <strong>Token budgets</strong> (batch limited to 210,000 tokens a minute): the investigation took{' '}
          <strong>2.4 minutes</strong>, the fastest, but only 920 of the 3,000 reports were done by 02:30.
        </li>
        <li>
          <strong>Priority + preemption:</strong> the investigation took <strong>4.0 minutes</strong>. It was a little
          slower, because it shared the GPUs with a full batch, but every report was still done by 02:30.
        </li>
      </ul>
      <figure>
        <img
          src={`${RUN}/sim_night_wait.png`}
          alt="Simulation line chart of how long each step of the root-cause agent waits for its first token under three rules"
          loading="lazy"
        />
        <figcaption>SIMULATION. Wait for the first token, per step of the agent's investigation (log scale).</figcaption>
      </figure>
      <p>
        At the daytime peak (200 engineers, an investigation at 10:15, no batch) all three rules gave the same result:
        2.3 minutes for the investigation and well under a second of waiting for questions, because the unit had spare
        capacity. <strong>Scheduling matters when the GPUs are full</strong>, which, with a nightly batch, is exactly
        when an excursion is least welcome.
      </p>
      <p>
        One detail matters for anyone evaluating a model server. Our first simulator only reordered the waiting line,
        and the agent still waited about 35 seconds per step. The batch prompts being re-read after preemption took
        the GPU first. Priority has to cover prompt processing too, not only the queue. Ask for that explicitly when
        you compare servers.
      </p>

      <h2>05 · The open-source stack</h2>
      <p>None of this needs a proprietary product. As of November 2026, these are the pieces we would use:</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Layer</th>
              <th>Pick</th>
              <th>What it decides</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Front door</td>
              <td>Agent Router (ex-Envoy AI Gateway, v1.2) or agentgateway (v1.7), Apache-2.0</td>
              <td>Who you are, your team's token budget, which models you may use, audit of every call</td>
            </tr>
            <tr>
              <td>Inference scheduler</td>
              <td>llm-d (v1.0, CNCF Sandbox) or NVIDIA Dynamo (v1.6)</td>
              <td>Which replica, which priority class, cache-aware routing across a GPU pool</td>
            </tr>
            <tr>
              <td>Model server</td>
              <td>vLLM (0.33, rc3) with SGLang as the second engine, Apache-2.0</td>
              <td>Continuous batching on the GPU, with a priority scheduling policy</td>
            </tr>
            <tr>
              <td>GPU quotas for jobs</td>
              <td>Kueue (v0.20) or KAI Scheduler (v0.18), Apache-2.0</td>
              <td>Fair share and preemption between training, embedding and batch jobs on the same GPUs</td>
            </tr>
            <tr>
              <td>Observe</td>
              <td>Langfuse, plus HolmesGPT (CNCF Sandbox) for incidents</td>
              <td>Tokens, cost and latency per call; an agent that explains platform incidents</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        One warning: LiteLLM is the most popular gateway, but its published packages were compromised twice in 2026
        (March and October). If you use it, build it from audited source and pin images by digest. That advice holds
        for every piece above: never pull <code>latest</code> into a fab.
      </p>

      <h2>06 · Our take</h2>
      <p>If we were starting an AI-native platform for a fab tomorrow, the order would be:</p>
      <ul>
        <li>
          <strong>One front door first</strong>, with a token budget per team and a workload class (urgent,
          interactive, batch) on every call. That's cheap, and it makes everything after it possible.
        </li>
        <li>
          <strong>Priority in the model server</strong> (vLLM's priority policy) as soon as agents run unattended, and
          an inference scheduler like llm-d once there is more than one serving unit.
        </li>
        <li>
          <strong>Measure the line from day one:</strong> queue depth and time-to-first-token per workload, with an
          alert when urgent work waits. This is where AIOps for the AI platform starts.
        </li>
        <li>
          <strong>Size GPUs last</strong>, from measured tokens per team, not from guesses. Scheduling can't create
          capacity, but it tells you exactly how much you need.
        </li>
      </ul>
      <p>
        And what we would avoid: GPU islands per team (they sit idle while the next team queues), agents without a
        workload class, and any gateway image pulled by tag instead of digest.
      </p>
      <p>
        Next in this series: the AI platform watching itself (AIOps). How do you know at 02:11 that the agent is
        waiting, before an engineer notices?
      </p>

      <p className="foot-note">
        Method: the real run used a synthetic, fab-vocabulary load on one laptop (no real fab data); dashboards and
        tables are unedited screenshots (dashboards cropped). The fab-scale results are a simulation. Serving speed
        is derived from NVIDIA's published NIM benchmark (Llama-3.3-70B-Instruct, FP8, TP2 on 2 × H200); the load is our
        assumption and is stated on every chart. Versions as of 2026-11-10. The scheduler, load generator and simulator
        are in{' '}
        <a href="https://gist.github.com/minhnhat165/db4b42d046add8a67d542073db7decf6" target="_blank" rel="noopener">
          this public gist
        </a>
        .
      </p>
    </>
  );
}

// The "Latest" slot figure: the simulation's headline number, redrawn small and still labelled.
export function LlmSchedulingFigure() {
  const rows = [
    { label: 'First come, first served', min: 21.2, color: 'var(--coral)' },
    { label: 'Token budgets', min: 2.4, color: '#C98A16' },
    { label: 'Priority + preemption', min: 4.0, color: 'var(--ok)' },
  ];
  const W = 300;
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Simulation: 02:10 root-cause investigation took 21.2, 2.4 and 4.0 minutes under three scheduling rules">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        SIMULATION
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        02:10 excursion · 30-step investigation
      </text>
      {rows.map((r, i) => (
        <g key={r.label} transform={`translate(0 ${48 + i * 52})`}>
          <text x="0" y="14" fontSize="14" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
            {r.label}
          </text>
          <rect x="0" y="22" width={(W * r.min) / 21.2} height="14" rx="3" fill={r.color} />
          <text x={(W * r.min) / 21.2 + 10} y="34" fontSize="14" fill="var(--ink)" fontFamily="var(--f-mono)">
            {r.min.toFixed(1)} min
          </text>
        </g>
      ))}
    </svg>
  );
}
