import { PostByline } from '../components/blog/post-context';
import { PostVideo } from '../components/blog/post-video';
// Engineering · Real-time data · part 1. Every number comes from the hands-on runs of 2026-11-17/18 (C4 parts 1-4):
// one laptop, synthetic fab readings, one run per setup after a fairness review. Nothing here is simulated.


// ---- charts (SVG in the site's colours; every value from the measured runs) ----
const C = { ch: 'var(--ok)', pg: 'var(--coral)', ts: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)' };
const DB = [
  { key: 'ch', label: 'ClickHouse', color: C.ch },
  { key: 'pg', label: 'PostgreSQL', color: C.pg },
  { key: 'ts', label: 'TimescaleDB', color: C.ts },
] as const;
const mono = 'var(--f-mono)';
const body = 'var(--f-body)';

function Legend({ y }: { y: number }) {
  return (
    <g transform={`translate(0 ${y})`}>
      {DB.map((d, i) => (
        <g key={d.key} transform={`translate(${i * 150} 0)`}>
          <rect width="12" height="12" rx="2" fill={d.color} />
          <text x="18" y="11" fontSize="13" fill={C.ink} fontFamily={body}>
            {d.label}
          </text>
        </g>
      ))}
    </g>
  );
}

// two side-by-side bar groups: write rate and size on disk
function WriteAndSizeChart() {
  const write = { ch: 915, pg: 96, ts: 84 };
  const size = { ch: 213, pg: 18582, ts: 772 };
  const panel = (x: number, title: string, vals: Record<string, number>, max: number, fmt: (v: number) => string, note: string) => (
    <g transform={`translate(${x} 0)`}>
      <text x="0" y="16" fontSize="14" fontWeight="700" fill={C.ink} fontFamily={body}>
        {title}
      </text>
      <text x="0" y="34" fontSize="12" fill={C.mute} fontFamily={body}>
        {note}
      </text>
      {DB.map((d, i) => {
        const w = Math.max(3, (260 * vals[d.key]) / max);
        return (
          <g key={d.key} transform={`translate(0 ${56 + i * 40})`}>
            <text x="0" y="12" fontSize="12" fill={C.mute} fontFamily={body}>
              {d.label}
            </text>
            <rect x="0" y="17" width={w} height="14" rx="3" fill={d.color} />
            <text x={w + 8} y="29" fontSize="13" fill={C.ink} fontFamily={mono}>
              {fmt(vals[d.key])}
            </text>
          </g>
        );
      })}
    </g>
  );
  return (
    <svg viewBox="0 0 720 190" role="img" aria-label="Write rate: ClickHouse 915,000 rows per second, PostgreSQL 96,000, TimescaleDB 84,000. Size on disk: 213 MiB, 18,582 MiB, 772 MiB">
      {panel(0, 'Write rate (replay-safe)', write, 915, (v) => `${v}k rows/s`, 'higher is better')}
      {panel(370, 'Size on disk, 30 days', size, 18582, (v) => `${v.toLocaleString('en-US')} MiB`, 'lower is better')}
    </svg>
  );
}

