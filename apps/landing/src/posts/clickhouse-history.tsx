import { PostByline } from '../components/blog/post-context';
// Engineering · Real-time data · part 5. Numbers from the hands-on results of 2026-11-13 (C1, C2) and 2026-11-16
// (C3): one laptop, synthetic fab readings. Lab tables are copies of the deep store's sensor table that differ in one
// thing each; query times are medians of 5 runs with ClickHouse's query caches off.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const mono = 'var(--f-mono)';
const body = 'var(--f-body)';

// ---- size per column, by codec ----
const CODECS = [
  { col: 'timestamp', codec: 'LZ4 (default)', mb: 468, color: C.coral },
  { col: 'timestamp', codec: 'Delta + ZSTD(1)', mb: 0.9, color: C.ok },
  { col: 'value', codec: 'LZ4 (default)', mb: 318, color: C.coral },
  { col: 'value', codec: 'ZSTD(1)', mb: 206, color: C.ok },
  { col: 'value', codec: 'Gorilla + ZSTD(1)', mb: 501, color: C.amber },
  { col: 'value', codec: 'Decimal(9,2), T64 + ZSTD(1)', mb: 121, color: C.mute },
];
function CodecChart() {
  const x0 = 260, W = 380, max = 550;
  const x = (v: number) => x0 + (v / max) * W;
  return (
    <svg viewBox="0 0 720 300" role="img" aria-label="Compressed size of one column of 93.45 million readings. Timestamp: LZ4, the default, 468 MB; Delta plus ZSTD 0.9 MB. Value: LZ4 318 MB; ZSTD 206 MB; Gorilla plus ZSTD 501 MB; as Decimal(9,2) with T64 plus ZSTD 121 MB">
      {[0, 100, 200, 300, 400, 500].map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1="8" y2="252" stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(v)} y="268" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {v}
          </text>
        </g>
      ))}
      {CODECS.map((r, i) => {
        const y = 12 + i * 40 + (i >= 2 ? 10 : 0);
        return (
          <g key={r.col + r.codec}>
            <text x={x0 - 10} y={y + 15} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body}>
              <tspan fontWeight="700">{r.col}</tspan>
              <tspan fill={C.mute}>{` · ${r.codec}`}</tspan>
            </text>
            <rect x={x0} y={y} width={Math.max(x(r.mb) - x0, 2)} height="20" rx="2" fill={r.color} />
            <text x={x(r.mb) + 6} y={y + 15} fontSize="12" fill={C.ink} fontFamily={mono} fontWeight={r.mb < 1 ? 700 : 400}>
              {r.mb} MB
            </text>
          </g>
        );
      })}
      <text x="0" y="292" fontSize="12" fill={C.mute} fontFamily={body}>
        compressed MB of one column, 93.45 million readings, sorted by sensor and time · Decimal only if 2 decimals
        suffice
      </text>
    </svg>
  );
}

