import { PostByline } from '../components/blog/post-context';
import { PostVideo } from '../components/blog/post-video';
// Engineering · Real-time data · part 2. Numbers from the measured demo run (hands-on results 2026-11-17 part 6:
// demo/night.py --failure, 6.0 min) and the recorded take (2026-11-18 part 1). The fab's data is synthetic; the
// pump's vibration curve is the story generator's own formula (what the platform was fed).

const C = { ch: 'var(--ok)', pg: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const mono = 'var(--f-mono)';
const body = 'var(--f-body)';

// ---- what runs ----
function StackDiagram() {
  const box = (x: number, y: number, w: number, h: number, title: string, lines: string[], color: string) => (
    <g transform={`translate(${x} ${y})`}>
      <rect width={w} height={h} rx="10" fill="none" stroke={color} strokeWidth="2" />
      <text x="14" y="26" fontSize="15" fontWeight="700" fill={color} fontFamily={body}>
        {title}
      </text>
      {lines.map((l, i) => (
        <text key={l} x="14" y={50 + i * 20} fontSize="13" fill={C.ink} fontFamily={body}>
          {l}
        </text>
      ))}
    </g>
  );
  const arrow = (x1: number, y1: number, x2: number, y2: number) => (
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={C.mute} strokeWidth="1.6" markerEnd="url(#arr)" />
  );
  return (
    <svg viewBox="0 0 720 300" role="img" aria-label="The stack: the fab's streams go into Kafka; three Flink jobs (alert rules, the equipment check before every lot, 1-minute roll-ups) decide and write back to Kafka; ClickHouse stores every stream; PostgreSQL holds the rules and baselines; Prometheus and Grafana watch it all">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill={C.mute} />
        </marker>
      </defs>
      {box(0, 20, 150, 130, 'The fab', ['sensor readings', 'tool health', 'MES: lots, recipes,', 'maintenance'], C.mute)}
      {box(200, 20, 120, 130, 'Kafka', ['one topic', 'per stream', 'contracts in a', 'schema registry'], C.ink)}
      {box(370, 0, 170, 150, 'Flink', ['alert rules', '(rules as rows)', 'equipment check', 'before every lot', '1-minute roll-ups'], C.amber)}
      {box(590, 20, 130, 130, 'ClickHouse', ['every stream,', 'every decision —', 'the history', 'for questions'], C.ch)}
      {box(370, 210, 170, 80, 'PostgreSQL', ['rules, baselines'], C.pg)}
      {box(590, 210, 130, 80, 'Prometheus', ['+ Grafana, 17', 'alert rules'], C.mute)}
      {arrow(150, 85, 198, 85)}
      {arrow(320, 60, 368, 60)}
      {arrow(368, 110, 322, 110)}
      <path d="M260 150 V178 H655 V154" fill="none" stroke={C.mute} strokeWidth="1.6" markerEnd="url(#arr)" />
      <text x="560" y="172" fontSize="11" fill={C.mute} fontFamily={body}>
        every topic
      </text>
      {arrow(455, 208, 455, 152)}
    </svg>
  );
}

// ---- the night, 01:30-02:30 ----
const EVENTS: { t: string; label: string; kind: 'mes' | 'alert' | 'watch' | 'hold' | 'alarm'; row: number }[] = [
  { t: '01:40', label: 'recipe change, ETCH-07', kind: 'mes', row: 0 },
  { t: '01:44', label: 'R-005', kind: 'alert', row: 1 },
  { t: '01:48', label: 'R-004', kind: 'alert', row: 1 },
  { t: '02:10', label: 'R-001 → RCA', kind: 'alert', row: 1 },
  { t: '02:14', label: 'R-005', kind: 'alert', row: 1 },
  { t: '02:00', label: 'WATCH LOT2503', kind: 'watch', row: 2 },
  { t: '02:10', label: 'HOLD LOT2504', kind: 'hold', row: 2 },
  { t: '02:20', label: 'HOLD LOT2505', kind: 'hold', row: 3 },
  { t: '02:23', label: 'the pump would reach its alarm', kind: 'alarm', row: 3 },
  { t: '02:25', label: 'pump replaced', kind: 'mes', row: 0 },
];
const KIND = {
  mes: { color: 'var(--ink-mute)', name: 'MES' },
  alert: { color: '#C98A16', name: 'alert (ETCH-07/C)' },
  watch: { color: '#C98A16', name: 'lot check' },
  hold: { color: 'var(--coral)', name: 'lot check' },
  alarm: { color: 'var(--coral)', name: '' },
};
const minutes = (t: string) => {
  const [h, m] = t.split(':').map(Number);
  return (h - 1) * 60 + m - 30; // minutes after 01:30
};

function NightTimeline() {
  const x0 = 70, W = 470;
  const x = (t: string) => x0 + (minutes(t) / 60) * W;
  const order = [...EVENTS].sort((a, b) => minutes(a.t) - minutes(b.t) || a.row - b.row);
  const rowH = 26, top = 24;
  const bottom = top + order.length * rowH;
  return (
    <svg viewBox={`0 0 720 ${bottom + 44}`} role="img" aria-label="The night on a timeline: 01:40 recipe change on ETCH-07; alerts on ETCH-07/C at 01:44, 01:48, 02:10 (R-001, trigger root-cause analysis) and 02:14; lot checks on ETCH-05/B: WATCH at 02:00, HOLD at 02:10 and 02:20; the pump would have reached its alarm level at 02:22:54; replaced at 02:25">
      {['01:30', '01:45', '02:00', '02:15', '02:30'].map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={top - 10} y2={bottom} stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(t)} y={bottom + 18} textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {t}
          </text>
        </g>
      ))}
      <rect x={x('02:23')} y={top - 10} width={x('02:25') - x('02:23')} height={bottom - top + 10} fill="var(--coral)" opacity="0.08" />
      {order.map((e, i) => {
        const cx = x(e.t), cy = top + i * rowH;
        const kind = e.kind === 'mes' ? 'MES' : e.kind === 'alert' ? 'alert · ETCH-07/C' : e.kind === 'alarm' ? '' : 'lot check · ETCH-05/B';
        return (
          <g key={e.t + e.label}>
            <text x="0" y={cy + 4} fontSize="12" fill={C.mute} fontFamily={mono}>
              {e.t}
            </text>
            <line x1={x0} x2={cx} y1={cy} y2={cy} stroke={C.rule} />
            {e.kind === 'alarm' ? (
              <path d={`M${cx} ${cy - 7} L${cx + 7} ${cy + 5} L${cx - 7} ${cy + 5} z`} fill="none" stroke={KIND.alarm.color} strokeWidth="2" />
            ) : (
              <circle cx={cx} cy={cy} r={e.kind === 'hold' ? 7 : 5} fill={KIND[e.kind].color} />
            )}
            <text x={cx + 14} y={cy + 4} fontSize="13" fill={C.ink} fontFamily={body} fontWeight={e.kind === 'hold' ? 700 : 500}>
              {e.label}
              <tspan fill={C.mute} fontWeight="400">{`  ${kind}`}</tspan>
            </text>
          </g>
        );
      })}
      <text x={x0} y={bottom + 38} fontSize="12" fill={C.mute} fontFamily={body}>
        night time, 11 Nov · replayed at 30× (the hour in 2 minutes)
      </text>
    </svg>
  );
}

