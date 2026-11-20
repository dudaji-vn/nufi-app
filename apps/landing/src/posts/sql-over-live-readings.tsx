import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 4. DBSP (PVLDB 16(7), 2023) read; Feldera 0.384.0 (Docker) vs DuckDB 2.0
// (in process) on the story's FDC readings, on an M4 Pro laptop (24 GB). One run per configuration.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const mono = 'var(--f-mono)';

const RUNS = [
  { label: '0–6 h', feldera: 16.7, recompute: 8.9 },
  { label: '24 h', feldera: 18.4, recompute: 21.9 },
  { label: '72 h', feldera: 18.6, recompute: 55.6 },
];

// ---- D ∘ Q ∘ I ----
function DeltaDiagram() {
  const boxes = [
    { x: 150, t: 'I', s: 'add up the changes' },
    { x: 310, t: 'Q', s: 'the query' },
    { x: 470, t: 'D', s: 'difference to last step' },
  ];
  return (
    <svg viewBox="0 0 720 200" role="img" aria-label="DBSP's definition: the incremental version of a query Q is D after Q after I. I adds up the changes into the whole table, Q runs on it, D takes the difference from the previous step. DBSP then rewrites this operator by operator so that filters, projections and grouped sums run on the changes alone, and a join runs on the change against the stored other side">
      <text x="0" y="66" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
        changes in
      </text>
      <text x="0" y="84" fontSize="11" fill={C.mute} fontFamily={body}>
        +1 insert, −1 delete
      </text>
      {boxes.map((b, i) => (
        <g key={b.t}>
          <rect x={b.x} y="44" width="110" height="54" rx="8" fill="none" stroke={i === 1 ? C.amber : C.ok} strokeWidth="2" />
          <text x={b.x + 55} y="72" textAnchor="middle" fontSize="20" fill={C.ink} fontFamily={mono} fontWeight="700">
            {b.t}
          </text>
          <text x={b.x + 55} y="90" textAnchor="middle" fontSize="10.5" fill={C.mute} fontFamily={body}>
            {b.s}
          </text>
          <text x={b.x - 20} y="76" textAnchor="middle" fontSize="18" fill={C.ok}>
            →
          </text>
        </g>
      ))}
      <text x="600" y="76" textAnchor="middle" fontSize="18" fill={C.ok}>
        →
      </text>
      <text x="620" y="66" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
        changes out
      </text>
      <text x="0" y="140" fontSize="13" fill={C.ink} fontFamily={body}>
        Q<tspan baselineShift="super" fontSize="10">Δ</tspan> = D ∘ Q ∘ I, then rewritten operator by operator:
      </text>
      <text x="0" y="162" fontSize="12" fill={C.ok} fontFamily={body}>
        filter, projection, GROUP BY with SUM / COUNT: run on the change only
      </text>
      <text x="0" y="182" fontSize="12" fill={C.amber} fontFamily={body}>
        join: the change against the stored other side · MIN / MAX: must remember values in case one is deleted
      </text>
    </svg>
  );
}