// ---- finding one lot: time and extra disk, log scales ----
const LOT = [
  { name: 'no index', ms: 622, kb: 0, extra: '—', color: C.mute },
  { name: 'skip index minmax', ms: 10, kb: 91, extra: '91 KB', color: C.amber },
  { name: 'skip index set(16)', ms: 7, kb: 308, extra: '308 KB', color: C.ok },
  { name: 'skip index bloom_filter', ms: 26.5, kb: 118, extra: '118 KB', color: C.amber },
  { name: 'projection sorted by lot', ms: 7, kb: 636000, extra: '636 MB', color: C.coral },
];
function LotChart() {
  const tx0 = 220, tW = 210, tlo = 0, thi = Math.log10(1000);
  const tx = (v: number) => tx0 + ((Math.log10(v) - tlo) / (thi - tlo)) * tW;
  const dx0 = 500, dW = 150, dlo = Math.log10(10), dhi = Math.log10(1e6);
  const dx = (v: number) => dx0 + ((Math.log10(v) - dlo) / (dhi - dlo)) * dW;
  return (
    <svg viewBox="0 0 720 280" role="img" aria-label="Every reading of one lot, median over 6 lots: no index 622 ms; minmax skip index 10 ms for 91 KB; set(16) skip index 7 ms for 308 KB; bloom filter 26.5 ms for 118 KB; a projection sorted by lot 7 ms for 636 MB, nearly three times the 223 MB table">
      <text x={tx0} y="14" fontSize="12" fill={C.mute} fontFamily={body} fontWeight="700">
        time, ms (log)
      </text>
      <text x={dx0} y="14" fontSize="12" fill={C.mute} fontFamily={body} fontWeight="700">
        extra on disk (log)
      </text>
      {LOT.map((r, i) => {
        const y = 28 + i * 40;
        return (
          <g key={r.name}>
            <text x={tx0 - 10} y={y + 15} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight={r.name.includes('set') ? 700 : 500}>
              {r.name}
            </text>
            <rect x={tx0} y={y + 2} width={tx(r.ms) - tx0} height="18" rx="2" fill={r.color} />
            <text x={tx(r.ms) + 6} y={y + 16} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.ms}
            </text>
            {r.kb > 0 ? (
              <>
                <rect x={dx0} y={y + 2} width={dx(r.kb) - dx0} height="18" rx="2" fill={r.color} />
                <text x={dx(r.kb) + 6} y={y + 16} fontSize="12" fill={C.ink} fontFamily={mono}>
                  {r.extra}
                </text>
              </>
            ) : (
              <text x={dx0} y={y + 16} fontSize="12" fill={C.mute} fontFamily={mono}>
                —
              </text>
            )}
          </g>
        );
      })}
      {[1, 10, 100, 1000].map((v) => (
        <text key={v} x={tx(v)} y="242" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
          {v.toLocaleString('en-US')}
        </text>
      ))}
      {[
        { v: 10, t: '10 KB' },
        { v: 1000, t: '1 MB' },
        { v: 1e6, t: '1 GB' },
      ].map((m) => (
        <text key={m.t} x={dx(m.v)} y="242" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
          {m.t}
        </text>
      ))}
      <text x="0" y="270" fontSize="12" fill={C.mute} fontFamily={body}>
        every reading of one lot · median over 6 lots, 5 runs each · the table itself: 223 MB · lab copy, no FINAL
      </text>
    </svg>
  );
}

// ---- Flink roll-ups vs raw readings ----
function RollupChart() {
  const rows = [
    { q: 'one sensor, minute by minute', raw: 6.4, roll: 4.8 },
    { q: 'every tool, hourly average', raw: 625, roll: 7.0 },
    { q: 'every sensor, highest minute', raw: 1045, roll: 9.1 },
  ];
  const x0 = 230, W = 400, lo = 0, hi = Math.log10(2000);
  const x = (v: number) => x0 + ((Math.log10(v) - lo) / (hi - lo)) * W;
  return (
    <svg viewBox="0 0 720 220" role="img" aria-label="3 hours of 560 sensors, read with FINAL. One sensor minute by minute: raw readings 6.4 ms, Flink roll-ups 4.8 ms. Every tool's hourly average: 625 ms against 7.0 ms, 89 times faster. Every sensor's highest minute average: 1,045 ms against 9.1 ms, 115 times faster">
      {[1, 10, 100, 1000].map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1="8" y2="170" stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(v)} y="186" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {v.toLocaleString('en-US')} ms
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = 12 + i * 54;
        return (
          <g key={r.q}>
            <text x={x0 - 10} y={y + 22} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="600">
              {r.q}
            </text>
            <rect x={x0} y={y} width={x(r.raw) - x0} height="16" rx="2" fill={C.coral} />
            <text x={x(r.raw) + 6} y={y + 12} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.raw.toLocaleString('en-US')}
            </text>
            <rect x={x0} y={y + 20} width={x(r.roll) - x0} height="16" rx="2" fill={C.ok} />
            <text x={x(r.roll) + 6} y={y + 32} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.roll}
            </text>
          </g>
        );
      })}
      <text x="0" y="210" fontSize="12" fill={C.mute} fontFamily={body}>
        <tspan fill="var(--coral)" fontWeight="700">
          raw readings (12.1 M)
        </tspan>{' '}
        ·{' '}
        <tspan fill="var(--ok)" fontWeight="700">
          Flink 1-minute roll-ups (100 k)
        </tspan>{' '}
        · 3 hours of 560 sensors · median of 5, both with FINAL, log scale
      </text>
    </svg>
  );
}

