import { PostByline } from '../components/blog/post-context';
// Engineering · Real-time data · part 4. Numbers from the hands-on results of 2026-11-13 (F5, F5 v2) and 2026-11-17
// (F5 v3): one laptop, synthetic fab readings. Story checks are replays compared with an independent model; false
// alarms and warning times are offline runs on simulated minute averages.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const mono = 'var(--f-mono)';
const body = 'var(--f-body)';
const STATUS = { GO: C.ok, WATCH: C.amber, HOLD: C.coral } as const;

// ---- the story's lots on ETCH-05/B: minutes to the alarm at the trend, log scale ----
const LOTS = [
  { t: '01:40', lot: 'LOT2501', due: 372, status: 'GO' as const },
  { t: '01:50', lot: 'LOT2502', due: 148, status: 'GO' as const },
  { t: '02:00', lot: 'LOT2503', due: 93, status: 'WATCH' as const },
  { t: '02:10', lot: 'LOT2504', due: 25, status: 'HOLD' as const },
  { t: '02:20', lot: 'LOT2505', due: 5, status: 'HOLD' as const },
];
function LotChart() {
  const x0 = 150, W = 400, lo = 0, hi = Math.log10(1000);
  const x = (v: number) => x0 + ((Math.log10(v) - lo) / (hi - lo)) * W;
  return (
    <svg viewBox="0 0 720 290" role="img" aria-label="The lots of ETCH-05/B and the minutes left to the pump's alarm level at the trend: 01:40 LOT2501 372 minutes, GO; 01:50 LOT2502 148, GO; 02:00 LOT2503 93, WATCH; 02:10 LOT2504 25, HOLD; 02:20 LOT2505 5, HOLD. HOLD below 40 minutes, WATCH below 120. A plain limit check says GO to all five">
      {[
        { v: 40, t: 'HOLD < 40 min' },
        { v: 120, t: 'WATCH < 2 h' },
      ].map((m) => (
        <g key={m.v}>
          <line x1={x(m.v)} x2={x(m.v)} y1="22" y2="232" stroke={m.v === 40 ? C.coral : C.amber} strokeDasharray="4 3" />
          <text x={m.v === 40 ? x(m.v) - 6 : x(m.v) + 6} y="14" textAnchor={m.v === 40 ? 'end' : 'start'} fontSize="12" fill={m.v === 40 ? C.coral : C.amber} fontFamily={body} fontWeight="700">
            {m.t}
          </text>
        </g>
      ))}
      {LOTS.map((r, i) => {
        const y = 30 + i * 40;
        return (
          <g key={r.lot}>
            <text x={x0 - 10} y={y + 16} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={mono} fontWeight="600">
              {r.t} {r.lot}
            </text>
            <rect x={x0} y={y + 2} width={x(r.due) - x0} height="20" rx="2" fill={STATUS[r.status]} opacity="0.85" />
            <text x={x(r.due) + 6} y={y + 17} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.due} min
            </text>
            <text x="600" y={y + 17} fontSize="13" fill={STATUS[r.status]} fontFamily={body} fontWeight="700">
              {r.status}
            </text>
            <text x="660" y={y + 17} fontSize="12" fill={C.mute} fontFamily={body}>
              limit: GO
            </text>
          </g>
        );
      })}
      {[1, 10, 100, 1000].map((v) => (
        <text key={v} x={x(v)} y="250" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
          {v.toLocaleString('en-US')}
        </text>
      ))}
      <text x="0" y="278" fontSize="12" fill={C.mute} fontFamily={body}>
        minutes left to the pump's alarm level at the trend, log scale · the check at each track-in · right: a plain
        limit check
      </text>
    </svg>
  );
}

