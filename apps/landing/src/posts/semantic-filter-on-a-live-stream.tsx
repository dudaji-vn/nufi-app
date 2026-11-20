import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 5. Continuous Prompts (arXiv 2512.03389 v2) and VectraFlow (arXiv 2604.03855)
// read; our run: qwen2.5 7B on Ollama on an M4 Pro laptop (24 GB), 200 synthetic notes at 3–40 per second, one run
// per configuration.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const mono = 'var(--f-mono)';

// notes waiting (arrived, not yet answered), sampled every second, at 20 notes/s
const WAITING = {
  all: [1, 15, 30, 45, 60, 77, 91, 106, 121, 136, 151, 146, 140, 135, 130, 125, 120, 116, 111, 106, 101, 96, 91, 86, 82, 77, 72, 67, 61, 57, 52, 47, 41, 36, 31, 26, 21, 16, 11, 6, 2, 0],
  split: [1, 8, 17, 21, 29, 35, 31, 36, 49, 58, 62, 51, 40, 32, 16, 0],
  split4: [1, 0, 4, 12, 9, 3, 12, 16, 21, 26, 34, 8, 0],
};

function WaitingChart() {
  const x0 = 60, w = 620, top = 16, h = 190, maxT = 42, maxN = 160;
  const X = (t: number) => x0 + (t / maxT) * w;
  const Y = (n: number) => top + h - (n / maxN) * h;
  const line = (ys: number[]) => ys.map((n, t) => `${X(t)},${Y(n)}`).join(' ');
  return (
    <svg viewBox="0 0 720 290" role="img" aria-label="Notes waiting for an answer, second by second, when 200 notes arrive at 20 per second. When every note goes to the model, the queue grows to 151 by second 10, when the last note arrives, and takes until second 40 to drain. With the split, at most 62 wait and the last answer is at 14 seconds; with the split and four concurrent requests, at most 34 and the last answer at 12 seconds">
      {[0, 50, 100, 150].map((n) => (
        <g key={n}>
          <line x1={x0} x2={x0 + w} y1={Y(n)} y2={Y(n)} stroke={C.rule} />
          <text x={x0 - 8} y={Y(n) + 4} textAnchor="end" fontSize="11" fill={C.mute} fontFamily={mono}>
            {n}
          </text>
        </g>
      ))}
      {[0, 10, 20, 30, 40].map((t) => (
        <text key={t} x={X(t)} y={Y(0) + 18} textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
          {t} s
        </text>
      ))}
      <line x1={X(10)} x2={X(10)} y1={top} y2={Y(0)} stroke={C.mute} strokeDasharray="3 3" />
      <text x={X(10) + 6} y={top + 10} fontSize="11" fill={C.mute} fontFamily={body}>
        last note arrives
      </text>
      <polyline points={line(WAITING.all)} fill="none" stroke={C.coral} strokeWidth="2.5" />
      <polyline points={line(WAITING.split)} fill="none" stroke={C.amber} strokeWidth="2.5" />
      <polyline points={line(WAITING.split4)} fill="none" stroke={C.ok} strokeWidth="2.5" />
      <text x={X(22)} y={Y(108)} fontSize="12" fill={C.coral} fontFamily={body} fontWeight="700">
        every note to the model
      </text>
      <text x={X(13.5)} y={Y(52)} fontSize="12" fill={C.amber} fontFamily={body} fontWeight="700">
        split
      </text>
      <text x={X(16)} y={Y(4)} fontSize="12" fill={C.ok} fontFamily={body} fontWeight="700">
        split, 4 at once
      </text>
      <text x="0" y="280" fontSize="12" fill={C.mute} fontFamily={body}>
        notes waiting for an answer, every second · 200 notes arriving at 20 per second · qwen2.5 7B on one laptop
      </text>
    </svg>
  );
}

// p95 latency (s) by arrival rate; null = not run
const P95: { name: string; c: string; ys: (number | null)[] }[] = [
  { name: 'every note, 1 at a time', c: C.coral, ys: [0.28, 15.5, 28.8, 37.1] },
  { name: 'every note, 4 at once', c: '#D9785F', ys: [null, 9.41, 19.9, null] },
  { name: 'split, 1 at a time', c: C.amber, ys: [0.28, 0.51, 4.79, 9.98] },
  { name: 'split, 4 at once', c: C.ok, ys: [null, null, 1.83, 6.08] },
];
const RATES = [3, 8, 20, 40];

