import { PostByline } from '../components/blog/post-context';
// Engineering · Real-time data · part 3. Numbers from the hands-on results of 2026-11-12 (F1-F3) and 2026-11-13
// (F4, S1): one laptop, synthetic fab readings. Live delays are single runs at the fab's real pace; the throughput and
// matcher runs replay a backlog as fast as the job can read it.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const mono = 'var(--f-mono)';
const body = 'var(--f-body)';

// ---- where the seconds go: window end -> Kafka -> ClickHouse (exactly-once, 2 s checkpoints) ----
function DelayChart() {
  const x0 = 20, W = 660, max = 11;
  const x = (s: number) => x0 + (s / max) * W;
  const parts = [
    { from: 0, to: 5, label: 'watermark: wait for late readings', color: 'var(--ink-mute)', op: 0.35 },
    { from: 5, to: 5.3, label: '', color: C.amber, op: 1 },
    { from: 5.3, to: 6.45, label: 'commit', color: C.coral, op: 0.85 },
    { from: 6.45, to: 9.6, label: "ClickHouse's default flush", color: C.ok, op: 0.55 },
  ];
  return (
    <svg viewBox="0 0 720 240" role="img" aria-label="Seconds from the end of a window to the alert, exactly-once with 2 s checkpoints, at the fab's real pace: 5 s watermark, about 0.3 s of Flink's own work, 0 to 2 s waiting for the checkpoint to commit (median 1.1 s) — in one live run 6.4–6.5 s in Kafka and 9.0–10.2 s as a row in ClickHouse with its default flush">
      {parts.map((p) => (
        <g key={p.from}>
          <rect x={x(p.from)} y="70" width={x(p.to) - x(p.from)} height="44" fill={p.color} opacity={p.op} />
          {p.label && (
            <text x={(x(p.from) + x(p.to)) / 2} y="97" textAnchor="middle" fontSize="12" fill={C.ink} fontFamily={body} fontWeight="600">
              {p.label}
            </text>
          )}
        </g>
      ))}
      <line x1={x(5.15)} x2={x(5.15)} y1="62" y2="40" stroke={C.amber} />
      <text x={x(5.15)} y="34" textAnchor="middle" fontSize="12" fill={C.amber} fontFamily={body} fontWeight="700">
        Flink's own work: about 0.3 s
      </text>
      {[
        { s: 6.45, t: 'one run: in Kafka 6.4–6.5 s', y: 140 },
        { s: 9.6, t: 'a ClickHouse row 9.0–10.2 s', y: 162 },
      ].map((m) => (
        <g key={m.t}>
          <line x1={x(m.s)} x2={x(m.s)} y1="114" y2={m.y - 12} stroke={C.ink} strokeDasharray="2 3" />
          <text x={x(m.s)} y={m.y} textAnchor="middle" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
            {m.t}
          </text>
        </g>
      ))}
      {[0, 2, 4, 6, 8, 10].map((s) => (
        <text key={s} x={x(s)} y="200" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
          {s} s
        </text>
      ))}
      <text x={x0} y="228" fontSize="12" fill={C.mute} fontFamily={body}>
        seconds after the window ends · live, at the fab's real pace · commit: 0–2 s, median 1.1 s (10 samples)
      </text>
    </svg>
  );
}