// ---- the join: checks that came, and their delay (live, 01:54–02:21 of the story) ----
function JoinChart() {
  const rows = [
    { label: 'interval join', checks: 30, delay: 5.3, delayText: '5.2–5.4 s', color: C.ok },
    { label: 'temporal join', checks: 20, delay: 600, delayText: '~600 s', color: C.coral },
  ];
  const cx0 = 150, cW = 220;
  const cx = (v: number) => cx0 + (v / 30) * cW;
  const dx0 = 430, dW = 230, lo = 0, hi = Math.log10(1000);
  const dx = (s: number) => dx0 + ((Math.log10(s) - lo) / (hi - lo)) * dW;
  return (
    <svg viewBox="0 0 720 200" role="img" aria-label="Live, both joins reading the same streams: the interval join gave 30 of 30 checks, equal to the model, 5.2–5.4 s after the track-in; the temporal join gave 20 of 30, each about 600 s late, and the 02:20 checks, LOT2505's HOLD among them, never came">
      <text x={cx0} y="16" fontSize="12" fill={C.mute} fontFamily={body} fontWeight="700">
        checks that came, of 30
      </text>
      <text x={dx0} y="16" fontSize="12" fill={C.mute} fontFamily={body} fontWeight="700">
        seconds from track-in in Kafka to check, log scale
      </text>
      {rows.map((r, i) => {
        const y = 34 + i * 56;
        return (
          <g key={r.label}>
            <text x={cx0 - 10} y={y + 19} textAnchor="end" fontSize="14" fill={C.ink} fontFamily={body} fontWeight="700">
              {r.label}
            </text>
            <rect x={cx0} y={y} width={cW} height="28" fill={C.rule} opacity="0.5" />
            <rect x={cx0} y={y} width={cx(r.checks) - cx0} height="28" fill={r.color} />
            <text x={cx0 + 8} y={y + 19} fontSize="13" fill="var(--ground)" fontFamily={mono} fontWeight="700">
              {r.checks}
            </text>
            <rect x={dx0} y={y + 6} width={dx(r.delay) - dx0} height="16" rx="2" fill={r.color} />
            <text x={dx(r.delay) + 6} y={y + 19} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.delayText}
            </text>
          </g>
        );
      })}
      {[1, 10, 100, 1000].map((s) => (
        <text key={s} x={dx(s)} y="160" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
          {s.toLocaleString('en-US')}
        </text>
      ))}
      <text x="0" y="188" fontSize="12" fill={C.mute} fontFamily={body}>
        live, one run, both jobs on the same streams · the temporal join's missing 10: the 02:20 track-ins, LOT2505's
        HOLD among them
      </text>
    </svg>
  );
}

// ---- false alarms per chamber-day, by noise and trend, log scale ----
const NOISE = [
  { label: 'white noise', sub: 'as in the story', v: [0, 0, 0] },
  { label: 'spikes', sub: '0.2 % of readings, 20× noise', v: [2.9, 0, 0] },
  { label: 'slow wander', sub: '1× noise, 30 min', v: [86.6, 16.4, 0.016] },
  { label: 'wander + spikes', sub: '2× noise, 60 min', v: [162.5, 49.8, 0.063] },
];
const TRENDS = [
  { name: 'v1: 5-minute change', color: C.coral },
  { name: 'regression + t test', color: C.amber },
  { name: 'v2: + normal band', color: C.ok },
];
function FalseAlarmChart() {
  const x0 = 190, W = 440, lo = Math.log10(0.01), hi = Math.log10(1000);
  const x = (v: number) => x0 + ((Math.log10(v) - lo) / (hi - lo)) * W;
  return (
    <svg viewBox="0 0 720 340" role="img" aria-label="False alarms (WATCH or HOLD episodes) per chamber-day with nothing wrong. White noise: 0, 0, 0. Spikes: v1 2.9, regression with t test 0, v2 0. Slow wander: 86.6, 16.4, 0.016. Strong wander with spikes: 162.5, 49.8, 0.063">
      {[0.01, 0.1, 1, 10, 100, 1000].map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1="10" y2="285" stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(v)} y="302" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {v < 1 ? v : v.toLocaleString('en-US')}
          </text>
        </g>
      ))}
      {NOISE.map((n, i) => {
        const y = 14 + i * 68;
        return (
          <g key={n.label}>
            <text x={x0 - 12} y={y + 18} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
              {n.label}
            </text>
            <text x={x0 - 12} y={y + 34} textAnchor="end" fontSize="11" fill={C.mute} fontFamily={body}>
              {n.sub}
            </text>
            {n.v.map((v, j) => {
              const yy = y + j * 18;
              return v > 0 ? (
                <g key={j}>
                  <rect x={x0} y={yy} width={x(v) - x0} height="14" rx="2" fill={TRENDS[j].color} />
                  <text x={x(v) + 6} y={yy + 11} fontSize="12" fill={C.ink} fontFamily={mono}>
                    {v}
                  </text>
                </g>
              ) : (
                <text key={j} x={x0 + 4} y={yy + 11} fontSize="12" fill={TRENDS[j].color} fontFamily={mono} fontWeight="700">
                  0
                </text>
              );
            })}
          </g>
        );
      })}
      <text x="0" y="328" fontSize="12" fill={C.mute} fontFamily={body}>
        {TRENDS.map((t, i) => (
          <tspan key={t.name} fill={t.color} fontWeight="700">
            {i > 0 ? ' · ' : ''}
            {t.name}
          </tspan>
        ))}
        <tspan> · episodes per chamber-day, log scale · simulated, 9 chambers × 7 days each</tspan>
      </text>
    </svg>
  );
}