// ---- step time vs history ----
function GrowthChart() {
  const x0 = 90, h = 200, top = 20, maxV = 60;
  const y = (v: number) => top + h - (v / maxV) * h;
  return (
    <svg viewBox="0 0 720 290" role="img" aria-label="Time per one-minute step, median. With 0 to 6 hours of history: Feldera 16.7 ms, DuckDB recompute 8.9 ms. With 24 hours: Feldera 18.4, recompute 21.9. With 72 hours: Feldera 18.6, recompute 55.6">
      {[0, 20, 40, 60].map((v) => (
        <g key={v}>
          <line x1={x0} x2="700" y1={y(v)} y2={y(v)} stroke={C.rule} />
          <text x={x0 - 10} y={y(v) + 4} textAnchor="end" fontSize="11" fill={C.mute} fontFamily={mono}>
            {v} ms
          </text>
        </g>
      ))}
      {RUNS.map((r, i) => {
        const cx = x0 + 60 + i * 200;
        return (
          <g key={r.label}>
            <rect x={cx} y={y(r.feldera)} width="56" height={y(0) - y(r.feldera)} fill={C.ok} />
            <rect x={cx + 64} y={y(r.recompute)} width="56" height={y(0) - y(r.recompute)} fill={C.amber} />
            <text x={cx + 28} y={y(r.feldera) - 6} textAnchor="middle" fontSize="12" fill={C.ink} fontFamily={mono} fontWeight="700">
              {r.feldera}
            </text>
            <text x={cx + 92} y={y(r.recompute) - 6} textAnchor="middle" fontSize="12" fill={C.ink} fontFamily={mono} fontWeight="700">
              {r.recompute}
            </text>
            <text x={cx + 60} y={y(0) + 20} textAnchor="middle" fontSize="13" fill={C.ink} fontFamily={body}>
              {r.label} of history
            </text>
          </g>
        );
      })}
      <rect x={x0} y="262" width="12" height="12" fill={C.ok} />
      <text x={x0 + 18} y="272" fontSize="12" fill={C.ink} fontFamily={body}>
        Feldera: the minute in, until every view has it (HTTP included)
      </text>
      <rect x={x0 + 390} y="262" width="12" height="12" fill={C.amber} />
      <text x={x0 + 408} y="272" fontSize="12" fill={C.ink} fontFamily={body}>
        DuckDB: rerun everything
      </text>
    </svg>
  );
}

export function SqlOverLiveReadingsBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>One SQL program, batch and live: what incremental view maintenance costs and what it changes</h1>
      <p className="standfirst">
        We wrote three views once and ran them two ways over the same sensor stream: rerun from scratch after every
        minute, and maintained incrementally by Feldera, which is built on DBSP. Both gave the same rows. Rerunning got
        slower as history grew, from 9 to 56 ms; the incremental step stayed at 17–19 ms. And a live answer is a running answer: in 10-second steps the alert appeared 50
        seconds before its minute was over, then was revised five times as the minute filled in.
      </p>
      <PostByline />

      <p>
        So far this series has been about asking for data in your own words. The other half of the idea is that the
        answer should stay current. A node in our design is a query. When new readings arrive, the node's table should
        follow, without anyone rewriting the query as a streaming job. This post tests the theory that promises exactly
        that.
      </p>

      <h2>01 · DBSP in one equation</h2>
      <p>
        <strong>DBSP</strong> (Budiu, Chajed, McSherry, Ryzhyk, Tannen; VLDB 2023, a best research paper
        award) treats a database as a stream of changes. A change is a table whose rows carry weights: +1 for an
        insert, −1 for a delete. The paper calls it a Z-set. It builds on two: lifting a function over a stream, and a
        delay by one step (plus two more for nested streams, used for recursion). From those it defines
        differentiate (D: this step minus the last) and integrate (I: the running sum). The
        incremental version of any query Q is then defined as
      </p>
      <figure>
        <DeltaDiagram />
        <figcaption>
          D ∘ Q ∘ I is correct but useless on its own: it reruns Q on everything. The work is in the rules that push the
          Δ inside, one operator at a time.
        </figcaption>
      </figure>
      <p>
        The paper's chain rule lets each sub-query be made incremental on its own, "a simple, syntax-directed,
        deterministic recipe". For a linear operator the incremental version is the operator itself. Filter, projection
        and grouping are linear, and so are SUM and COUNT, so they cost work in proportion to the change. A join is
        bilinear. Its incremental version joins the change against the stored other side: O(|DB| × |ΔDB|), better than
        recomputing by a factor of |DB| / |ΔDB| but not proportional to the change. MIN and MAX are neither. To handle a
        delete they must remember the values, which costs memory. The paper reports no benchmark numbers; it points to
        its code repository.
      </p>
      <p>
        <strong>Feldera</strong> is the company and open-source engine (MIT, apart from an enterprise part) built on
        DBSP. It compiles SQL tables and views into a DBSP circuit in Rust. We ran version 0.384.0 in Docker.
      </p>

      <h2>02 · The test</h2>
      <p>
        One program, three views, over the fab readings used in earlier posts: 18 sensors, two readings a second, with
        the scripted incident where ETCH-07/C's RF power drifts over its 1450 limit at 02:09.
      </p>
      <ul>
        <li>
          <code>fdc_1min</code>: the per-minute average of every sensor, a GROUP BY with SUM and COUNT. It is linear.
        </li>
        <li>
          <code>r001</code>: the alert rule as a <em>crossing</em>. A minute's average is above 1450 while the minute
          before was not, written as a self-join of <code>fdc_1min</code>. It is a join.
        </li>
        <li>
          <code>lot_summary</code>: readings and the highest RF power per lot and chamber. MAX is not linear.
        </li>
      </ul>
      <p>
        The readings were fed one simulated minute at a time (2,160 readings). After each minute:
      </p>
      <ul>
        <li>
          <strong>recompute:</strong> DuckDB, in process, appended the minute and ran all three views over everything
          so far (only the views are timed);
        </li>
        <li>
          <strong>incremental:</strong> Feldera received the minute over HTTP. The step was timed until Feldera's
          completion token reported that every view had absorbed it.
        </li>
      </ul>
      <p>
        The same SQL ran on both. The one difference is the function that rounds a timestamp down to the minute:
        <code>TIMESTAMP_TRUNC(ts, MINUTE)</code> in Feldera, <code>date_trunc('minute', ts)</code> in DuckDB. At the
        end, every Feldera view was compared row by row with DuckDB's batch answer over the whole input.
      </p>

      <h2>03 · Same rows, and a cost that barely grows</h2>
      <p>
        <strong>Same answer, every run.</strong> All three views matched the batch result row for row, from 129,600
        readings up to 9.4 million. The alert view held one row per night of the story, 02:09 on ETCH-07/C: one in
        the 6-hour run, three in the 72-hour run.
      </p>
      <figure>
        <GrowthChart />
        <figcaption>
          Median time per one-minute step. For the first pair the timed steps are hours 0–6 themselves (360 steps).
          For the others, 24 or 72 hours were loaded first, then 30 steps were timed. One run each.
        </figcaption>
      </figure>
      <p>
        Rerunning everything grew by about 0.7 ms for each hour of history, from a straight-line fit over all the
        timed steps. The incremental step barely grew. By that fit the two cross at roughly 15–18 hours of history;
        we did not measure between 6 and 24 hours. Below that, rerunning was the cheaper of the two.
        That is not a flaw in the theory. DuckDB is a fast columnar engine working in our own process, and its time
        covers only the three views, not appending the minute. Feldera's time includes sending 2,160 rows as JSON
        over HTTP and polling until they are processed. Feldera's memory at the end
        of the one-minute runs was 1.14, 0.95 and 0.92 GiB (one reading each): it did not grow with the history. The{' '}
        <code>LATENESS</code> annotation on the timestamp is meant to let it drop state that no new row can change;
        we did not run without it, so we cannot say how much of that it did.
      </p>
      <p>
        The point is the shape, not the crossing. A dashboard over a day of readings, recomputed every minute, pays
        for the whole day every minute; over a month it pays for the month. The incremental engine pays for the
        minute.
      </p>

      <h2>04 · A live answer is a running answer</h2>
      <p>
        Then we fed the incident hour in 10-second steps, so each minute arrived in six pieces.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>View</th>
              <th>Inserts sent</th>
              <th>Deletes sent</th>
              <th>Rows at the end</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>fdc_1min</td>
              <td>6,480</td>
              <td>5,400</td>
              <td>1,080</td>
            </tr>
            <tr>
              <td>r001</td>
              <td>6</td>
              <td>5</td>
              <td>1</td>
            </tr>
            <tr>
              <td>lot_summary</td>
              <td>3,600</td>
              <td>3,540</td>
              <td>60</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        An incremental view is always the query's answer over the rows so far. Halfway through a minute, that is the
        average of half a minute. Every per-minute row was sent once and then revised five times, as each new piece
        changed its average: 1,080 rows, 5,400 revisions. Feldera sends a revision as a delete of the old row and an
        insert of the new one.
      </p>
      <p>
        The alert view did the same. We only counted Feldera's changes, so we replayed the same 10-second steps in
        DuckDB and compared the alert view after each step. That gave the same 6 inserts and 5 deletes, all on the
        one real alert:
      </p>
      <ul>
        <li>
          the alert for ETCH-07/C, minute 02:09, appeared at <strong>02:09:09.5</strong>, after the first 10 seconds
          of the minute. Its partial average was 1452.12, already over the limit. That was 50 seconds before the
          minute was over;
        </li>
        <li>
          then the row was revised five times as the rest of the minute came in: 1452.36, 1452.78, 1452.98, 1452.55,
          and finally 1452.89, the batch answer.
        </li>
      </ul>
      <p>
        So the running answer was early, and here it was right. It did not have to be. A partial average can cross a
        limit and fall back, and then the alert appears and is withdrawn. That did not happen in this data, but
        anything that reads the change stream must be ready for it.
      </p>
      <p>
        RisingWave's <code>EMIT ON WINDOW CLOSE</code>, and Flink's window aggregations, take the other side. They
        publish each minute once, when the watermark says it is complete. The cost is waiting for the rest of the
        minute and the watermark's delay, and then the engine's own time. In our hands-on runs on the same story,
        Flink took 0.18–0.36 s after the watermark passed, and RisingWave 0.75–10.75 s depending on its barrier
        interval. That was one run per interval, replayed at 30× speed. Feldera offers final-only output as an
        experimental option, which we did not test.
      </p>

      <h2>05 · What this means for a node</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>What we found</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Can one SQL program serve batch and live?</td>
              <td>Yes. The same views gave the same rows from a batch engine and from an incremental one.</td>
            </tr>
            <tr>
              <td>When is incremental worth it?</td>
              <td>When the history is large compared with each change. On a small table, rerunning was faster.</td>
            </tr>
            <tr>
              <td>What does the node need to say?</td>
              <td>
                Whether its answer is <em>running</em> (early, revised as data arrives, could be withdrawn) or{' '}
                <em>final</em> (waits for the window to close). A chart can show running; an alert that pages
                someone should read final.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        The previous posts asked which parts of a question need a language model. This one asked what it takes to
        keep the answer current. Next: semantic operators on a stream, where the two meet. That means a model's
        judgement inside a query that never ends.
      </p>

      <p className="foot-note">
        Sources: M. Budiu, T. Chajed, F. McSherry, L. Ryzhyk, V. Tannen, "DBSP: Automatic Incremental View Maintenance
        for Rich Query Languages", PVLDB 16(7):1601–1614, 2023 (arXiv 2203.16684); Flink and RisingWave timings from
        our own hands-on runs on the same story; Feldera 0.384.0 documentation
        (docs.feldera.com: completion tokens, lateness, JSON format). Our run: Feldera 0.384.0 in Docker (4 workers, 3
        GB memory cap) and DuckDB 2.0 in Python, on an M4 Pro laptop with 24 GB; the readings are the synthetic fab
        story used throughout this blog.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function SqlOverLiveReadingsFigure() {
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Time per one-minute step: Feldera 16.7, 18.4 and 18.6 ms with 0 to 6, 24 and 72 hours of history; rerunning in DuckDB 8.9, 21.9 and 55.6 ms">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        RUN
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        ms per one-minute step, by history
      </text>
      {RUNS.map((r, i) => {
        const x = 30 + i * 165;
        const s = (v: number) => (v / 60) * 120;
        return (
          <g key={r.label}>
            <rect x={x} y={170 - s(r.feldera)} width="50" height={s(r.feldera)} fill="var(--ok)" />
            <rect x={x + 56} y={170 - s(r.recompute)} width="50" height={s(r.recompute)} fill="#C98A16" />
            <text x={x + 25} y={164 - s(r.feldera)} textAnchor="middle" fontSize="12" fill="var(--ink)" fontFamily="var(--f-mono)">
              {r.feldera}
            </text>
            <text x={x + 81} y={164 - s(r.recompute)} textAnchor="middle" fontSize="12" fill="var(--ink)" fontFamily="var(--f-mono)">
              {r.recompute}
            </text>
            <text x={x + 53} y="192" textAnchor="middle" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
              {r.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
