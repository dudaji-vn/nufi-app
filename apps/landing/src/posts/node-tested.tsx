import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 7. The node demo of part 6 on a larger test: 84 intents on 4 tables (sets written
// before the change each one tests), rule checks on the model's SQL, the graph saved, live mode on Feldera.
// qwen2.5 7B and 14B on Ollama, DuckDB 2.0, Feldera 0.384.0 in Docker, on an M4 Pro laptop (24 GB). One run per number
// unless the text says three.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const mono = 'var(--f-mono)';

// ---- live step time, DuckDB vs Feldera ----
function StepChart() {
  const rows = [
    { h: '0 h of history', duck: 19.9, feld: 52.1 },
    { h: '24 h of history', duck: 109.9, feld: 73.3 },
  ];
  const max = 120, x0 = 150, w = 480;
  const bar = (v: number) => (v / max) * w;
  return (
    <svg viewBox="0 0 720 230" role="img" aria-label="Median time of one live step of the whole graph. With no history DuckDB takes 19.9 ms and Feldera 52.1 ms. With 24 hours of history DuckDB takes 109.9 ms and Feldera 73.3 ms">
      {rows.map((r, i) => {
        const y = 30 + i * 95;
        return (
          <g key={r.h}>
            <text x="0" y={y + 32} fontSize="14" fill={C.ink} fontFamily={body} fontWeight="700">
              {r.h}
            </text>
            <rect x={x0} y={y} width={bar(r.duck)} height="26" rx="3" fill={C.amber} />
            <text x={x0 + bar(r.duck) + 8} y={y + 18} fontSize="13" fill={C.ink} fontFamily={mono}>
              {r.duck} ms DuckDB
            </text>
            <rect x={x0} y={y + 32} width={bar(r.feld)} height="26" rx="3" fill={C.ok} />
            <text x={x0 + bar(r.feld) + 8} y={y + 50} fontSize="13" fill={C.ink} fontFamily={mono}>
              {r.feld} ms Feldera
            </text>
          </g>
        );
      })}
      <text x="0" y="222" fontSize="12" fill={C.mute} fontFamily={body}>
        median of 30 steps; one step = one minute of readings (2,160) and a refresh of all 7 nodes
      </text>
    </svg>
  );
}

export function NodeTestedBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>Our node on a larger test: 84 intents, rule checks on the model's SQL, and a live mode on Feldera</h1>
      <p className="standfirst">
        Part 6 built a node you can edit as words, SQL, schema, table or chart. Its one weak number was the model's: 8 of
        10 intents turned into the right SQL. On 84 intents and twice as many tables that number did not hold. Facts in
        the prompt helped, and rule checks on the model's SQL helped more, on intents written before the checks. We also
        moved live mode onto an incremental engine, and found our own slowest step on the way.
      </p>
      <PostByline />

      <p>
        In <a href="/blog/our-node-design-built">part 6</a> the model's only job between words and SQL was measured on
        10 intents over 2 tables, in one run. That is too small to build on. This post makes the test larger and more
        honest, then fixes what it finds, then measures what an incremental engine buys a live graph.
      </p>

      <h2>01 · A larger, fairer test</h2>
      <p>
        We added two tables to the demo's sensor readings and maintenance notes: <code>lots</code> (120 lots, with a
        product and when each entered and left its chamber) and <code>limits</code> (an upper limit per sensor). Then we
        wrote intents in six groups: one table, time windows, joins, ranking, filters on groups, and semantic questions
        about the notes. Every intent has a hand-written answer, and the result is compared by value, so column names
        and order do not matter.
      </p>
      <p>
        The important part is <strong>when</strong> each set was written. We changed the prompt and added checks by
        reading the model's mistakes. A change tuned on a set of intents will look good on that set. So each change was
        tested on intents written before it:
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Set</th>
              <th>Intents</th>
              <th>Written before</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>v2</td>
              <td>40 (including part 6's 10)</td>
              <td>— (the changes were made by reading its failures)</td>
            </tr>
            <tr>
              <td>v2h</td>
              <td>20</td>
              <td>the prompt rules</td>
            </tr>
            <tr>
              <td>v2h2</td>
              <td>12</td>
              <td>the table descriptions</td>
            </tr>
            <tr>
              <td>v2h3</td>
              <td>12</td>
              <td>the rule checks</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        For the semantic intents, the answer is the label each note was written from, kept in a table the model never
        sees. So a <code>sem_filter</code> that judges a note wrongly counts as wrong.
      </p>

      <h2>02 · More tables, worse SQL; facts help</h2>
      <p>
        With part 6's prompt, the larger catalog alone broke 3 of the 10 intents that passed in part 6. The model
        joined notes to lots for no reason (60 rows instead of 5), copied <code>ETCH-05</code> where the intent said{' '}
        <code>ETCH-07</code>, and took a maximum with <code>CASE WHEN</code> instead of a filter. A score on 2 tables
        does not carry over to a catalog with more in it.
      </p>
      <p>
        We gave the model two kinds of facts, both found by a query, not guessed: the data's time range (so "from
        03:00" lands on the data's date, not on today), and five SQL habits (<code>time_bucket</code> for N-minute
        windows, <code>lag</code> for a change, <code>QUALIFY</code> for the top row per group, "join a table only
        when you need its column", "every 'per X' is a GROUP BY column"). Then a one-line description of each table.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>qwen2.5 7B, exact (match)</th>
              <th>v2 (40)</th>
              <th>v2h (20)</th>
              <th>v2h2 (12)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>part 6's prompt</td>
              <td>24 (25)</td>
              <td>8 (8)</td>
              <td>—</td>
            </tr>
            <tr>
              <td>+ time range and SQL habits</td>
              <td>26 (29)</td>
              <td>
                <strong>11 (13)</strong>
              </td>
              <td>8 (8)</td>
            </tr>
            <tr>
              <td>+ a line per table</td>
              <td>28 (31)</td>
              <td>14 (15)</td>
              <td>
                <strong>6 (7)</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Bold marks the fair test: the first run on a set written before that change. The time range and the habits
        helped on intents they had never seen (8 → 11 exact). The table descriptions did not: on the set written to
        test them, the score went down (8 → 6). In three seeded runs at temperature 0.3 they made the total over all 72
        intents higher and steadier (46–47 against 35–46 exact), but on that set still lower (6, 6, 6 against 7, 8, 7).
        We kept them and say plainly that they are not proven. "Match" also counts an answer with one extra column, such
        as the maximum next to the chambers that were asked for.
      </p>
      <p>
        The larger qwen2.5 14B, with the same prompt, got 35 of 72 exact against the 7B's 48, and took 3.5 times as
        long (median 6.5 s against 1.9 s per intent). The prompt was tuned on the 7B's mistakes, but as in part 6, a
        bigger model was not the fix.
      </p>

      <h2>03 · Rule checks on the model's SQL</h2>
      <p>
        The misses that were left were mostly of kinds you can see in the SQL itself: 7 tables joined for no reason, 4
        wrong groupings, 2 values copied wrong (one of them does not exist at all). That is the split from{' '}
        <a href="/blog/semantic-operators-rule-or-model">part 2</a> again: let a rule say what is checkable. After the
        parser and a dry run accept the SQL, four checks read it (SQLGlot, no model):
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Check</th>
              <th>Speaks when</th>
              <th>Example</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>unknown value</td>
              <td>a text literal is not among the column's known values</td>
              <td>
                <code>tool = 'CVD-07'</code>
              </td>
            </tr>
            <tr>
              <td>needless join</td>
              <td>the query uses only a table's join keys, and those keys repeat in it, so the join multiplies rows</td>
              <td>counting readings instead of lots</td>
            </tr>
            <tr>
              <td>"per X" missing</td>
              <td>the intent says per lot, for each tool or "in 20-minute windows", and nothing groups by it</td>
              <td>"Lots with…" grouped by tool and chamber</td>
            </tr>
            <tr>
              <td>finer time than asked</td>
              <td>the query groups by the asked window and also by a smaller one</td>
              <td>20-minute windows, also per minute</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        If a check speaks, the SQL goes back to the model once, with the check's sentence, through the repair the node
        already had. If it still speaks after that, the node runs and shows a warning; a check never blocks. Two
        exceptions came from the first version, which spoke on 7 of 53 right answers: a needless join on a key that does
        not repeat (one query tells), or under <code>DISTINCT</code>, <code>MIN</code>, <code>MAX</code> or{' '}
        <code>COUNT(DISTINCT …)</code>, cannot change the answer, so it is left alone. On the 84 hand-written answers
        the checks say nothing; that is a test.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>qwen2.5 7B, exact (match)</th>
              <th>all 84</th>
              <th>v2h3 (12, written before the checks)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>without checks</td>
              <td>54 (60)</td>
              <td>6 (7)</td>
            </tr>
            <tr>
              <td>with checks</td>
              <td>
                <strong>60 (68)</strong>
              </td>
              <td>
                <strong>8 (10)</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        The checks sent 10 of 84 answers back. 8 went from wrong to right, one right answer stayed right, one wrong
        answer stayed wrong, and none went from right to wrong. A check takes 0.5 ms; the extra model call added 0.3 s per
        intent on average. What they cannot catch: a value that exists but is the wrong one (<code>ETCH-05</code> for{' '}
        <code>ETCH-07</code>), and the semantic filter misjudging a note (it found 2 of 3 chiller problems).
      </p>

      <h2>04 · The graph survives a restart</h2>
      <p>
        Until now, restarting the demo lost every node a user had made. The graph is now saved after every change, as
        one JSON file written to a temporary file and renamed, so a crash never leaves half a graph. Only what a person
        or the model wrote is saved: the intent, the code, pins, a suggestion still waiting. Schema, table and chart are
        derived again from the code when it loads, by the parser and the engine, with no model call. We edited a node's
        limit, stopped the server and started it again: the node came back with its new SQL, its 65 rows, and the
        model's suggestion still waiting next to the user's words.
      </p>

      <h2>05 · Live mode on Feldera</h2>
      <p>
        In <a href="/blog/z-sets-batch-and-live-sql">part 4</a> one SQL program gave the same rows recomputed by DuckDB
        and maintained incrementally by Feldera, and incremental paid off once there was enough history. Now the whole
        graph runs that way. Each node's SQL is translated to Feldera's dialect by SQLGlot. A node Feldera cannot run
        stays in DuckDB and says why: <code>pump_notes</code> uses <code>sem_filter</code>, a Python call to the model.
        A Feldera node reads only sources and Feldera nodes, a DuckDB node only sources and DuckDB nodes, so nothing is
        copied between them. Feldera took 4 of the 5 scenario nodes, and all 4 gave exactly DuckDB's rows.
      </p>
      <figure>
        <StepChart />
        <figcaption>
          With no history, recomputing is cheaper. With a day of readings (3.2 million), Feldera's step is 1.5 times
          faster: DuckDB recomputes the minute averages (30 ms) and the uptime (33 ms) at every step, Feldera only
          reads them.
        </figcaption>
      </figure>
      <p>
        Most of what is left on Feldera's side is reading, not computing: sorting and sending the first 5,000 of 26,460
        minute averages to the table view costs 29 ms. A view that shows fewer rows, or reads only what changed, would
        remove most of it.
      </p>
      <p>
        <strong>The surprise was our own code.</strong> The first runs said both engines were slow: 189 ms against 221
        ms per step, 274 against 258 ms with a day of history. When we timed each part of a step, 174 of the 188 ms
        went to appending the minute's 2,160 readings to DuckDB one row at a time. One bulk insert through an Arrow
        table takes 1.4 ms. The demo now starts in 5–10 seconds instead of about 30, and a day of history loads in 0.6 s
        instead of 259 s. Measure the whole step before you blame the engine.
      </p>

      <h2>06 · What we take from it</h2>
      <ul>
        <li>
          <strong>Test the model on intents written before you tuned for them.</strong> Our tuned set rose from 24 to
          29 exact; the fair sets show the real gains, and one change that did not help.
        </li>
        <li>
          <strong>Facts and rules, not a bigger model.</strong> The data's time range, a few SQL habits and four rule
          checks moved the 7B model; the 14B model did worse and slower.
        </li>
        <li>
          <strong>Every check should come with a sentence the model can act on</strong>, and leave the user a warning
          if the doubt remains, instead of a silent fix or a hard stop.
        </li>
        <li>
          <strong>An incremental engine pays off for a live graph once history grows</strong>, and the parts the model
          has to run (a semantic filter) stay where they can run.
        </li>
      </ul>

      <h2>Limits</h2>
      <p>
        84 intents on 4 small tables, written by us; on a set of 12, one intent moves the score by 8 points. One run at temperature 0
        for most numbers, three seeded runs for one comparison. The "per X" check reads English phrases and our column
        names. Live mode in the demo itself still recomputes in DuckDB: using Feldera there means compiling the program
        (30 s) whenever a node's SQL changes. Feldera ran in Docker with 3 GB and 4 workers on one laptop.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function NodeTestedFigure() {
  const bars = [
    { label: 'without checks', v: 54, c: 'var(--ink-mute)' },
    { label: 'with rule checks', v: 60, c: 'var(--ok)' },
  ];
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Of 84 intents, qwen2.5 7B wrote the right SQL for 54 without rule checks and 60 with them">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        TESTED
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        right SQL, of 84 intents (7B)
      </text>
      {bars.map((b, i) => (
        <g key={b.label}>
          <text x="10" y={68 + i * 50} fontSize="13" fill="var(--ink)" fontFamily="var(--f-body)">
            {b.label}
          </text>
          <rect x="150" y={52 + i * 50} width={(b.v / 84) * 320} height="24" rx="3" fill={b.c} />
          <text x={158 + (b.v / 84) * 320} y={69 + i * 50} fontSize="13" fill="var(--ink)" fontFamily="var(--f-mono)">
            {b.v}
          </text>
        </g>
      ))}
      <text x="10" y="180" fontSize="14" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        Rules read the model's SQL; none turned a right answer wrong
      </text>
    </svg>
  );
}