// ---- after a pump swap: alarm-minutes in the day after, over 5 swaps ----
function SwapChart() {
  const rows = [
    { label: '+0.4 mm/s', v2: 5, v3: 3 },
    { label: '+0.8 mm/s', v2: 54, v3: 1 },
    { label: '+1.6 mm/s', v2: 115, v3: 5 },
  ];
  const x0 = 130, W = 480, max = 120;
  const x = (v: number) => x0 + (v / max) * W;
  return (
    <svg viewBox="0 0 720 230" role="img" aria-label="WATCH or HOLD minutes in the healthy day after a pump swap, over 5 swaps per size. Level raised by 0.4 mm/s: v2 5, v3 3. By 0.8: v2 54, v3 1. By 1.6: v2 115, v3 5">
      {[0, 40, 80, 120].map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1="10" y2="170" stroke={C.rule} strokeDasharray="2 4" />
          <text x={x(v)} y="186" textAnchor="middle" fontSize="12" fill={C.mute} fontFamily={mono}>
            {v}
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = 16 + i * 52;
        return (
          <g key={r.label}>
            <text x={x0 - 10} y={y + 22} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={mono} fontWeight="600">
              {r.label}
            </text>
            <rect x={x0} y={y} width={x(r.v2) - x0} height="16" rx="2" fill={C.coral} />
            <text x={x(r.v2) + 6} y={y + 12} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.v2}
            </text>
            <rect x={x0} y={y + 20} width={Math.max(x(r.v3) - x0, 2)} height="16" rx="2" fill={C.ok} />
            <text x={x(r.v3) + 6} y={y + 32} fontSize="12" fill={C.ink} fontFamily={mono}>
              {r.v3}
            </text>
          </g>
        );
      })}
      <text x="0" y="216" fontSize="12" fill={C.mute} fontFamily={body}>
        level after the swap · alarm-minutes in the day after, 5 swaps ·{' '}
        <tspan fill="var(--coral)" fontWeight="700">
          v2, old band
        </tspan>{' '}
        ·{' '}
        <tspan fill="var(--ok)" fontWeight="700">
          v3: jump test, band re-centred
        </tspan>{' '}
        · simulated
      </text>
    </svg>
  );
}