// ---- the pump: vibration (the generator's curve) and the decisions ----
const VIB = [
  2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.02, 2.04, 2.07, 2.1, 2.12, 2.16, 2.19, 2.22, 2.26,
  2.3, 2.35, 2.39, 2.44, 2.5, 2.56, 2.62, 2.69, 2.76, 2.84, 2.92, 3.01, 3.11, 3.21, 3.32, 3.44, 3.57, 3.71, 3.85, 4.01,
  4.18, 4.36, 4.56, 4.77, 5.0, 5.24, 5.5, 5.79, 6.09, 6.41, 6.76, 7.13, 7.53, 2.8, 2.8, 2.8, 2.8, 2.8, 2.8,
];
function PumpChart() {
  const x0 = 60, W = 620, y0 = 250, H = 210, vmax = 8;
  const x = (m: number) => x0 + (m / 60) * W;
  const y = (v: number) => y0 - (v / vmax) * H;
  const before = VIB.slice(0, 55).map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const after = `M${x(55)} ${y(2.8)} L${x(60)} ${y(2.8)}`;
  const mark = (m: number, label: string, color: string, dy: number) => (
    <g>
      <line x1={x(m)} x2={x(m)} y1={y(VIB[m])} y2={y0} stroke={color} strokeDasharray="3 3" />
      <circle cx={x(m)} cy={y(VIB[m])} r="6" fill={color} />
      <text x={x(m) - 8} y={y(VIB[m]) + dy} textAnchor="end" fontSize="12" fontWeight="700" fill={color} fontFamily={body}>
        {label}
      </text>
    </g>
  );
  return (
    <svg viewBox="0 0 720 300" role="img" aria-label="ETCH-05/B pump vibration rising from 2 mm/s at 01:42 towards the 7.1 mm/s alarm level, reached at 02:22:54; the check put lots on WATCH at 02:00 (2.76 mm/s on the curve) and HOLD at 02:10 (3.85) and 02:20 (6.09); replaced at 02:25, the new pump at 2.8 mm/s">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily={mono}>
        SYNTHETIC
      </text>
      <text x="104" y="15" fontSize="13" fill={C.mute} fontFamily={body}>
        ETCH-05/B pump vibration, mm/s · the generator's curve, without noise
      </text>
      {[0, 2, 4, 6, 8].map((v) => (
        <g key={v}>
          <line x1={x0} x2={x0 + W} y1={y(v)} y2={y(v)} stroke={C.rule} strokeDasharray="2 4" />
          <text x={x0 - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill={C.mute} fontFamily={mono}>
            {v}
          </text>
        </g>
      ))}
      <line x1={x0} x2={x0 + W} y1={y(7.1)} y2={y(7.1)} stroke="var(--coral)" strokeWidth="1.5" />
      <text x={x0 + W} y={y(7.1) - 6} textAnchor="end" fontSize="12" fill="var(--coral)" fontFamily={body}>
        alarm 7.1
      </text>
      <line x1={x0} x2={x0 + W} y1={y(4.5)} y2={y(4.5)} stroke="#C98A16" strokeWidth="1" strokeDasharray="5 4" />
      <text x={x0 + 4} y={y(4.5) - 6} fontSize="12" fill="#C98A16" fontFamily={body}>
        warning 4.5
      </text>
      <path d={before} fill="none" stroke={C.ink} strokeWidth="2.2" />
      <path d={after} fill="none" stroke="var(--ok)" strokeWidth="2.2" />
      {mark(30, 'WATCH LOT2503', '#C98A16', -12)}
      {mark(40, 'HOLD LOT2504', 'var(--coral)', -12)}
      {mark(50, 'HOLD LOT2505', 'var(--coral)', -12)}
      <text x={x(55) + 6} y={y(2.8) - 10} fontSize="12" fill="var(--ok)" fontFamily={body}>
        new pump
      </text>
      {['01:30', '01:45', '02:00', '02:15', '02:30'].map((t, i) => (
        <text key={t} x={x(i * 15)} y={y0 + 20} textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
          {t}
        </text>
      ))}
    </svg>
  );
}

// ---- the failure: seconds after the TaskManager was killed ----
function FailureChart() {
  const ev = [
    { s: 12.2, label: 'ScrapeTargetDown fires', color: '#C98A16', ours: true },
    { s: 12.7, label: 'FlinkCheckpointFailed fires', color: '#C98A16', ours: true },
    { s: 41.3, label: 'Flink records the failure', color: C.mute, ours: false },
    { s: 42.7, label: 'FlinkJobRestarted fires', color: '#C98A16', ours: true },
    { s: 52.9, label: 'FlinkJobNotRunning fires', color: '#C98A16', ours: true },
    { s: 81.8, label: 'the job runs again', color: 'var(--ok)', ours: false },
  ];
  const x0 = 20, W = 660;
  const x = (s: number) => x0 + (s / 90) * W;
  return (
    <svg viewBox="0 0 720 250" role="img" aria-label="After the TaskManager was killed: our alerts fired at 12.2 and 12.7 seconds; Flink recorded the failure at 41.3 seconds; FlinkJobRestarted at 42.7 and FlinkJobNotRunning at 52.9; the job ran again at 81.8 seconds, the TaskManager having been down for 60 seconds">
      <rect x={x(0)} y="186" width={x(60) - x(0)} height="10" rx="3" fill="var(--coral)" opacity="0.35" />
      <text x={x(0)} y="214" fontSize="12" fill={C.mute} fontFamily={body}>
        TaskManager down (60 s)
      </text>
      <line x1={x0} x2={x0 + W} y1="200" y2="200" stroke={C.rule} />
      {[0, 15, 30, 45, 60, 75, 90].map((s) => (
        <text key={s} x={x(s)} y="236" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
          {s} s
        </text>
      ))}
      {ev.map((e, i) => {
        const y = 22 + i * 28;
        const right = x(e.s) > 470;
        return (
          <g key={e.label}>
            <line x1={x(e.s)} x2={x(e.s)} y1={y + 4} y2="200" stroke={e.color} strokeDasharray="2 3" opacity="0.6" />
            <circle cx={x(e.s)} cy={y} r="5" fill={e.color} />
            <text x={right ? x(e.s) - 10 : x(e.s) + 10} y={y + 4} textAnchor={right ? 'end' : 'start'} fontSize="12" fill={C.ink} fontFamily={body} fontWeight={e.ours ? 600 : 500}>
              {e.s} s · {e.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function OneNightBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Real-time data</p>
      <h1>One night at the fab</h1>
      <p className="standfirst">
        A recipe change slowly drifts one etch chamber while, two tools away, a vacuum pump wears out. We replayed that
        night through a real streaming stack — Kafka, Flink, ClickHouse — and let it catch both, explain them, and
        survive a Flink worker being killed. One script, about six minutes, nothing staged.
      </p>
      <PostByline />

      <p>
        Demos of data platforms usually show a dashboard. The questions that matter at 02:00 are different: did the
        platform notice in time, did it stop the next lot before the damage, can an engineer find out why in a minute —
        and does any of it survive when a machine dies? We wrote the night down as a story, generated its data (a
        synthetic fab: no real fab data), and built a demo that plays it against the running system and checks every
        decision the system makes.
      </p>
      <p className="pull">
        A demo should check itself: every alert and every lot decision compared with the expected answer, and timed
        from the reading that caused it.
      </p>

      <PostVideo
        src="/blog/realtime/one-night.mp4"
        poster="/blog/realtime/one-night-poster.jpg"
        caption="The demo, recorded as it ran (3:24): Flink starting its jobs fresh, the night at 30×, the investigation in ClickHouse, a TaskManager killed. Parts are sped up; the timings in the text are from a separate measured run of the same script."
      />

      <h2>01 · What runs</h2>
      <figure>
        <StackDiagram />
        <figcaption>
          The stack on one laptop. Flink decides in real time; ClickHouse keeps the history; PostgreSQL holds the
          rules and the equipment baselines; Prometheus watches all of it.
        </figcaption>
      </figure>
      <ul>
        <li>
          <strong>Alert rules are rows</strong>, not code: "ETCH-07/C rf_power, 1-minute average above 1450, trigger root-cause
          analysis" is one line in a table that Flink reads, so a new rule needs no new job.
        </li>
        <li>
          <strong>An equipment check before every lot</strong>: when MES tracks a lot into a chamber, Flink looks at that
          chamber's health — the trend of its pump, not only the level — and answers GO, WATCH or HOLD.
        </li>
        <li>
          <strong>Exactly-once</strong>: after a crash, no alert is lost and none is sent twice (measured earlier by
          killing the TaskManager mid-story three times: 6 of 6 alerts, none lost or doubled — with at-least-once, 3 came
          twice).
        </li>
      </ul>

      <h2>02 · The night</h2>
      <p>
        The demo replays 01:30–02:30 at 30 times real speed: 237,712 events — sensor readings, the tools' own health
        sensors, MES track-ins — on one clock. The terminal prints every decision as it arrives:
      </p>
      <figure>
        <NightTimeline />
        <figcaption>
          Every alert and every lot not cleared to GO that night (the other 57 lot checks said GO). The shaded strip is the worn pump at its alarm level, from 02:22:54
          until it was replaced at 02:25 — after both holds.
        </figcaption>
      </figure>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Measured run</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Alerts</td>
              <td>
                <strong>4 of 4</strong>, equal to the offline model — each 1.2–1.3 s after the reading that triggered it, at 30× replay
              </td>
            </tr>
            <tr>
              <td>Lot checks</td>
              <td>
                <strong>60 of 60</strong>, equal to the model — WATCH, HOLD and HOLD 2.1–2.3 s after the track-in (mostly
                the 2 s exactly-once commit)
              </td>
            </tr>
            <tr>
              <td>After the pump swap</td>
              <td>the chamber's health GO every minute to the end of the hour (02:25–02:28) — a new pump is not mistaken for wear</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>03 · Holding the lot before the pump reaches its alarm</h2>
      <p>
        A limit check — "stop when vibration passes the alarm" — would have let every lot into ETCH-05/B, including the
        one running when the pump reached its alarm. The check looks at the trend instead: a rising line, clearly more
        than noise and outside this chamber's normal band, projected forward to the alarm. Even
        the warning limit (4.5 mm/s) would have stopped only LOT2505, not LOT2504.
      </p>
      <figure>
        <PumpChart />
        <figcaption>
          LOT2504 was held at 02:10, about 13 minutes before the pump reached its alarm level (02:22:54); LOT2505,
          which would have run into it, was held too. The cost of that margin: LOT2504 itself would have finished about
          3 minutes before the alarm. Synthetic data: the story generator's vibration curve; the check saw the measured
          minute averages 2.68, 3.8 and 5.94 mm/s.
        </figcaption>
      </figure>

      <h2>04 · Why? Asking the history</h2>
      <p>
        Alert R-001 says "trigger root-cause analysis". The deep store — ClickHouse, a month of readings — answers
        the questions an engineer would ask, each in milliseconds:
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>Answer</th>
              <th>ms</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>What changed on that tool in the two hours before?</td>
              <td>01:40, recipe change: rf_power setpoint 1440 → 1448</td>
              <td>2.2</td>
            </tr>
            <tr>
              <td>Which lots ran on ETCH-07/C after it, with what yield?</td>
              <td>five lots, yield 0.83</td>
              <td>10.8</td>
            </tr>
            <tr>
              <td>One chamber or all of them?</td>
              <td>ETCH-07/C 0.904 → 0.834; every other chamber unchanged</td>
              <td>3.1</td>
            </tr>
            <tr>
              <td>Did the measured CD move too?</td>
              <td>45.6 nm against 45.0 elsewhere, all in spec</td>
              <td>2.9</td>
            </tr>
            <tr>
              <td>Was this sensor ever above 1450 in the 30 days before? (every minute)</td>
              <td>never — highest 1442.5</td>
              <td>187</td>
            </tr>
            <tr>
              <td>Why was LOT2504 held?</td>
              <td>vibration 3.8 mm/s, alarm in 30 min; only chamber B of the tool</td>
              <td>0.9–3.3</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        From an alert to its cause in five questions: the recipe change, one chamber, the yield drop. The answers are
        plain SQL over everything the platform has stored; the same questions are what the next step — an agent doing
        the root-cause analysis — will ask.
      </p>

      <h2>05 · A failure, live</h2>
      <p>
        Last act: the TaskManager — the process that runs every Flink job — is killed for 60 seconds, as when a machine
        dies. What notices, and when?
      </p>
      <figure>
        <FailureChart />
        <figcaption>
          Seconds after the kill. Our monitoring fired about 29 s before Flink itself recorded the failure; the job
          was back from its last checkpoint at 81.8 s.
        </figcaption>
      </figure>
      <p>
        16 of the 17 alert rules in the monitoring were tested by causing their failure on purpose before they were
        trusted; low disk only in unit tests, to protect a disk shared with other work. Three rules changed after the
        drills: one never fired as written, two fired late or falsely.
      </p>

      <h2>06 · What it shows, and what is not there yet</h2>
      <ul>
        <li>
          <strong>Real time, checked</strong>: every decision equal to a model computed offline from the same data,
          within about 2 seconds of the reading at 30× replay; at the fab's real pace an alert takes about 6.5 s,
          mostly the 5 s wait for late readings.
        </li>
        <li>
          <strong>Explainable</strong>: the decision and the evidence are in one store, queried in milliseconds.
        </li>
        <li>
          <strong>Survivable</strong>: a lost process is noticed by monitoring first, and the jobs resume from their
          checkpoints.
        </li>
      </ul>
      <p>
        Not yet: the root-cause agent that R-001 asks for (the investigation above is still a script), and notifications
        to a channel people use. Next in this series: how the alert job turns readings into alerts, where its 6.5 seconds
        go, and what it costs to make that exactly-once.
      </p>

      <p className="foot-note">
        Method: synthetic fab data (no real fab data) replayed at 30× into Kafka 4.4 on one laptop (Apple M4 Pro, 24 GB);
        Flink 2.2.1, ClickHouse 26.8, PostgreSQL 18, Prometheus + Grafana. Timings are from one measured run of the demo
        script (6.0 min); the video is a separate take of the same script, so its numbers differ by up to about 3 s.
        Versions as of 2026-11-18.
      </p>
    </>
  );
}

// The "Latest" slot figure: the night's decisions on one line.
export function OneNightFigure() {
  const x0 = 20, W = 480;
  const x = (t: string) => x0 + (minutes(t) / 60) * W;
  const dots = [
    { t: '01:40', c: 'var(--ink-mute)' },
    { t: '01:44', c: '#C98A16' },
    { t: '01:48', c: '#C98A16' },
    { t: '02:00', c: '#C98A16' },
    { t: '02:10', c: 'var(--coral)' },
    { t: '02:14', c: '#C98A16' },
    { t: '02:20', c: 'var(--coral)' },
    { t: '02:25', c: 'var(--ok)' },
  ];
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="The night of 11 Nov, 01:30 to 02:30: a recipe change, four alerts, a watch and two holds, a pump replaced — all decided live, 4 of 4 alerts and 60 of 60 lot checks equal to the model">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        LIVE DEMO
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        11 Nov, 01:30–02:30 · replayed at 30×
      </text>
      <line x1={x0} x2={x0 + W} y1="100" y2="100" stroke="var(--rule)" strokeWidth="2" />
      {dots.map((d) => (
        <circle key={d.t} cx={x(d.t)} cy="100" r={d.c === 'var(--coral)' ? 9 : 6} fill={d.c} />
      ))}
      {['01:30', '02:00', '02:30'].map((t) => (
        <text key={t} x={x(t)} y="128" textAnchor="middle" fontSize="12" fill="var(--ink-mute)" fontFamily="var(--f-mono)">
          {t}
        </text>
      ))}
      <text x={x0} y="172" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        4/4 alerts · 60/60 lot checks · = the model
      </text>
      <text x={x0} y="196" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        2 lots held before the pump's alarm · a TaskManager killed, back at 82 s
      </text>
    </svg>
  );
}