export function ClickHouseHistoryBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Real-time data</p>
      <h1>93 million readings in 213 MiB: storing a fab's sensor history in ClickHouse</h1>
      <p className="standfirst">
        One table holds every sensor reading. Two column codecs made it 3.6 times smaller; a 0.3 MB index made finding
        a lot 90 times faster in the lab (7 times on the de-duplicating store); and the roll-ups that worked in the lab would have double-counted on the real table.
        What we measured, and what we applied.
      </p>
      <PostByline />

      <p>
        In <a href="/blog/clickhouse-postgresql-timescaledb-sensor-history">the comparison with PostgreSQL and
        TimescaleDB</a>, ClickHouse kept 93.5 million readings in 213 MiB. It did not start there: the same table was
        766 MiB. This post is how it got smaller and faster — each choice measured by copying the table and changing
        one thing. All data is synthetic; all numbers are measured on one laptop.
      </p>

      <h2>01 · One table, measured one change at a time</h2>
      <p>
        The deep store's sensor table holds <strong>93.45 million readings</strong>: 30 days of synthetic history plus
        the story night, one row per sensor and half-second. It is sorted by tool, chamber, sensor and time, split into
        daily partitions, and de-duplicates replays (a ReplacingMergeTree). For each experiment we copied it, unchanged,
        into a lab table that differs in one thing — a codec, the sort key, an index — (a plain MergeTree, without
        de-duplication) and asked the questions an
        investigation asks, five times each, with ClickHouse's query caches turned off (more on why in section 06).
      </p>

      <h2>02 · Two codecs, 3.6 times smaller</h2>
      <p>
        ClickHouse compresses each column on its own, with a codec chosen per column. The default is LZ4. Per column:
      </p>
      <figure>
        <CodecChart />
        <figcaption>
          A sensor's timestamps are half a second apart: after Delta, almost every number is the same and ZSTD keeps
          nearly nothing — the biggest column (468 MB) dropped to under 1 MB. Gorilla, the usual advice for floats, made the
          values <em>bigger</em>.
        </figcaption>
      </figure>
      <ul>
        <li>
          <strong>Gorilla depends on the data.</strong> It stores the bits that differ from the previous value; our
          synthetic readings are noise rounded to two decimals, so almost every bit differs. Real sensors may do better
          — it must be measured on them.
        </li>
        <li>
          <strong>ZSTD costs read speed</strong>: decompressing all 93 million values took 778 ms instead of 405 ms
          with LZ4. The investigation's questions read little and did not slow down (one sensor over 30 days: 127 ms vs
          136 ms).
        </li>
      </ul>
      <p>
        With <code>Delta + ZSTD(1)</code> on the timestamp and <code>ZSTD(1)</code> on the value, the lab table went
        from 802 MB to 223 MB. Applied to the real store with one <code>ALTER … CODEC</code> and a 9-second rewrite:{' '}
        <strong>766 MiB → 213 MiB on disk</strong>, the same 93,450,240 readings, the store's answers unchanged.
      </p>

      <h2>03 · The sort key decides what can be skipped</h2>
      <p>
        ClickHouse reads in blocks of 8,192 rows (granules) and keeps the first key of each block in memory. A
        question that filters on the start of the sort key skips most blocks; any other question reads more. Same rows,
        two sort keys:
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>tool, chamber, sensor, time (ours)</th>
              <th>time only</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>one sensor, one hour</td>
              <td>16 k rows, 4 ms</td>
              <td>139 k rows, 5 ms</td>
            </tr>
            <tr>
              <td>
                <strong>one sensor, 30 days</strong>
              </td>
              <td>
                <strong>5.4 M rows, 136 ms</strong>
              </td>
              <td>93 M rows (all), 1,122 ms</td>
            </tr>
            <tr>
              <td>whole fab, one minute</td>
              <td>218 k rows, 6 ms</td>
              <td>8 k rows, 2 ms</td>
            </tr>
            <tr>
              <td>one tool, one day</td>
              <td>1.4 M rows, 64 ms</td>
              <td>3.1 M rows, 75 ms</td>
            </tr>
            <tr>
              <td>one lot (not in the key)</td>
              <td>93 M rows, 604 ms</td>
              <td>93 M rows, 475 ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ul>
        <li>
          <strong>Sensor first is how an investigation asks</strong>: 8.3 times faster for a sensor's history. The
          price is on fab-wide questions — 27 times more rows for one minute, still 6 ms because the daily partition
          narrows it.
        </li>
        <li>
          <strong>Partitions are not a speed knob.</strong> By day, by month or none: within about 1.3 times on these
          questions, no consistent winner. Choose them for managing data — expiring and dropping a day.
        </li>
        <li>
          <strong>A lot is in no key</strong>, so finding its readings reads all 93 million rows.
        </li>
      </ul>

      <h2>04 · Finding a lot: 0.3 MB against 636 MB</h2>
      <p>
        A <em>skip index</em> keeps a small summary per granule; a query skips the granules whose summary rules the value
        out. A <em>projection</em> keeps a second copy of the table, sorted another way. Both answer "every reading of
        this lot":
      </p>
      <figure>
        <LotChart />
        <figcaption>
          A lot runs on one chamber for a while, so in the sensor-sorted table its readings sit together: each granule
          holds only a few lot ids. <code>set(16)</code> — the exact list, up to 16 — rules out all but 2–3 of 11,417
          granules: about 90 times faster for 0.3 MB. The projection is as fast and nearly three times the size of the
          table.
        </figcaption>
      </figure>
      <p>
        Why is the projection so big? Re-sorted by lot, the timestamp column loses its regular half-second steps and
        grows from 0.9 MB to 292 MB. The order that makes the table small is the order a second copy throws away.
      </p>
      <p>
        On the real table the index helps less. Its queries use <code>FINAL</code>, which removes replayed duplicates
        at read time:
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>"Every reading of LOT1234"</th>
              <th>without the index</th>
              <th>with the index</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>without FINAL</td>
              <td>590 ms, 93.6 M rows</td>
              <td>
                <strong>7 ms, 33 k rows</strong>
              </td>
            </tr>
            <tr>
              <td>with FINAL (as the investigation asks)</td>
              <td>1,392 ms, 93.6 M rows</td>
              <td>
                <strong>196 ms, 10.6 M rows</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        The index finds 4 granules; then <code>FINAL</code> widens the read to every granule whose key range overlaps
        them, in every part — a duplicate of a row could sit anywhere in that range. 7 times faster instead of about
        80, and the more unmerged parts a partition has, the more it reads.
      </p>

      <h2>05 · Roll-ups: ClickHouse's own would double-count, so Flink computes them</h2>
      <p>
        Charts and dashboards ask for per-minute summaries. In the lab, ClickHouse's own ways — a materialized view
        into an AggregatingMergeTree, or an aggregate projection — answered them 9–16 times faster for under 10 MB.
        On the real table, neither works:
      </p>
      <ul>
        <li>
          <strong>The projection is refused</strong> on a ReplacingMergeTree by default (ClickHouse 26.8).
        </li>
        <li>
          <strong>The materialized view counts duplicates.</strong> It sees each insert as it comes: the same reading
          inserted twice was counted twice in the roll-up, while the table with <code>FINAL</code> held it once. The
          demo replays its story many times, and a source that resends after a failure does the same.
        </li>
      </ul>
      <p>
        So Flink computes them. Its 1-minute windows emit <strong>one finished row per window</strong> — average,
        lowest, highest, count — and ClickHouse stores them in a table keyed by sensor and minute that keeps the newest
        copy. A window sent again <em>replaces</em> itself instead of adding.
      </p>
      <p>
        Tested on a synthetic big fab (560 sensors, 3 hours, 12.1 million readings): after a crash run and a full replay,
        Kafka had delivered <strong>151,760 messages for 100,240 windows</strong>. ClickHouse with <code>FINAL</code>{' '}
        held exactly 100,240 windows, and every one equalled the raw readings — average, lowest, highest and count.
      </p>
      <figure>
        <RollupChart />
        <figcaption>
          The gain is for questions over many sensors or long periods: 89 and 115 times faster, and 21 times smaller
          on disk (1.35 MiB against 27.9 MiB). A question about one sensor was already fast — the sort key finds it.
        </figcaption>
      </figure>
      <p>
        The limit: the newest copy wins, not the most complete. A job started in the middle of a minute emits a partial
        window that would replace a complete one, so replays must start at or before a minute's first reading.
      </p>

      <h2>06 · The traps that made no error</h2>
      <ul>
        <li>
          <strong>93 million rows "in 1 ms".</strong> Our first timings were wrong. ClickHouse's query condition cache,
          on by default, remembers which granules failed a filter, and repeated runs skipped them. Every number here is
          measured with it off — a ClickHouse benchmark must say which caches were on.
        </li>
        <li>
          <strong>Merges filled the disk and stopped Kafka.</strong> A merge writes the new part before the old ones
          go, and ClickHouse keeps merged-away parts for 8 minutes by default. Rewriting several 0.8 GB copies at once
          filled Docker's disk to the last 78 MB; Kafka, on the same disk, stopped. It recovered once space came back.
          The lab now stops below 4 GB free; for the platform, free disk — with room for a partition being rewritten —
          is a monitoring item.
        </li>
        <li>
          <strong>Counting rows is no count of duplicates.</strong> Background merges remove some duplicates at random
          times; we counted duplicates from what Kafka delivered.
        </li>
        <li>
          <strong>A restored roll-up job wrote nothing more</strong> after a crash, in all 4 lab runs — while, in an
          earlier attempt watched by hand, it showed as running and kept checkpointing. Two manual runs did recover. The cause and the fix are a later post in this series.
        </li>
      </ul>

      <h2>07 · What we keep</h2>
      <ul>
        <li>Sort by how you investigate (sensor, then time); partition by how you expire data.</li>
        <li>Delta + ZSTD on timestamps, ZSTD on values; measure Gorilla on real data before using it.</li>
        <li>A 0.3 MB <code>set</code> skip index for lots, not a second copy of the table.</li>
        <li>
          Roll-ups computed by Flink and stored so that a recomputed window replaces itself; de-duplication stays in
          ClickHouse.
        </li>
        <li>Benchmarks with caches off, and disk headroom for merges.</li>
      </ul>
      <p>Next in this series: fire drills — breaking Flink and Kafka on purpose to see which alerts fire.</p>

      <p className="foot-note">
        Method: synthetic fab data on one laptop (Apple M4 Pro, 24 GB; Docker with 8 CPUs). ClickHouse 26.8, Flink 2.2.1,
        Kafka 4.4. Lab tables: copies of the deep store's 93.45 million readings, one change each; medians of 5 runs,
        warm OS cache, query result and condition caches off; lots: median over 6 lots. Roll-ups: a 3-hour synthetic
        fab of 560 sensors, Flink at parallelism 1. Sizes in the table lab are compressed column data in MB (10⁶ bytes); the
        store's and the roll-up lab's are on-disk MiB with index files. Versions as of 2026-11-20.
      </p>
    </>
  );
}