// ---- the pattern rules warn earlier ----
function PatternChart() {
  const x0 = 20, W = 660;
  const x = (m: number) => x0 + ((m - 90) / 50) * W; // minutes after 00:00, 01:30..02:20
  const evs = [
    { m: 100, label: '01:40 recipe change', sub: 'MES', color: C.mute },
    { m: 104, label: '01:44 R-005', sub: 'trend: 5 rises over 6 minutes, +5.5 W', color: C.amber },
    { m: 108, label: '01:48 R-004', sub: '9 minutes above the centre line', color: C.amber },
    { m: 130, label: '02:10 R-001', sub: 'limit: 1-minute average 1452.9 > 1450', color: C.coral },
  ];
  return (
    <svg viewBox="0 0 720 230" role="img" aria-label="ETCH-07/C rf_power: recipe change at 01:40; the trend rule R-005 fires at 01:44 and the run rule R-004 at 01:48, while every value is inside the limit; the limit rule R-001 fires at 02:10, 22–26 minutes later">
      <rect x={x(104)} y="40" width={x(130) - x(104)} height="10" rx="3" fill={C.amber} opacity="0.3" />
      <text x={(x(104) + x(130)) / 2} y="32" textAnchor="middle" fontSize="12" fill={C.amber} fontFamily={body} fontWeight="700">
        22–26 minutes earlier, every value still inside the limit
      </text>
      <line x1={x0} x2={x0 + W} y1="80" y2="80" stroke={C.rule} strokeWidth="2" />
      {evs.map((e, i) => {
        const y = 110 + i * 28;
        const right = x(e.m) > 470;
        return (
          <g key={e.label}>
            <line x1={x(e.m)} x2={x(e.m)} y1="80" y2={y - 4} stroke={e.color} strokeDasharray="2 3" />
            <circle cx={x(e.m)} cy="80" r="6" fill={e.color} />
            <text x={right ? x(e.m) - 8 : x(e.m) + 8} y={y + 4} textAnchor={right ? 'end' : 'start'} fontSize="12" fill={C.ink} fontFamily={body}>
              <tspan fontWeight="700">{e.label}</tspan>
              <tspan fill={C.mute}>{`  ${e.sub}`}</tspan>
            </text>
          </g>
        );
      })}
      {[90, 100, 110, 120, 130, 140].map((m) => (
        <text key={m} x={x(m)} y="68" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
          {`0${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`}
        </text>
      ))}
    </svg>
  );
}

// ---- many rules: indexed vs naive, Flink DataStream job, log scale ----
const MATCH = [
  { n: '10', idx: 0.18, naive: 0.13 },
  { n: '1,000', idx: 0.2, naive: 3.4 },
  { n: '10,000', idx: 0.2, naive: 33.4 },
  { n: '100,000', idx: 0.25, naive: 769 },
];
function MatcherChart() {
  const x0 = 110, W = 520, lo = Math.log10(0.1), hi = Math.log10(1000);
  const x = (v: number) => x0 + ((Math.log10(v) - lo) / (hi - lo)) * W;
  return (
    <svg viewBox="0 0 720 270" role="img" aria-label="Microseconds per reading to find the rules it breaks, in a Flink job: with an index 0.18, 0.20, 0.20, 0.25 µs for 10, 1,000, 10,000 and 100,000 rules; checking every rule 0.13, 3.4, 33.4 and 769 µs">
      {[0.1, 1, 10, 100, 1000].map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1="10" y2="215" stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(v)} y="232" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {v < 1 ? v : v.toLocaleString('en-US')} µs
          </text>
        </g>
      ))}
      {MATCH.map((r, i) => {
        const y = 22 + i * 50;
        return (
          <g key={r.n}>
            <text x={x0 - 10} y={y + 14} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={mono} fontWeight="600">
              {r.n}
            </text>
            <rect x={x0} y={y} width={x(r.idx) - x0} height="14" rx="2" fill={C.ok} />
            <text x={x(r.idx) + 6} y={y + 11} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.idx}
            </text>
            <rect x={x0} y={y + 18} width={x(r.naive) - x0} height="14" rx="2" fill={C.coral} />
            <text x={x(r.naive) + 6} y={y + 29} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.naive}
            </text>
          </g>
        );
      })}
      <text x="0" y="258" fontSize="12" fill={C.mute} fontFamily={body}>
        rules ·{' '}
        <tspan fill="var(--ok)" fontWeight="700">
          indexed
        </tspan>{' '}
        ·{' '}
        <tspan fill="var(--coral)" fontWeight="700">
          check every rule
        </tspan>{' '}
        · µs per reading, log scale · synthetic rules, Flink job at parallelism 1
      </text>
    </svg>
  );
}