// every question, three databases, on a log time axis
function QuestionsChart() {
  const qs = [
    { q: "One sensor's month", ch: 157, pg: 3040, ts: 357 },
    { q: "Every chamber's daily average", ch: 2050, pg: 8400, ts: 7600 },
    { q: 'Fab-wide hourly, one day', ch: 154, pg: 660, ts: 470 },
    { q: 'Readings stored for one day', ch: 24, pg: 52, ts: 18 },
    { q: 'One chamber, 10 minutes', ch: 4.0, pg: 0.5, ts: 0.9 },
    { q: 'Every reading of one lot', ch: 9.0, pg: 2.3, ts: 720 },
    { q: 'Latest reading of every sensor', ch: 4740, pg: 5.8, ts: 487 },
  ];
  const x0 = 250, W = 440, lo = Math.log10(0.3), hi = Math.log10(30000);
  const x = (ms: number) => x0 + ((Math.log10(ms) - lo) / (hi - lo)) * W;
  const ticks = [1, 10, 100, 1000, 10000];
  const label = (ms: number) => (ms >= 1000 ? `${ms / 1000} s` : `${ms} ms`);
  return (
    <svg viewBox="0 0 720 420" role="img" aria-label="Median time per question in ClickHouse, PostgreSQL and TimescaleDB on a logarithmic axis: ClickHouse fastest on three of the four history questions (TimescaleDB on the one-day count), PostgreSQL on the three lookups">
      <Legend y={0} />
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1="34" y2="360" stroke="var(--rule)" strokeDasharray="2 4" />
          <text x={x(t)} y="378" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {label(t)}
          </text>
        </g>
      ))}
      <text x={x0 + W / 2} y="402" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={body}>
        median time per question · log scale · left is faster
      </text>
      {qs.map((r, i) => {
        const y = 52 + i * 46;
        const best = DB.reduce((a, d) => (r[d.key] < r[a.key] ? d : a), DB[0]);
        return (
          <g key={r.q}>
            <text x="0" y={y + 4} fontSize="13" fill={C.ink} fontFamily={body}>
              {r.q}
            </text>
            <line x1={x(Math.min(r.ch, r.pg, r.ts))} x2={x(Math.max(r.ch, r.pg, r.ts))} y1={y} y2={y} stroke="var(--rule)" strokeWidth="2" />
            {DB.map((d) => (
              <circle key={d.key} cx={x(r[d.key])} cy={y} r={d.key === best.key ? 7 : 5} fill={d.color} stroke={d.key === best.key ? C.ink : 'none'} strokeWidth="1.5" />
            ))}
            <text x={x(r[best.key])} y={y - 11} textAnchor="middle" fontSize="11" fill={C.ink} fontFamily={mono}>
              {label(r[best.key])}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// horizontal bars on a log scale, one per setup
function LogBars({ rows, unit, aria, axis, linear }: { rows: { label: string; v: number; text: string; color: string; note?: string }[]; unit: 'ms' | 's'; aria: string; axis: string; linear?: boolean }) {
  const toMs = (v: number) => (unit === 's' ? v * 1000 : v);
  const lo = Math.log10(1), hi = Math.log10(10000), W = 360, x0 = 250;
  const max = Math.max(...rows.map((r) => r.v));
  const w = (v: number) =>
    Math.max(4, linear ? (v / max) * W : ((Math.log10(Math.max(toMs(v), 1)) - lo) / (hi - lo)) * W);
  return (
    <svg viewBox={`0 0 720 ${rows.length * 44 + 40}`} role="img" aria-label={aria}>
      {rows.map((r, i) => (
        <g key={r.label} transform={`translate(0 ${10 + i * 44})`}>
          <text x="0" y="14" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="600">
            {r.label}
          </text>
          {r.note && (
            <text x="0" y="31" fontSize="11" fill={C.mute} fontFamily={body}>
              {r.note}
            </text>
          )}
          <rect x={x0} y="6" width={w(r.v)} height="16" rx="3" fill={r.color} />
          <text x={x0 + w(r.v) + 8} y="19" fontSize="13" fill={C.ink} fontFamily={mono}>
            {r.text}
          </text>
        </g>
      ))}
      <text x={x0} y={rows.length * 44 + 30} fontSize="12" fill={C.mute} fontFamily={body}>
        {axis}
      </text>
    </svg>
  );
}

export function DeepStoreCompareBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Real-time data</p>
      <h1>ClickHouse, PostgreSQL or TimescaleDB for a fab's sensor history?</h1>
      <p className="standfirst">
        A fab's sensors never stop talking, and every alert ends with the same request: show me what this chamber did
        before. We put the same 93.5 million synthetic readings into three databases, with the same guarantees and the same
        questions, and measured. The answer is not "one wins": each wins where its design says it should.
      </p>
      <PostByline />

      <p>
        02:10. An alert fires on one etch chamber. The first questions an engineer asks are all about history: what
        changed on that tool, which lots ran after it, is it one chamber or all of them, has this sensor ever looked like
        this before. The store that answers them — we call it the <em>deep store</em> — holds every sensor reading for
        weeks, and it is written to all day long.
      </p>
      <p>
        In our real-time platform that store is ClickHouse. The obvious question from anyone who has run a database is:
        why not PostgreSQL, which everyone already knows? Or TimescaleDB, PostgreSQL made for time series? Instead of
        arguing, we put the store behind one interface and switched it by configuration.
      </p>
      <p className="pull">
        Choose a database by measuring the job it will do: the same data, the same guarantees, the same questions —
        and every answer identical before any time counts.
      </p>

      <PostVideo
        src="/blog/realtime/deep-store-compare.mp4"
        poster="/blog/realtime/deep-store-compare-poster.jpg"
        caption="The whole post in 90 seconds: the fair setup, writes and size, who wins where, and what we chose. English and Korean captions."
      />

      <h2>01 · The setup, made fair</h2>
      <ul>
        <li>
          <strong>The data</strong>: 30 days of a synthetic fab — 93.5 million sensor readings, 18 sensors, 43,000 lots
          — written day by day in time order, in batches of 100,000 rows, as a live ingest would. Every database got the
          same bytes (the same checksum per day).
        </li>
        <li>
          <strong>The same guarantee</strong>: a reading sent twice (Kafka can deliver twice) is stored once, the last
          one winning. ClickHouse does it with a ReplacingMergeTree and <code>FINAL</code> where it matters;
          PostgreSQL with a primary key and <code>INSERT … ON CONFLICT DO UPDATE</code>.
        </li>
        <li>
          <strong>The same machine</strong>: one laptop (Apple M4 Pro, Docker with 8 CPUs), each database limited to
          2 GB of memory, PostgreSQL tuned for that size.
        </li>
        <li>
          <strong>Each database in its own idiom</strong>: PostgreSQL 18 got a covering primary key and partitions per
          day; TimescaleDB 2.31 a hypertable with column compression; ClickHouse 26.8 its usual sorted, compressed
          table. Every one of the seven questions returned the same answer in all three.
        </li>
        <li>
          <strong>Not identical, and worth knowing</strong>: PostgreSQL syncs every commit to disk; ClickHouse, by
          default, does not sync each insert — part of its write lead. ClickHouse also shared its server with our
          running demo.
        </li>
      </ul>
      <p>
        One more rule: the first run was reviewed for fairness before we believed it. The review found real problems —
        PostgreSQL had no index carrying the value, opened a connection per question and did not let the last replayed
        write win; ClickHouse used <code>FINAL</code> where it changes nothing; TimescaleDB's "latest" question was not
        written its own way — and every number below is from the run after the fixes.
      </p>

      <h2>02 · Writing and keeping 30 days</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>ClickHouse</th>
              <th>PostgreSQL</th>
              <th>TimescaleDB</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Write, replay-safe</td>
              <td>
                <strong>915,000 rows/s</strong>
              </td>
              <td>96,000 rows/s</td>
              <td>84,000 rows/s (71,000 with compression)</td>
            </tr>
            <tr>
              <td>Size on disk, 30 days</td>
              <td>
                <strong>213 MiB</strong>
              </td>
              <td>18,582 MiB</td>
              <td>772 MiB</td>
            </tr>
            <tr>
              <td>Bytes per reading</td>
              <td>~2.4</td>
              <td>~100 in the table, plus indexes as large again</td>
              <td>~8.7</td>
            </tr>
          </tbody>
        </table>
      </div>
      <figure>
        <WriteAndSizeChart />
        <figcaption>
          The same 93.5 million readings, written in 100,000-row batches with replays allowed, then stored for 30 days.
          One run per database on one laptop.
        </figcaption>
      </figure>
      <p>
        ClickHouse stores each column sorted by sensor and time and compresses it; a timestamp that grows by half a
        second compresses to almost nothing. PostgreSQL stores rows, and its primary key on three text columns is a
        second copy of most of them. TimescaleDB's compression closes most of that gap — 24 times smaller than plain
        PostgreSQL — but not all of it.
      </p>

      <h2>03 · Asking the questions</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Question (median of 5)</th>
              <th>ClickHouse</th>
              <th>PostgreSQL</th>
              <th>TimescaleDB</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>One sensor's 1-minute averages over 30 days</td>
              <td>
                <strong>157 ms</strong>
              </td>
              <td>3,040 ms</td>
              <td>357 ms</td>
            </tr>
            <tr>
              <td>Every chamber's daily average, all history</td>
              <td>
                <strong>2.05 s</strong>
              </td>
              <td>24.6 s as planned (8.4 s with a sequential scan)</td>
              <td>7.6 s</td>
            </tr>
            <tr>
              <td>Every tool's hourly averages for one day</td>
              <td>
                <strong>154 ms</strong>
              </td>
              <td>660 ms</td>
              <td>470 ms</td>
            </tr>
            <tr>
              <td>Readings stored for one day</td>
              <td>24 ms</td>
              <td>52 ms</td>
              <td>
                <strong>18 ms</strong>
              </td>
            </tr>
            <tr>
              <td>One chamber, a 10-minute window</td>
              <td>4.0 ms</td>
              <td>
                <strong>0.5 ms</strong>
              </td>
              <td>0.9 ms</td>
            </tr>
            <tr>
              <td>Every reading of one lot</td>
              <td>9.0 ms</td>
              <td>
                <strong>2.3 ms</strong>
              </td>
              <td>720 ms</td>
            </tr>
            <tr>
              <td>The latest reading of every sensor</td>
              <td>4,740 ms</td>
              <td>
                <strong>5.8 ms</strong>
              </td>
              <td>487 ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <figure>
        <QuestionsChart />
        <figcaption>
          Who wins where: each dot is a database's median time for one question (the winner outlined and labelled).
          ClickHouse is fastest on three of the four history questions (TimescaleDB on the one-day count), PostgreSQL
          on the three lookups. PostgreSQL's daily-average dot is
          its best plan (8.4 s); the plan it chose took 24.6 s.
        </figcaption>
      </figure>
      <p>
        The pattern is the design. Questions that read many rows — a sensor's month, the whole fab's day — are what
        a column store is built for: ClickHouse is 4 to 19 times faster than PostgreSQL there (2 times on a single day's
        count). Questions an index
        answers — one lot, one short window, the newest value — are what a b-tree is built for, and PostgreSQL wins
        them. TimescaleDB's compressed batches lose most of that index advantage: its lot and "latest" lookups were 80
        to 310 times slower than plain PostgreSQL's (a per-batch bloom filter finds a lot's readings in 80 ms; this
        question's count of distinct sensors makes it 720 ms).
      </p>
      <p className="q">
        One surprise worth knowing: with the covering index in place, PostgreSQL 18's planner chose an index skip scan
        for the full-history question, expected 1.9 million groups where there are 248, and spilled to disk — 24.6 s,
        where the sequential scan it did not choose takes 8.4 s.
      </p>

      <h2>04 · ClickHouse's answer to the questions it lost</h2>
      <p>
        ClickHouse has its own tools for lookups, so we measured them the same way, as two more configurations:
      </p>
      <ul>
        <li>
          <strong>A small "latest" table kept by a materialized view</strong>: every insert also writes the newest
          reading of each sensor (at most 18 rows per batch). The latest-reading question went from 4.7 s to{' '}
          <strong>2.0 ms</strong> — faster than PostgreSQL's 5.8 ms — for a few KB of disk and 14% of the write rate.
        </li>
        <li>
          <strong>A projection sorted by lot</strong>: a second copy of the table inside ClickHouse, used automatically
          when a question filters by lot. One lot went from 8.1 to 5.9 ms — still slower than PostgreSQL's 2.3 ms —
          for another 14% of the write rate and 3.9 times the disk. On a 2 GB server, merging the whole table with the
          projection ran out of memory; merging one day at a time did not.
        </li>
      </ul>
      <figure>
        <LogBars
          unit="ms"
          aria="The latest reading of every sensor: ClickHouse 4,740 ms, ClickHouse with a latest table 2.0 ms, PostgreSQL 5.8 ms, TimescaleDB 487 ms"
          axis="median time · log scale"
          rows={[
            { label: 'ClickHouse', note: 'reads every row', v: 4740, text: '4.7 s', color: C.ch },
            { label: 'ClickHouse + "latest" table', note: 'a few KB, −14% write rate', v: 2.0, text: '2.0 ms', color: C.ch },
            { label: 'PostgreSQL', note: 'walks its primary key', v: 5.8, text: '5.8 ms', color: C.pg },
            { label: 'TimescaleDB', note: 'compressed batches', v: 487, text: '487 ms', color: C.ts },
          ]}
        />
        <figcaption>"What is the newest reading of every sensor?" — the question ClickHouse lost, and its answer.</figcaption>
      </figure>
      <p>
        Keeping a small answer up to date while writing made the "latest" lookup almost free. A second copy of the whole
        table bought 2 ms on lot lookups for 3.9 times the disk — not worth it here; for lots queried all day it might
        be.
      </p>

      <h2>05 · TimescaleDB: not the middle it looks like</h2>
      <p>
        On paper TimescaleDB is the best of both: PostgreSQL's SQL and indexes with column compression. Measured, it is
        3.6 times ClickHouse's size, 11 to 13 times slower to write, 2 to 4 times slower on history questions — and its
        lookups are far slower than plain PostgreSQL's. Two more things matter in operation:
      </p>
      <ul>
        <li>
          <strong>A replay into compressed days is refused by default</strong>: a write that would decompress more
          than 100,000 rows in one transaction fails. With the limit lifted, the day was stored once at 28,000 rows/s
          and grew the table by 1.2 GiB until it was compressed again. A pipeline that replays Kafka into old days has
          to plan for this.
        </li>
        <li>
          <strong>The compression is not open source</strong> in the OSI sense: it is under the Timescale License (free
          to use, except offering TimescaleDB as a hosted service). The Apache-licensed build has no compression.
        </li>
      </ul>

      <h2>06 · From Kafka to a stored row</h2>
      <p>
        A deep store fills itself from the event stream. ClickHouse reads Kafka on its own; PostgreSQL needs a writer —
        here a Flink job with the JDBC sink, upserting on the same key. At 10,000 readings per second, with a probe
        reading every second:
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>ClickHouse, default flush</th>
              <th>ClickHouse, 1 s flush</th>
              <th>Flink → PostgreSQL, 1 s flush</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Kafka to a stored row, median</td>
              <td>4.2 s</td>
              <td>0.64 s</td>
              <td>0.59 s</td>
            </tr>
            <tr>
              <td>A backlog of 2 M readings, the reader restarted</td>
              <td>43,000 rows/s</td>
              <td>273,000 rows/s</td>
              <td>38,000 rows/s (one Flink task)</td>
            </tr>
            <tr>
              <td>The whole topic, a freshly created reader</td>
              <td>181,000 rows/s</td>
              <td>290,000 rows/s</td>
              <td>—</td>
            </tr>
          </tbody>
        </table>
      </div>
      <figure>
        <LogBars
          unit="s"
          linear
          aria="Kafka to a stored row, median: ClickHouse with its default flush 4.2 s, with a 1 second flush 0.64 s, Flink into PostgreSQL 0.59 s"
          axis="median, from Kafka's acknowledgement to a stored row"
          rows={[
            { label: 'ClickHouse, default flush', note: 'a block every 7.5 s', v: 4.2, text: '4.2 s', color: C.ch },
            { label: 'ClickHouse, 1 s flush', note: 'one setting changed', v: 0.64, text: '0.64 s', color: C.ch },
            { label: 'Flink → PostgreSQL, 1 s flush', note: 'JDBC sink, upsert', v: 0.59, text: '0.59 s', color: C.pg },
          ]}
        />
        <figcaption>10,000 readings per second, a probe reading every second, 90 probes per setup.</figcaption>
      </figure>
      <p>
        With the same one-second flush, both get a reading stored equally fast. ClickHouse's default flush adds up to 7.5
        seconds — change it to the delay you can accept. On throughput, a fresh ClickHouse reader is several times
        faster than one Flink task; one result we cannot explain yet: a ClickHouse reader detached and attached again
        with the default flush drained a backlog at only 43,000 rows/s. And ClickHouse needs no extra job to run.
      </p>

      <h2>07 · What we chose</h2>
      <ul>
        <li>
          <strong>ClickHouse for the history of readings</strong> — it writes 9.5 times faster in 1/87 of the disk
          and answers history questions several times faster; with a small table kept by a view it also answers "the
          latest value".
        </li>
        <li>
          <strong>PostgreSQL for what is small, changing and looked up by key</strong> — the alert rules, the
          equipment baselines, the latest state of each lot. It already holds the rules and baselines in our platform.
        </li>
        <li>
          <strong>Keep the store behind an interface</strong>: the next candidate, or a bigger fab, is a configuration
          entry and one more run.
        </li>
      </ul>
      <p>
        What we did not test: many clients at once, updates and deletes (PostgreSQL's strength), a fab 10 to 100 times
        bigger, more than one Flink task or ClickHouse consumer; TimescaleDB's continuous aggregates and hypercore
        options; and exactly-once delivery into PostgreSQL (the JDBC sink here is at-least-once plus upsert). Next in
        this series: how the same platform raises
        an alert in seconds, and what happens to it when a server dies.
      </p>

      <p className="foot-note">
        Method: synthetic fab readings (no real fab data) on one laptop (Apple M4 Pro, 24 GB; Docker with 8 CPUs), each
        database limited to 2 GB of memory. ClickHouse 26.8, PostgreSQL 18.1, TimescaleDB 2.31 on PostgreSQL 18, Flink
        2.2.1, Kafka 4.4. One run per configuration after a review of the first run's fairness; every answer was checked
        to be identical across the databases. Versions as of 2026-11-18.
      </p>
    </>
  );
}

// The "Latest" slot figure: size on disk for the same 30 days of readings.
export function DeepStoreCompareFigure() {
  const rows = [
    { label: 'ClickHouse', mib: 213, color: 'var(--ok)' },
    { label: 'TimescaleDB', mib: 772, color: '#C98A16' },
    { label: 'PostgreSQL', mib: 18582, color: 'var(--coral)' },
  ];
  const W = 300;
  const max = 18582;
  return (
    <svg
      viewBox="0 0 520 210"
      role="img"
      aria-label="Size on disk of the same 93.5 million readings: ClickHouse 213 MiB, TimescaleDB 772 MiB, PostgreSQL 18,582 MiB"
    >
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        MEASURED
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        93.5 M readings, 30 days · size on disk
      </text>
      {rows.map((r, i) => {
        const w = Math.max(4, (W * r.mib) / max);
        return (
          <g key={r.label} transform={`translate(0 ${48 + i * 52})`}>
            <text x="0" y="14" fontSize="14" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
              {r.label}
            </text>
            <rect x="0" y="22" width={w} height="14" rx="3" fill={r.color} />
            <text x={w + 10} y="34" fontSize="14" fill="var(--ink)" fontFamily="var(--f-mono)">
              {r.mib.toLocaleString('en-US')} MiB
            </text>
          </g>
        );
      })}
    </svg>
  );
}