function P95Chart() {
  const x0 = 70, w = 420, top = 16, h = 200, maxY = 40;
  const X = (i: number) => x0 + (i / (RATES.length - 1)) * w;
  const Y = (v: number) => top + h - (v / maxY) * h;
  return (
    <svg viewBox="0 0 720 276" role="img" aria-label="p95 latency by arrival rate. Every note to the model, one at a time: 0.28 s at 3 notes per second, 15.5 at 8, 28.8 at 20, 37.1 at 40. Four at once: 9.4 at 8, 19.9 at 20. Split, one at a time: 0.28, 0.51, 4.8, 10.0. Split, four at once: 1.8 at 20, 6.1 at 40">
      {[0, 10, 20, 30, 40].map((v) => (
        <g key={v}>
          <line x1={x0} x2={x0 + w} y1={Y(v)} y2={Y(v)} stroke={C.rule} />
          <text x={x0 - 8} y={Y(v) + 4} textAnchor="end" fontSize="11" fill={C.mute} fontFamily={mono}>
            {v} s
          </text>
        </g>
      ))}
      {RATES.map((r, i) => (
        <text key={r} x={X(i)} y={Y(0) + 18} textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
          {r}/s
        </text>
      ))}
      <text x={x0 + w / 2} y={Y(0) + 34} textAnchor="middle" fontSize="10.5" fill={C.mute} fontFamily={body}>
        arrival rate (the four rates we ran, evenly spaced)
      </text>
      {P95.map((s) => {
        const pts = s.ys.map((v, i) => (v === null ? null : [X(i), Y(v)])).filter((p): p is number[] => p !== null);
        return (
          <g key={s.name}>
            <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke={s.c} strokeWidth="2.5" />
            {pts.map((p, k) => (
              <circle key={k} cx={p[0]} cy={p[1]} r="4" fill={s.c} />
            ))}
          </g>
        );
      })}
      {P95.map((s, i) => (
        <g key={s.name}>
          <rect x="520" y={40 + i * 26} width="14" height="4" fill={s.c} />
          <text x="542" y={46 + i * 26} fontSize="12" fill={C.ink} fontFamily={body}>
            {s.name}
          </text>
        </g>
      ))}
      <text x="0" y="270" fontSize="12" fill={C.mute} fontFamily={body}>
        p95 latency (arrival to answer) by arrival rate · one run each · split: the rule picks pump notes, 74 of 200
      </text>
    </svg>
  );
}

export function SemanticFilterOnALiveStreamBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>A semantic filter on a live stream: when notes arrive faster than the model can read</h1>
      <p className="standfirst">
        A semantic operator over a stream never finishes. It has to keep up. We sent maintenance notes to a local 7B
        model at 3 to 40 per second. Reading every note, it handled about 5 a second; above that, the wait grew with
        every note, to 37 seconds at p95. Letting a rule answer "which part?" first sent 63 % fewer notes to the model,
        and that did more than running requests in parallel or batching notes into one call.
      </p>
      <PostByline />

      <p>
        The previous posts measured a semantic filter on a table, and an incremental SQL program on a stream. This one
        puts the two together. A semantic filter runs as a continuous query: "tell me when a note reports a problem
        with a pump". The notes do not wait for the model.
      </p>

      <h2>01 · Two papers on semantic operators over streams</h2>
      <p>
        Both come from one group at Brown University.
      </p>
      <p>
        <strong>Continuous Prompts</strong> (Chen, Raghavan, Çetintemel; arXiv 2512.03389, version 2, November 2026)
        turns one-shot prompts into "persistent semantic computations over unstructured streams". It has filter, map,
        aggregate, top-k and join, plus operators native to streams: windows that close when the topic changes, and
        groups that appear and retire as the stream moves. Each operator can be run by a language model, a small
        decision model or embeddings. A planner chooses the implementation, the model, how many tuples go into one call,
        and which operators to fuse. It learns the trade-off between throughput and accuracy, then picks the most
        accurate plan that still keeps up with the arrival rate. In the paper's words, "the planner never drops tuples
        to keep up".
      </p>
      <p>
        Their baseline is one model call per tuple, which is how Flink's <code>ML_PREDICT</code> works. Run on Flink 2.2
        against the same vLLM servers (three L40S GPUs), it managed about 17–18 tuples/s. As arrivals rose past 20 per
        second its p95 latency "climbs to tens of seconds", while the planner kept up to 200 per second with a p95 of a
        few seconds. Its end-to-end accuracy is measured against a GPT-4o pipeline, not human labels.
      </p>
      <p>
        <strong>VectraFlow</strong> (Chen, Liu, Raghavan, Çetintemel; arXiv 2604.03855, a 4-page demo paper) adds a
        semantic <em>event pattern</em>. A model reads each record once and emits typed, timestamped events per entity.
        A classic automaton, as in FlinkCEP, then matches sequences on those events, with negation and time windows. On 256 clinical notes and 5 patterns it reports F1 0.848 with GPT-4o-mini and 3.1 M
        tokens. Re-prompting the model with each patient's growing history at every step scored 0.675 with 14.6 M
        tokens, and ran out of memory on the local Qwen models. It does not study arrival rates. Neither paper links to its own code.
      </p>

      <h2>02 · Our test</h2>
      <p>
        The 200 maintenance notes from the second post, in the wording the keyword rule had never seen, arrive in a fixed
        shuffled order at a fixed rate: 3, 8, 20 or 40 per second. The arrival clock runs whatever the model is doing.
        Workers take notes first in, first out. Each note's arrival, start and answer times are recorded, so latency is
        waiting plus work. The model is qwen2.5 7B on Ollama on one laptop, asked for a single word, yes or no. We
        tried three plans:
      </p>
      <ul>
        <li>
          <strong>every note:</strong> each note goes to the model with "does it report a problem with a pump?";
        </li>
        <li>
          <strong>split:</strong> the rule from the second post answers "which part?" from names. Only notes about a
          pump, 74 of 200, go to the model, asked "is a symptom present?";
        </li>
        <li>
          <strong>batch:</strong> the split, but every waiting pump note goes in one call, up to 8.
        </li>
      </ul>
      <p>
        "Every note" and "split" also ran with four requests to the model at once, as Flink's{' '}
        <code>ML_PREDICT</code> can with its async option. Each configuration ran once.
      </p>

      <h2>03 · Above its throughput, the wait only grows</h2>
      <figure>
        <WaitingChart />
        <figcaption>
          At 20 notes a second, the "every note" plan had 151 notes waiting when the last one arrived. It needed 30 more
          seconds to answer them all. The split never had more than 62 waiting.
        </figcaption>
      </figure>
      <p>
        Asked one at a time, the model answered in about 0.2 s, about 5 notes a second. At 3 notes a second every plan
        answered within 0.4 s. At 8, the "every note" plan's p95 was 15.5 s, and at 40 it was 37 s. The wait keeps
        growing for as long as the stream runs faster than the model. Here the stream stopped after 200 notes, so the
        queue drained. A real log does not stop.
      </p>
      <figure>
        <P95Chart />
        <figcaption>
          The split stays under a second up to 8 notes a second and under 10 s at 40. Four concurrent requests help each
          plan, but not by four times.
        </figcaption>
      </figure>

      <h2>04 · What helped, and what did not</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Change</th>
              <th>Throughput while busy</th>
              <th>F1</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>every note, 1 at a time</td>
              <td>4.3–5.0 notes/s</td>
              <td>0.981</td>
            </tr>
            <tr>
              <td>every note, 4 at once</td>
              <td>5.8–6.5</td>
              <td>0.981</td>
            </tr>
            <tr>
              <td>split, 1 at a time</td>
              <td>11.3–14.0</td>
              <td>1.000</td>
            </tr>
            <tr>
              <td>split, 4 at once</td>
              <td>17.7</td>
              <td>1.000</td>
            </tr>
            <tr>
              <td>split, up to 8 notes per call</td>
              <td>8.2–15.3</td>
              <td>0.915–1.000</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        <em>Throughput while busy</em>: notes answered ÷ seconds a worker was working. For the split it counts the notes the
        rule answered at once. One run per rate.
      </p>
      <p>
        <strong>Sending fewer notes was the big lever.</strong> The split's throughput was 2.5–3 times that of sending
        every note, and in this run it was also more accurate (2 false alarms fewer). The model itself was no faster:
        the gain is the 126 notes the rule answered without it.
      </p>
      <p>
        <strong>Concurrency gave 20–30 %.</strong> One laptop GPU does all the work, so parallel requests only fill
        its idle moments.
      </p>
      <p>
        <strong>Batching did not pay here.</strong> At 8 notes a second the batch plan made 27 calls for the 74 pump
        notes and was busy 24 s; the split, one note per call, was busy 16 s. At 20 a second the two were even, and at
        40 batching was a little faster (15.3 against 13.3 notes a second). But at every rate where it actually batched,
        it missed 4–8 real problems.
        Continuous Prompts reports large gains from batching, but on vLLM, a server built to run many requests together
        on data-centre GPUs. Ollama on a laptop is not that server. Measure on the server you will run.
      </p>
      <p>
        <strong>How the model is asked mattered as much as which engine runs it.</strong> The same 7B model, called
        directly and asked for one word, scored F1 0.981 at about 0.2 s per note. In the second post, through LOTUS's
        prompts, it scored 0.911 at about 1.9 s per note; its calls there averaged about 29 output tokens (all three
        questions), while here the answer is capped at 3. Prompt, calling path and output length all changed at once,
        and each ran once.
      </p>

      <h2>05 · What a live semantic node needs</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Property</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>A measured throughput, next to its accuracy</td>
              <td>Below it, answers take under a second; above it, the wait grows without limit</td>
            </tr>
            <tr>
              <td>A stated overload policy</td>
              <td>Queue (latency grows), switch to a cheaper plan (Continuous Prompts), or shed load</td>
            </tr>
            <tr>
              <td>The split, first</td>
              <td>Rules and SQL answer what they can, and the model sees only the rows that need meaning</td>
            </tr>
            <tr>
              <td>Read once, store the answer</td>
              <td>
                VectraFlow's extractor and the "tags" from the third post: a judgement made once becomes a column that
                plain stream operators can use
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        That ends the research half of this series. Next: our own node design, from these five posts, and a demo.
      </p>

      <p className="foot-note">
        Sources: S. Chen, D. Raghavan, U. Çetintemel, "Continuous Prompts: Adaptive Semantic Query Processing over
        Unstructured Streams", arXiv 2512.03389 (v2, 2026); S. Chen, J. Liu, D. Raghavan, U. Çetintemel, "VectraFlow:
        Long-Horizon Semantic Processing over Data and Event Streams with LLMs", arXiv 2604.03855 (v1, 2026); Apache
        Flink 2.1 release notes (ML_PREDICT). Our run: qwen2.5:7b on Ollama, on an M4 Pro laptop with 24 GB; the notes
        are synthetic, written by a language model from labelled events.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function SemanticFilterOnALiveStreamFigure() {
  const X = (t: number) => 20 + (t / 41) * 480;
  const Y = (n: number) => 170 - (n / 160) * 130;
  const line = (ys: number[]) => ys.map((n, t) => `${X(t)},${Y(n)}`).join(' ');
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Notes waiting at 20 notes per second: every note to the model peaks at 151 and drains at 40 seconds; the split peaks at 62 and is done at 14 seconds">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        RUN
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        notes waiting, 20 arriving per second
      </text>
      <line x1="20" x2="500" y1="170" y2="170" stroke="var(--rule)" />
      <polyline points={line(WAITING.all)} fill="none" stroke="var(--coral)" strokeWidth="3" />
      <polyline points={line(WAITING.split)} fill="none" stroke="var(--ok)" strokeWidth="3" />
      <text x={X(18)} y={Y(140)} fontSize="13" fill="var(--coral)" fontFamily="var(--f-body)" fontWeight="700">
        every note to the model
      </text>
      <text x={X(14.5)} y={Y(40)} fontSize="13" fill="var(--ok)" fontFamily="var(--f-body)" fontWeight="700">
        rule first
      </text>
      <text x="20" y="196" fontSize="12" fill="var(--ink-mute)" fontFamily="var(--f-mono)">
        0 s
      </text>
      <text x="500" y="196" textAnchor="end" fontSize="12" fill="var(--ink-mute)" fontFamily="var(--f-mono)">
        40 s
      </text>
    </svg>
  );
}