export function EquipmentCheckBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Real-time data</p>
      <h1>Holding a lot before the pump fails: three versions of an equipment check</h1>
      <p className="standfirst">
        Before a lot goes into a chamber, is the chamber's own hardware healthy enough? Our Flink check made the right
        call on every lot of the story once its join was right — and would have raised 87 false alarms a day per chamber on simulated sensors that wander. What it took
        to make it trustworthy, measured.
      </p>
      <PostByline />

      <p>
        In the <a href="/blog/one-night-at-the-fab">night at the fab</a>, a wearing dry pump on ETCH-05/B was caught by
        a check that held the next lot 13 minutes before the pump reached its alarm level. This post opens that check:
        what it computes, the join that silently withheld its most important answer, and the two versions after the
        first — one for sensors that drift and spike, one for the day a part is replaced. All data is synthetic and
        every number is measured on one laptop; false alarms and warning times are offline runs on simulated sensors.
      </p>

      <h2>01 · The question at track-in</h2>
      <p>
        Every chamber sends its health once a second: the dry pump's vibration (mm/s) and current (A), and the chiller
        temperature. Every minute, a Flink SQL job computes per chamber and sensor the average, the trend, and the{' '}
        <strong>minutes left to the alarm level</strong> at that trend. HOLD if the alarm is reached or due within 40
        minutes (a lot's 10 minutes plus a margin); WATCH if above the warning level or due within 2 hours; else GO. The
        limits and horizons are rows in PostgreSQL, like the alert rules. Every MES track-in is joined to its chamber's
        health of the minute just before, and the decision goes to Kafka, exactly-once.
      </p>
      <figure>
        <LotChart />
        <figcaption>
          The trend sees it coming; a limit does not. A limit check lets all five lots start, including LOT2505, which
          is in the chamber when the pump reaches its alarm (02:22:54). Every other chamber: GO at every track-in.
        </figcaption>
      </figure>
      <p>
        The same check also exists as a short plain-Python model, about 200 lines. Every replay compares each of Flink's decisions
        with that model — and that comparison found most of what follows.
      </p>

      <h2>02 · The textbook join withheld the most important check</h2>
      <p>
        "The chamber's health as of the track-in" is, by the book, an <em>event-time temporal join</em>. It emits a
        check only once the event-time clocks of both inputs have passed the track-in. But MES is sparse — in the
        story, a burst of track-ins every 10 minutes — so its clock moves only when the next burst comes.
      </p>
      <figure>
        <JoinChart />
        <figcaption>
          Each temporal check waited for the next MES burst. After the last burst nothing moved MES's clock, so the
          02:20 checks never came — no error, just no output. Replays agreed: 50 of 60 checks, three times per order
          the streams were sent in; the interval join gave 60 of 60.
        </figcaption>
      </figure>
      <ul>
        <li>
          <strong>An idle timeout is not the fix.</strong> Declaring MES idle after 5 s brought all 60 checks in the
          measured runs — but in an earlier test it brought <em>none</em>: MES was idle, the clock moved on with the
          equipment readings, and the track-ins then arrived "late" and were dropped. The same trap as the alert job's.
        </li>
        <li>
          <strong>The interval join emits as soon as both rows are there</strong>: the health minute that ended within
          the 60 s before the track-in. A check comes when that minute is computed, whatever MES's clock does — 5.2–5.4
          s, which is the 5 s the minute waits for late readings. A track-in with no health minute just before gets
          NO_DATA; an older health is not used.
        </li>
      </ul>

      <h2>03 · A trend that real sensors would not fool</h2>
      <p>
        Version 1's trend was the change over the last 5 minutes. On the story's clean noise it raised no false alarm in
        7 days of 9 healthy chambers — 90,720 chamber-minutes — but its closest call was 2.4 minutes from a false WATCH.
        Real sensors also drift and spike. Version 2 asks two questions before it trusts a rise:
      </p>
      <ul>
        <li>
          <strong>Is it more than noise?</strong> The least-squares slope over the last 10 minute averages counts only
          if it is at least 3 standard errors above zero — a t test, written in Flink SQL as a fixed weighted sum of the
          10 lagged values.
        </li>
        <li>
          <strong>Is the level unusual for this chamber?</strong> Only above the mean + 4 sd of the chamber's own
          minute averages. ClickHouse computes those bands from 7 days of history (18.1 million readings in about 2 s)
          and stores them in PostgreSQL, where the Flink job looks them up next to the limits.
        </li>
      </ul>
      <figure>
        <FalseAlarmChart />
        <figcaption>
          The t test removes noise and spikes, but not wander: a sensor that drifts and comes back really does rise
          steadily for ten minutes. Only "is this level unusual here?" tells it apart from wear — 86.6 false alarms per
          chamber-day become 0.016, about one in 60.
        </figcaption>
      </figure>
      <p>
        Two honest limits. The band works only if the history holds the wander: each chamber's band was learned from 7
        days with the same noise as the test, and a chamber quieter in its history than today would get a band too
        narrow. And v2's 0.016 and 0.063 are 1 and 4 episodes, with t ≥ 3 and 4 sd chosen on these same profiles — no
        held-out test yet.
      </p>

      <h2>04 · What it costs: warning time</h2>
      <p>
        A stricter trend holds later. On a wearing pump in 8 shapes, 5 runs each on slow-wander noise, minutes from the first HOLD to the
        alarm (median):
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Wear</th>
              <th>Alarm after onset</th>
              <th>v1</th>
              <th>v2</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>exponential, fast (τ 7 min)</td>
              <td>21 min</td>
              <td>9</td>
              <td>9</td>
            </tr>
            <tr>
              <td>exponential (τ 14, like the story)</td>
              <td>42 min</td>
              <td>15</td>
              <td>15</td>
            </tr>
            <tr>
              <td>exponential (τ 28)</td>
              <td>84 min</td>
              <td>27</td>
              <td>19</td>
            </tr>
            <tr>
              <td>exponential, slow (τ 56)</td>
              <td>168 min</td>
              <td>40</td>
              <td>32</td>
            </tr>
            <tr>
              <td>linear</td>
              <td>60 / 120 / 180 / 240 min</td>
              <td>46 / 62 / 86 / 87</td>
              <td>44 / 49 / 63 / 61</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ul>
        <li>
          <strong>v2 holds later on slow wear</strong>, by up to 26 minutes — but no run of either version was late,
          and v2 still held at least 7 minutes before the alarm in every run (the closest: the fastest failure).
        </li>
        <li>
          <strong>v1's early warnings were noise.</strong> Its first WATCH came <em>before the wear began</em> in 40 of
          40 runs (the regression without the band: 17; v2: none). A warning that always fires is not warning time.
        </li>
      </ul>
      <p>
        In Flink, v2 decided all 60 checks of each story replay exactly as the model did, and every lot as v1 had —
        WATCH at 02:00, HOLD at 02:10 and 02:20.
      </p>

      <h2>05 · Maintenance is not wear</h2>
      <p>
        When the worn pump is replaced, both questions go wrong. For ten minutes the trend's window holds the old level
        and the new one, and a straight line through a jump has a clear slope. And the band was learned from the old
        pump: a new one that runs a little higher sits above it for days, so every chance rise counts. MES now sends a{' '}
        <code>maintenance</code> event. Version 3 uses it where it can wait for it, and not where it cannot:
      </p>
      <ul>
        <li>
          <strong>Flink does not wait for MES</strong> — a sparse MES clock is what stalled the temporal join. It tells
          a swap from wear in the readings: <em>a swap is a jump, wear is a ramp</em>. A trend counts only if a line
          fits the 10 minutes at least as well as the best single jump, split anywhere: 9 more fixed sums over the same
          lagged values, no new state, no new join.
        </li>
        <li>
          <strong>ClickHouse uses the MES event</strong>, because the band is a batch job. After a swap, the band's
          mean comes from the minutes after it and its spread from the minutes before — a new part moves the level, not
          the sensor's noise. "Before" leaves out the 6 hours just before the swap, which hold the failure. In the first
          hour, the old band stays; with less than a day of history before the swap, no band rather than a wrong one.
        </li>
      </ul>
      <figure>
        <SwapChart />
        <figcaption>
          The jump test removes the false alarms of the swap itself; the re-centred band removes the ones in the days
          after. Keeping the old band in the first hour matters: with no band at all, the jump test alone let 19
          minutes through at +0.8 mm/s.
        </figcaption>
      </figure>
      <p>
        Does it still catch the new pump wearing out three days later? Yes, never late, and the first HOLD comes at the
        same minute with either band; the re-centred band gives the first WATCH 15–16 minutes sooner (median). On
        the 40 wear runs without maintenance, v3 holds at exactly v2's minute in all 40; its first WATCH is later in 5
        of them, by 1–10 minutes, when a noisy start fits a jump as well as a line.
      </p>

      <h2>06 · The traps that made no error</h2>
      <ul>
        <li>
          <strong>The join</strong> above: the textbook choice withheld the HOLD that mattered most.
        </li>
        <li>
          <strong>A band 9 hours late.</strong> ClickHouse read the band's time parameters in the server's time zone
          (UTC), so the "normal" history missed 8 hours and contained the story night's wear — its standard deviation
          far too wide. It showed as 9,600 minutes per series instead of 10,080. The parameters now carry the
          fab's time zone.
        </li>
        <li>
          <strong>Precision.</strong> A slope from sums of x and x² over absolute timestamps loses precision in a
          DOUBLE. Over the 10 lagged minutes, the weights are fixed — the same arithmetic as the Python model.
        </li>
        <li>
          <strong>Two clocks in one measurement.</strong> Our first live run sent MES 6 minutes early: each sender paced
          itself from its own first event. Redone with one clock.
        </li>
      </ul>

      <h2>07 · What we keep, and what is not tested</h2>
      <ul>
        <li>A trend that must be more than noise, above the chamber's own normal band: 86.6 → 0.016 false alarms per chamber-day on wander.</li>
        <li>An interval join for sparse events: every check, in about 5 seconds, whatever MES's clock does.</li>
        <li>The live decision never waits for MES; the history (ClickHouse) uses it.</li>
        <li>An independent model of the check, compared on every replay.</li>
      </ul>
      <p>
        Not tested yet: a swap that <em>lowers</em> the level (the story's own case — the old band stays too high for a
        while); wear starting within 10 minutes of a swap (up to 9 minutes late, by reasoning); a failure that is itself
        a jump, left to the warning and alarm levels; re-running the band on the MES event (by hand here). All noise is
        simulated: the false alarms come from 4 profiles, one seed each; warning times and swaps from one profile, 5 runs
        per case.
      </p>
      <p>Next in this series: 93 million readings in 213 MiB — how ClickHouse stores the sensor history.</p>

      <p className="foot-note">
        Method: synthetic fab data on one laptop (Apple M4 Pro, 24 GB; Docker with 8 CPUs). Flink 2.2.1 (SQL job),
        Kafka 4.4, PostgreSQL 18 for limits and bands, ClickHouse 26.8 for history and bands. Story checks: replays and
        one live run, every check compared with a plain-Python model. False alarms: 9 healthy chambers × 7 days per noise
        profile; warning time: 8 wear shapes × 5 seeds; swaps: 5 per size, a healthy day after, slow-wander noise — all
        simulated minute averages. Versions as of 2026-11-20.
      </p>
    </>
  );
}