// ---- crashes: messages per 6 alerts ----
function CrashChart() {
  const x0 = 170, W = 450, max = 9;
  const x = (v: number) => x0 + (v / max) * W;
  const rows = [
    { label: 'at-least-once', note: '3 crashes', ok: 6, dup: 3 },
    { label: 'exactly-once', note: '3 crashes', ok: 6, dup: 0 },
  ];
  return (
    <svg viewBox="0 0 720 170" role="img" aria-label="The TaskManager killed mid-story, three times per guarantee: at-least-once delivered 9 messages for 6 alerts each time (3 duplicates); exactly-once delivered exactly 6, with none lost">
      {rows.map((r, i) => {
        const y = 20 + i * 54;
        return (
          <g key={r.label}>
            <text x="0" y={y + 16} fontSize="14" fill={C.ink} fontFamily={body} fontWeight="700">
              {r.label}
            </text>
            <text x="0" y={y + 34} fontSize="12" fill={C.mute} fontFamily={body}>
              {r.note}, each
            </text>
            <rect x={x0} y={y} width={x(r.ok) - x0} height="26" fill={C.ok} />
            <text x={(x0 + x(r.ok)) / 2} y={y + 18} textAnchor="middle" fontSize="13" fill="var(--ground)" fontFamily={body} fontWeight="700">
              6 alerts
            </text>
            {r.dup > 0 && (
              <>
                <rect x={x(r.ok)} y={y} width={x(r.ok + r.dup) - x(r.ok)} height="26" fill={C.coral} />
                <text x={(x(r.ok) + x(r.ok + r.dup)) / 2} y={y + 18} textAnchor="middle" fontSize="13" fill="var(--ground)" fontFamily={body} fontWeight="700">
                  +3 twice
                </text>
              </>
            )}
            {r.dup === 0 && (
              <text x={x(r.ok) + 10} y={y + 18} fontSize="13" fill={C.ink} fontFamily={body}>
                none lost, none twice
              </text>
            )}
          </g>
        );
      })}
      <text x="0" y="150" fontSize="12" fill={C.mute} fontFamily={body}>
        messages that reached a normal Kafka reader and ClickHouse, for the story's 6 alerts · TaskManager killed with
        docker kill
      </text>
    </svg>
  );
}

// ---- throughput by parallelism and time format ----
function ThroughputChart() {
  const rows = [
    { p: 1, demo: 83635, simple: 157148 },
    { p: 2, demo: 147133, simple: 295352 },
    { p: 4, demo: 297242, simple: 544171 },
  ];
  const x0 = 120, W = 480, max = 600000;
  const x = (v: number) => x0 + (v / max) * W;
  return (
    <svg viewBox="0 0 720 250" role="img" aria-label="Readings per second the alert job handles: parallelism 1, 83,635 with the demo's timestamp parsing and 157,148 with the simplest; parallelism 2, 147,133 and 295,352; parallelism 4, 297,242 and 544,171. A big fab sends 1,120 per second">
      {[0, 200000, 400000, 600000].map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1="10" y2="190" stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(v)} y="206" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {v === 0 ? '0' : `${v / 1000}k`}
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = 20 + i * 58;
        return (
          <g key={r.p}>
            <text x={x0 - 10} y={y + 22} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="600">
              parallelism {r.p}
            </text>
            <rect x={x0} y={y} width={x(r.demo) - x0} height="16" rx="2" fill={C.amber} />
            <text x={x(r.demo) + 6} y={y + 12} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.demo.toLocaleString('en-US')}
            </text>
            <rect x={x0} y={y + 20} width={x(r.simple) - x0} height="16" rx="2" fill={C.ok} />
            <text x={x(r.simple) + 6} y={y + 32} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.simple.toLocaleString('en-US')}
            </text>
          </g>
        );
      })}
      <text x="0" y="234" fontSize="12" fill={C.mute} fontFamily={body}>
        readings/s ·{' '}
        <tspan fill="#C98A16" fontWeight="700">
          any-offset timestamps (the demo)
        </tspan>{' '}
        ·{' '}
        <tspan fill="var(--ok)" fontWeight="700">
          one fixed format
        </tspan>{' '}
        · a big fab: 1,120 readings/s
      </text>
    </svg>
  );
}

