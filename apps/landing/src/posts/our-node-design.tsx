import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 6. Our node design from parts 1–5, built as a local demo: Python (DuckDB,
// SQLGlot, FastAPI), a React page, qwen2.5 7B on Ollama, on an M4 Pro laptop (24 GB). Every number is one run.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const MODEL = '#8A5CD6';

// ---- who derives what ----
function DeriveDiagram() {
  const boxes = [
    { id: 'Intent', x: 20, y: 30 },
    { id: 'Code (SQL)', x: 260, y: 30 },
    { id: 'Schema', x: 500, y: 30 },
    { id: 'Table', x: 260, y: 160 },
    { id: 'Chart', x: 500, y: 160 },
  ];
  const w = 180, h = 48;
  const arrow = (x1: number, y1: number, x2: number, y2: number, color: string, label: string, lx: number, ly: number, dash = false) => (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth="2" strokeDasharray={dash ? '5 4' : undefined} markerEnd="url(#nd-arrow)" />
      <text x={lx} y={ly} fontSize="12" fill={color} fontFamily={body} fontWeight="700" textAnchor="middle">
        {label}
      </text>
    </g>
  );
  return (
    <svg viewBox="0 0 720 260" role="img" aria-label="Who derives each projection. The model writes the code from the intent, and from an edited code only a suggested intent. The parser derives the schema from the code. The engine derives the table from the code. A rule derives the chart from the schema and table">
      <defs>
        <marker id="nd-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--ink-mute)" />
        </marker>
      </defs>
      {boxes.map((b) => (
        <g key={b.id}>
          <rect x={b.x} y={b.y} width={w} height={h} rx="8" fill="none" stroke={C.rule} strokeWidth="2" />
          <text x={b.x + w / 2} y={b.y + 30} textAnchor="middle" fontSize="15" fill={C.ink} fontFamily={body} fontWeight="700">
            {b.id}
          </text>
        </g>
      ))}
      {arrow(200, 46, 258, 46, MODEL, 'model', 229, 36)}
      {arrow(258, 66, 200, 66, MODEL, 'suggests', 229, 90, true)}
      {arrow(440, 54, 498, 54, C.ok, 'parser', 469, 44)}
      {arrow(350, 78, 350, 158, C.amber, 'engine', 385, 122)}
      {arrow(590, 78, 590, 158, '#C98A16', 'rule', 612, 122)}
      {arrow(440, 184, 498, 184, '#C98A16', '', 0, 0)}
      <text x="20" y="236" fontSize="12" fill={C.mute} fontFamily={body}>
        solid: applied · dashed: a suggestion the user accepts · a pinned projection is never rewritten
      </text>
    </svg>
  );
}

function Shot({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return (
    <figure>
      <img src={src} alt={alt} loading="lazy" />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

export function OurNodeDesignBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>Our node design, built: one data step as intent, code, schema, table and chart</h1>
      <p className="standfirst">
        Five posts asked which parts of a data question need a language model. This one puts the answers into a
        working system. In our design a node is a single data step that you can read and edit as words, as SQL, as a
        schema, as a table and as a chart, and nodes form a graph that updates itself, in batch or live. The model translates between words and SQL, and judges the rows a semantic filter cannot rule out
        by a rule. A parser, an engine and a few rules do everything else, in milliseconds.
      </p>
      <PostByline />

      <p>
        The idea we started this series with: in a self-service data platform, one step of an analysis — a source, a
        filter, a metric — should be one thing with several faces. An engineer edits whichever face suits them, and the
        others follow. The five posts gave us the rules for building it:
      </p>
      <ul>
        <li>
          <a href="/blog/flowco-one-node-many-levels">Flowco</a>: build down one level per step, never overwrite what the
          user wrote, and treat the way back up (code to words) as a suggestion.
        </li>
        <li>
          <a href="/blog/semantic-operators-rule-or-model">Semantic operators</a>: split each question; rules answer
          names and codes, the model only what needs meaning.
        </li>
        <li>
          <a href="/blog/write-the-rule-once">Compiling the rule</a>: the schema of a SQL query comes from a parser,
          not a model.
        </li>
        <li>
          <a href="/blog/z-sets-batch-and-live-sql">Batch and live</a>: one SQL program serves both, and a live
          answer is running until its window closes.
        </li>
        <li>
          <a href="/blog/semantic-filter-on-a-live-stream">Semantic filter on a stream</a>: send the model as few
          rows as possible, and know its throughput.
        </li>
      </ul>

      <h2>01 · The node, and who derives what</h2>
      <p>
        A node has five projections — intent, code, schema, table, chart — plus its inputs, which are read from its SQL,
        not declared. Every projection records who last derived it. The rules are fixed:
      </p>
      <figure>
        <DeriveDiagram />
        <figcaption>
          The model works on the left: words to SQL, and back as a suggestion. Everything to the right of the code is
          derived without a model, except the rows a semantic filter sends to it (section 05).
        </figcaption>
      </figure>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>When this changes</th>
              <th>This is derived</th>
              <th>By</th>
              <th>Measured</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Intent</td>
              <td>Code</td>
              <td>the model; checked by the parser and a dry run, one repair try</td>
              <td>2.2–3.3 s</td>
            </tr>
            <tr>
              <td>Code</td>
              <td>Schema, inputs, time window</td>
              <td>the parser (SQLGlot)</td>
              <td>4–13 ms</td>
            </tr>
            <tr>
              <td>Code, edited by hand</td>
              <td>Intent, as a suggestion to accept</td>
              <td>the model</td>
              <td>1.0 s</td>
            </tr>
            <tr>
              <td>Code or an input</td>
              <td>Table</td>
              <td>the engine (DuckDB)</td>
              <td>7–15 ms</td>
            </tr>
            <tr>
              <td>Schema or table</td>
              <td>Chart</td>
              <td>a rule: time and a number make a line, a category and a number a bar</td>
              <td>&lt; 1 ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Three more rules come from the series. A <strong>pinned</strong> projection (intent, code or chart) is never
        rewritten; a change that would rewrite it shows a warning instead. A node whose input broke is
        <strong> blocked</strong> with the input's name, not repaired by the model. And a table in live mode says
        whether its answer is <strong>final</strong> or still <strong>running</strong>.
      </p>
      <p>
        We wrote the node down as a small spec (version 0.1, as a JSON Schema) and built it: a Python service with
        DuckDB, SQLGlot and a local model (qwen2.5 7B on Ollama), and a one-page web UI. The data is the fab story used
        throughout this blog: two hours of sensor readings, 18 sensors at two a second, and 40 maintenance notes
        written for the same tools and times.
      </p>

      <h2>02 · Words to a table and chart, in two clicks</h2>
      <p>
        "+ node", a name, a sentence, "Generate SQL". The model wrote the SQL, the parser derived the schema and traced
        each column to its source, the engine ran it, and the rule picked a chart. It took 3.3 s; the parser and the
        engine took about 25 ms of that.
      </p>
      <Shot
        src="/blog/semantic-data/node-new.png"
        alt="The node demo: a new node rf_by_hour, its intent, the SQL written by the model, the schema from the parser, the table and the chart"
        caption="&quot;Hourly maximum rf_power per tool and chamber.&quot; Each projection is labelled with who derived it: user, model, parser, engine, rule. The chart splits by tool because the rule found two tools."
      />

      <h2>03 · Edit the SQL: the rest follows, the words wait</h2>
      <p>
        We changed the anomaly limit in the SQL from 1450 to 1500. The schema was re-derived in 4 ms and the table in
        7 ms; the two nodes that read anomalies re-ran in 32 ms. A second later the model's new intent appeared — "…above its 1500 limit." It takes the intent's place,
        flagged as the model's suggestion ("intent?") until someone accepts it; to keep your own words, pin the
        intent.
      </p>
      <Shot
        src="/blog/semantic-data/node-anomalies.png"
        alt="The anomalies node after a hand edit of its SQL: the suggested intent is shown with an Accept button"
        caption="Code by user, schema by parser, table by engine, chart by rule; the intent by the model, waiting for Accept."
      />
      <p>
        When an edit upstream removes a column that others use, nothing is fixed behind your back. A new intent for the
        per-minute node made the model rename <code>avg_value</code> to <code>max_value</code>. The anomaly node turned
        to error ("Column 'avg_value' could not be resolved"), and the two nodes below it to "input anomalies has an
        error".
      </p>

      <h2>04 · Live: the same nodes, running or final</h2>
      <p>
        Switch to live and the story replays on a clock. At each tick (30 story seconds in our run) the graph is re-read in about 0.1 s; three of its nine nodes
        were still stopped by the error above. A per-minute node marks the rows of the minute still filling in as running; a node without a time
        window, like uptime per chamber, says running as a whole until the data ends.
      </p>
      <Shot
        src="/blog/semantic-data/node-live.png"
        alt="Live mode: the per-minute node shows the current minute's rows tinted as running, labelled mixed from 01:51"
        caption="Taken at 10× speed, 01:51:30 on the story clock: the 01:51 rows have about half a minute's readings (61 of 120), and are marked running."
      />

      <h2>05 · A semantic node</h2>
      <p>
        <code>sem_filter(note, 'reports a problem with a pump')</code> is a function in the SQL. A rule answers first:
        25 of the 40 notes are not about a pump and never reach the model. The model judged the other 15, and every
        answer is cached, so a live tick asks nothing twice. Against the notes' labels it was right on all 40.
      </p>
      <Shot
        src="/blog/semantic-data/node-pump-notes.png"
        alt="The pump_notes node: sem_filter with its rule, the rows it ruled out, the model calls and the cache"
        caption="The node shows how many rows the rule ruled out, how many the model judged, and its rows per second of model time."
      />

      <h2>06 · What the model needed was facts; a bigger model did not help</h2>
      <p>
        We gave the model ten intents on the source tables and compared each result with a hand-written answer.
        With table and column names only, qwen2.5 7B got <strong>2 of 10</strong> right. It used the semantic filter on
        a column of sensor names and guessed values that do not exist. Then we added, for every text column with few values, the list of those values, found by one query, and one
        line saying the semantic filter is only for free text. It got <strong>8 of 10</strong>. The larger 14B model, with the same prompt, got 7. Each was one run of ten intents.
      </p>
      <p>
        Trying the demo with the real model found two more gaps, both fixed the same way:
      </p>
      <ul>
        <li>
          Asked for "hourly maximum rf_power", the model read from the anomaly node: it was listed first and had a
          column called rf_power. Listing the source tables first, each node with its intent as a description, fixed it.
        </li>
        <li>
          After the limit changed to 1500, the suggested intent still said 1450. Showing the model the old SQL as well
          as the new one fixed it.
        </li>
      </ul>
      <p>
        That is the series' thread one last time. The cheapest improvements were algorithms giving the model facts it
        could not know, not more model.
      </p>

      <h2>07 · What is not done</h2>
      <ul>
        <li>One user, no saved state; the demo runs on a laptop.</li>
        <li>
          Live mode reruns each node in DuckDB. That is fine for two hours of data; the incremental engine from part 4
          pays off with longer history.
        </li>
        <li>Ten intents is a small test. Every number here is one run.</li>
        <li>
          A suggested intent replaces the old wording instead of sitting next to it; there is no "reject" that brings
          the user's sentence back. Pinning is the only protection today.
        </li>
        <li>
          A review of the build found what a viewer would hit, and we fixed it. Examples: the live clock stopped while
          the model wrote SQL, and a model that was down left an empty node.
        </li>
      </ul>

      <p className="foot-note">
        The demo: Python 3.13 with DuckDB 2.0, SQLGlot 30, FastAPI; a React page with Vega-Lite charts; qwen2.5:7b on
        Ollama; an M4 Pro laptop with 24 GB. The data is the synthetic fab story used throughout this blog; the
        maintenance notes were written by a language model from labelled events. Series: parts 1–5 linked above.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function OurNodeDesignFigure() {
  const items = [
    { t: 'Intent', by: 'user', c: 'var(--ink)' },
    { t: 'Code', by: 'model', c: MODEL },
    { t: 'Schema', by: 'parser', c: 'var(--ok)' },
    { t: 'Table', by: 'engine', c: '#C98A16' },
    { t: 'Chart', by: 'rule', c: '#C98A16' },
  ];
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="One node seen five ways: intent by the user, code by the model, schema by the parser, table by the engine, chart by a rule">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        BUILT
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        one node, five projections
      </text>
      {items.map((it, i) => (
        <g key={it.t}>
          <rect x={10 + i * 102} y="62" width="92" height="44" rx="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
          <text x={56 + i * 102} y="89" textAnchor="middle" fontSize="14" fontWeight="700" fill="var(--ink)" fontFamily="var(--f-body)">
            {it.t}
          </text>
          <text x={56 + i * 102} y="130" textAnchor="middle" fontSize="12" fill={it.c} fontFamily="var(--f-mono)">
            {it.by}
          </text>
        </g>
      ))}
      <text x="10" y="180" fontSize="14" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        The model writes SQL and judges free text; the rest takes ms
      </text>
    </svg>
  );
}