// The "Latest" slot figure: the store's size on disk, before and after.
export function ClickHouseHistoryFigure() {
  const x0 = 20, W = 470, max = 800;
  const x = (v: number) => x0 + (v / max) * W;
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="93.45 million readings on disk: 766 MiB with the default codecs, 213 MiB with Delta plus ZSTD on the timestamp and ZSTD on the value; one lot found in 196 ms instead of 1,392 with a 0.3 MB index, read de-duplicated">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        MEASURED
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        93.45 M readings on disk, ClickHouse
      </text>
      <rect x={x0} y="44" width={x(766) - x0} height="28" rx="2" fill="var(--coral)" opacity="0.85" />
      <text x={x0 + 8} y="63" fontSize="13" fill="var(--ground)" fontFamily="var(--f-mono)" fontWeight="700">
        766 MiB · default codecs
      </text>
      <rect x={x0} y="84" width={x(213) - x0} height="28" rx="2" fill="var(--ok)" />
      <text x={x(213) + 8} y="103" fontSize="13" fill="var(--ink)" fontFamily="var(--f-mono)" fontWeight="700">
        213 MiB · Delta + ZSTD
      </text>
      <text x={x0} y="160" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        One lot: 1,392 → 196 ms with a 0.3 MB index
      </text>
      <text x={x0} y="186" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        roll-ups by Flink: 89–115× faster fab-wide · synthetic data
      </text>
    </svg>
  );
}