export function FlinkAlertsBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Real-time data</p>
      <h1>From a sensor reading to an alert, in Flink</h1>
      <p className="standfirst">
        Our alert job turns a fab's sensor readings into alerts: limits, patterns, rules as rows. We measured where its
        seconds go, what exactly-once costs, how far it scales on one laptop — and the traps that dropped alerts without
        an error.
      </p>
      <PostByline />

      <p>
        In the <a href="/blog/one-night-at-the-fab">night at the fab</a>, every alert arrived within seconds and the job
        came back after a worker was killed; the crash tests below lost no alert. This post opens the job behind it: Apache Flink 2.2.1 reading the sensor stream from
        Kafka, deciding, and writing alerts back to Kafka, from where ClickHouse stores them. All data is synthetic; all
        numbers are measured on one laptop.
      </p>

      <h2>01 · A rule is a row</h2>
      <p>
        An engineer's rule — "ETCH-07/C rf_power, 1-minute average above 1450, high, trigger root-cause analysis" — is
        one row in a PostgreSQL table, not code. The job cuts the readings into 1-minute and 30-second windows by the
        readings' own time, compares each window with the one before, and looks up the rules for that chamber and its
        tool family when the window closes. A rule fires when the value <em>crosses</em> the limit, so a chamber that
        stays high raises one alert, not one a minute.
      </p>
      <ul>
        <li>
          <strong>A new rule applies from now on</strong>: within about 10 s by design (the lookup cache
          expires after 10 s; not timed), and never to minutes already past. We tested it with a rule the night's past minutes would have broken: it stayed silent. A first
          version on another engine, with a plain join, did re-send old crossings as fresh alerts.
        </li>
        <li>
          <strong>The cost</strong>: Flink keeps no rule table of its own. The rules live in a database, and the cache
          time is a choice between load on that database and how fast a change takes effect.
        </li>
      </ul>

      <h2>02 · Where the seconds go</h2>
      <p>
        Sending readings at the fab's real pace and timing each alert from the end of its window:
      </p>
      <figure>
        <DelayChart />
        <figcaption>
          Most of the delay is a choice: the watermark waits 5 s for late readings before it calls a minute complete.
          Flink's own work is about 0.3 s; exactly-once adds the wait for the next checkpoint, 0–2 s. ClickHouse's
          Kafka reader flushes every 7.5 s by default; a 1 s flush, measured later, brings its part to about 0.6 s.
        </figcaption>
      </figure>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Live run (two alerts each)</th>
              <th>In Kafka</th>
              <th>Row in ClickHouse</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>at-least-once, 2 s checkpoints</td>
              <td>5.37, 5.30 s</td>
              <td>10.76, 6.43 s</td>
            </tr>
            <tr>
              <td>
                <strong>exactly-once, 2 s</strong> (what we run)
              </td>
              <td>
                <strong>6.52, 6.41 s</strong>
              </td>
              <td>
                <strong>9.03, 10.20 s</strong>
              </td>
            </tr>
            <tr>
              <td>exactly-once, 10 s</td>
              <td>9.42, 9.30 s</td>
              <td>12.70, 13.89 s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        For comparison, the same rules on RisingWave 3.1.1, run side by side on the same stream, took 8.3–10.6 s to
        Kafka, while Flink took 5.2–5.4 s in the same runs (at-least-once): 3–6 s of RisingWave's own on top of the same
        watermark. The watermark is the lever: if sensors are known to report promptly, a shorter wait saves up to 5 s
        — at the price of dropping readings that arrive later than it (not measured).
      </p>

      <h2>03 · Patterns warn earlier</h2>
      <p>
        A limit sees one window. A drift shows first as a <em>shape</em> over several — what fabs catch with SPC run
        rules. Flink SQL expresses them with <code>MATCH_RECOGNIZE</code>, pattern matching over rows in time order:
        "nine minutes in a row above the centre line", "five rises in a row, at least 3 W in total". They are rows in
        the same rule table.
      </p>
      <figure>
        <PatternChart />
        <figcaption>
          The night's drift on ETCH-07/C. The pattern rules fired 22–26 minutes before the limit rule, live within
          5.3–5.5 s of their window like the limit rules (measured at-least-once, before exactly-once became the
          default): pattern matching adds no visible delay.
        </figcaption>
      </figure>
      <p>
        The price is chance alarms. In the offline model, the same two patterns (centre line 12, no minimum rise) on the
        eight ETCH <em>pressure</em> series, where nothing was wrong, raised 2 alarms in the hour; a minimum rise of 0.2
        would remove one of them. Which sensors get which run rules, and with what minimum rise, is an
        engineering choice per parameter — to be checked on history before it is switched on.
      </p>

      <h2>04 · A hundred thousand rules</h2>
      <p>
        If engineers register their own rules, the table grows to thousands of rows. Checking every rule for every
        reading grows with the number of rules. The alternative is an index: look up the rules for this chamber and
        sensor, keep their limits sorted, and find the ones a new reading crossed with two binary searches. We built
        both as a Flink job in Java, with the rules broadcast to every worker as messages:
      </p>
      <figure>
        <MatcherChart />
        <figcaption>
          The index stays flat — 0.18 to 0.25 µs per reading from 10 to 100,000 rules. Checking every rule is 3,100×
          slower at 100,000 rules, and the whole job falls from 746,000 to 1,293 readings per second. Every alert of
          both was equal to an independent model's.
        </figcaption>
      </figure>
      <p>
        100,000 rules are a 5.9 MB savepoint, and a rule change is one message — no restart. The limit of this design:
        each worker rebuilds its whole index after a change (33 ms at 100,000 rules), fine for rules that change a few
        times a minute.
      </p>

      <h2>05 · Exactly-once, tested by crashing it</h2>
      <p>
        We killed the TaskManager — the process that runs the job — just after the story's first three alerts were
        written (checkpoints every 2 s, every 10 s, or before the first one), started it again 3 s later, and counted every message against the six alerts the story should raise:
      </p>
      <figure>
        <CrashChart />
        <figcaption>
          No alert was lost in any of the six crashes. At-least-once sends the three alerts written before the crash
          again after the restart; exactly-once writes them in a Kafka transaction that the crash aborted, and
          ClickHouse's reader skips uncommitted messages.
        </figcaption>
      </figure>
      <p>
        Exactly-once costs time, not alerts: an alert becomes visible only when the next checkpoint commits, so the
        extra wait falls anywhere between zero and the checkpoint interval — a median of <strong>1.1 s</strong> at 2 s
        checkpoints and 4.1 s at 10 s (10 samples each). A checkpoint of this job takes milliseconds, so we run
        exactly-once every 2 s. The job was back 15–21 s after the kill, 10–14 s of it Flink noticing the dead worker; a machine that stays
        down was not tested here.
      </p>

      <h2>06 · How much can it take?</h2>
      <p>
        A synthetic big fab — 560 sensors at two readings a second, 1,120 readings per second — three hours of it, read
        as fast as the job can:
      </p>
      <figure>
        <ThroughputChart />
        <figcaption>
          Near-linear to 4 parallel readers. The limit is the first task — reading Kafka, parsing JSON and the
          timestamp; the windows, rule lookups and pattern matching after it were never the bottleneck.
        </figcaption>
      </figure>
      <ul>
        <li>
          <strong>About half the work is reading the timestamp.</strong> Our job accepts any ISO time-zone offset and converts
          it; with one fixed format the same job is 1.8–2.0× faster. The data contract with the sources decides
          throughput.
        </li>
        <li>
          <strong>Partitions set the ceiling.</strong> A Kafka partition is read by one reader; in a first round on 6
          partitions, parallelism 4 reached only 198,000 because two readers had twice the work of the others.
        </li>
        <li>
          With the demo's 5 rules, one 8-CPU laptop keeps up with 75 to 486 such fabs. More rules, more state and real
          data change that picture.
        </li>
      </ul>

      <h2>07 · The traps that made no error</h2>
      <p>
        The worst bugs gave no error. The first two dropped alerts and were found only by comparing the job's alerts with
        an offline model of the rules:
      </p>
      <ul>
        <li>
          <strong>Idle partitions dropped readings.</strong> With an idle timeout, a pause made every Kafka partition
          "idle"; when the catch-up burst came, the first partition moved the job's clock ahead alone and the others'
          readings counted as late — two alerts gone, no error. The timeout is off now; the price is that one silent
          partition holds every alert back, so a
          stalled watermark raises an alert; heartbeat messages into every partition would prevent the stall.
        </li>
        <li>
          <strong>Two lookups shared a filter.</strong> The job looked up one rule table three times with different
          filters; Flink pushed them down and two lookups got the same one. The trend rule never fired. PostgreSQL's
          statement log showed it; each rule kind now has its own view.
        </li>
        <li>
          <strong>A time-zone offset was ignored.</strong> One timestamp function read 02:09:58+09:00 as 02:09:58 UTC.
          The job now converts offsets itself, and that is the timestamp work above.
        </li>
        <li>
          <strong>The planner never returned.</strong> A rule test written as a chain of ORs never finished planning:
          EXPLAIN did not return, no error. Written as one number — how far past its limit the window is — it plans in 0.5 s.
        </li>
      </ul>

      <h2>08 · What we keep</h2>
      <ul>
        <li>Rules as rows, applied from now on; patterns for drift, tuned per sensor before they are switched on.</li>
        <li>Exactly-once with 2 s checkpoints: about a second of delay for no duplicates after a crash.</li>
        <li>An index for rules at scale, and a cheap, fixed timestamp format agreed with the sources.</li>
        <li>An offline model of every rule, to compare the job against — it found the alerts that went missing.</li>
      </ul>
      <p>
        Next in this series: the equipment check that holds a lot before a pump reaches its alarm, and the three
        versions it took.
      </p>

      <p className="foot-note">
        Method: synthetic fab data on one laptop (Apple M4 Pro, 24 GB; Docker with 8 CPUs). Flink 2.2.1 (SQL job;
        the rule matcher as a Java DataStream job), Kafka 4.4, PostgreSQL 18 for the rules, ClickHouse 26.8,
        RisingWave 3.1.1 for comparison. Live delays: single runs at the fab's real pace (36 readings per second).
        Throughput and matcher: a backlog read at full speed, one run each (an earlier matcher run gave 1,059 µs instead
        of 769 for checking every rule — that time varies a lot; the index's hardly does). Versions as of 2026-11-18.
      </p>
    </>
  );
}