// The "Latest" slot figure: false alarms on a wandering sensor.
export function EquipmentCheckFigure() {
  const rows = [
    { name: 'v1: 5-minute change', v: 86.6, color: 'var(--coral)' },
    { name: '+ t test', v: 16.4, color: '#C98A16' },
    { name: 'v2: + normal band', v: 0.016, color: 'var(--ok)' },
  ];
  const x0 = 150, W = 300, lo = Math.log10(0.01), hi = Math.log10(100);
  const x = (v: number) => x0 + ((Math.log10(v) - lo) / (hi - lo)) * W;
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="False alarms per chamber-day on a slowly wandering sensor: 86.6 with a 5-minute change, 16.4 with a t test, 0.016 with the chamber's normal band">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        MEASURED
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        false alarms per chamber-day, simulated wandering sensor
      </text>
      {rows.map((r, i) => {
        const y = 44 + i * 36;
        return (
          <g key={r.name}>
            <text x={x0 - 10} y={y + 15} textAnchor="end" fontSize="13" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
              {r.name}
            </text>
            <rect x={x0} y={y} width={x(r.v) - x0} height="20" rx="2" fill={r.color} />
            <text x={x(r.v) + 6} y={y + 15} fontSize="13" fill="var(--ink)" fontFamily="var(--f-mono)" fontWeight="700">
              {r.v}
            </text>
          </g>
        );
      })}
      <text x="0" y="172" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        Every lot of the story decided as before
      </text>
      <text x="0" y="196" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        held 13 min before the pump's alarm · log scale · offline, simulated noise
      </text>
    </svg>
  );
}