// The "Latest" slot figure: where the seconds go.
export function FlinkAlertsFigure() {
  const x0 = 20, W = 470, max = 10.5;
  const x = (s: number) => x0 + (s / max) * W;
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="From a window's end to an alert, one live run: 5 s watermark, 0.3 s of Flink, about 1 s exactly-once commit — about 6.5 s in Kafka; 9–10 s in ClickHouse with its default flush">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        MEASURED
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        a window's end → an alert, live
      </text>
      <rect x={x(0)} y="60" width={x(5) - x(0)} height="34" fill="var(--ink-mute)" opacity="0.35" />
      <rect x={x(5)} y="60" width={x(5.3) - x(5)} height="34" fill="#C98A16" />
      <rect x={x(5.3)} y="60" width={x(6.45) - x(5.3)} height="34" fill="var(--coral)" opacity="0.85" />
      <rect x={x(6.45)} y="60" width={x(9.6) - x(6.45)} height="34" fill="var(--ok)" opacity="0.55" />
      <text x={x(2.5)} y="82" textAnchor="middle" fontSize="12" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        watermark 5 s
      </text>
      <text x={x(6.45)} y="122" textAnchor="middle" fontSize="13" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="700">
        Kafka ≈6.5 s

      </text>
      <text x={x(9.6)} y="122" textAnchor="end" fontSize="13" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="700">
        ClickHouse 9–10 s
      </text>
      <text x={x0} y="172" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        Flink's own work ≈0.3 s · exactly-once ≈1 s
      </text>
      <text x={x0} y="196" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        6 crashes, no alert lost · up to 297k readings/s as built
      </text>
    </svg>
  );
}
