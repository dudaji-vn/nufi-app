import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 1. A reading of the Flowco paper (arXiv 2504.14038, April 2025) and of its code
// (github.com/stephenfreund/flowco, last commit 2026-05-04; PyPI 0.76.0). Read, not run: Flowco needs an OpenAI key.
// Every claim about the code was checked in the source.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const mono = 'var(--f-mono)';
const body = 'var(--f-body)';

// ---- a node's levels, and the two directions ----
function LevelsDiagram() {
  const levels = [
    { y: 20, title: 'Label', sub: '"Select Fortis"', note: 'shown on the canvas' },
    { y: 100, title: 'Requirements + output type', sub: 'prose bullets · columns, types, meanings', note: 'the contract' },
    { y: 180, title: 'Code', sub: 'one pure Python function', note: 'run on the inputs' },
    { y: 260, title: 'Output', sub: 'a table, a value, or a plot', note: 'checked against the type' },
  ];
  const bx = 150, bw = 300, bh = 56;
  return (
    <svg viewBox="0 0 720 340" role="img" aria-label="A Flowco node has levels: label, requirements with an output type, code, and its output. Going down, each level is generated from the one above, each LLM call limited to one node and one level, cached on its inputs and regenerated from a diff; the code is then run to give the output. Going up, from an edited level to the others, is done by a chat agent when the user asks">
      {levels.map((l, i) => (
        <g key={l.title}>
          <rect x={bx} y={l.y} width={bw} height={bh} rx="8" fill="none" stroke={i === 1 ? C.ok : C.rule} strokeWidth={i === 1 ? 2.5 : 1.5} />
          <text x={bx + 16} y={l.y + 24} fontSize="15" fill={C.ink} fontFamily={body} fontWeight="700">
            {l.title}
          </text>
          <text x={bx + 16} y={l.y + 44} fontSize="12" fill={C.mute} fontFamily={body}>
            {l.sub}
          </text>
          <text x={bx - 12} y={l.y + 34} textAnchor="end" fontSize="12" fill={C.mute} fontFamily={body}>
            {l.note}
          </text>
          {i < levels.length - 1 && (
            <>
              <line x1={bx + 90} x2={bx + 90} y1={l.y + bh + 2} y2={l.y + 78} stroke={C.ok} strokeWidth="2" markerEnd="url(#fc-down)" />
              <line x1={bx + 210} x2={bx + 210} y1={l.y + 78} y2={l.y + bh + 2} stroke={C.amber} strokeWidth="2" strokeDasharray="4 3" markerEnd="url(#fc-up)" />
            </>
          )}
        </g>
      ))}
      <defs>
        <marker id="fc-down" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--ok)" />
        </marker>
        <marker id="fc-up" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#C98A16" />
        </marker>
      </defs>
      <text x="480" y="70" fontSize="13" fill={C.ok} fontFamily={body} fontWeight="700">
        down: built
      </text>
      <text x="480" y="90" fontSize="12" fill={C.ink} fontFamily={body}>
        each LLM call: one level,
      </text>
      <text x="480" y="108" fontSize="12" fill={C.ink} fontFamily={body}>
        cached on its inputs,
      </text>
      <text x="480" y="126" fontSize="12" fill={C.ink} fontFamily={body}>
        regenerated from a diff
      </text>
      <text x="480" y="190" fontSize="13" fill={C.amber} fontFamily={body} fontWeight="700">
        up: on request
      </text>
      <text x="480" y="210" fontSize="12" fill={C.ink} fontFamily={body}>
        a chat agent, told
      </text>
      <text x="480" y="228" fontSize="12" fill={C.ink} fontFamily={body}>
        "don't change the code"
      </text>
      <text x="0" y="332" fontSize="12" fill={C.mute} fontFamily={body}>
        a Flowco node, as built by its code (May 2026) · the optional "algorithm" level between requirements and
        code is off by default
      </text>
    </svg>
  );
}

// ---- the phases a node climbs ----
function PhaseLadder() {
  const rows = [
    { label: 'build', phases: ['clean', 'requirements', 'code', 'runnable', 'run checked'] },
    { label: 'checks', phases: ['assertions code', 'assertions checked'] },
    { label: 'tests', phases: ['unit tests code', 'unit tests checked'] },
  ];
  const LLM = ['requirements', 'code', 'assertions code', 'unit tests code'];
  const x0 = 80, bw = 112, gap = 18;
  return (
    <svg viewBox="0 0 720 220" role="img" aria-label="The phases a Flowco node climbs: clean, requirements, code, runnable, run checked; then, in the checks view, assertion code and assertions checked; in the tests view, unit-test code and unit tests checked. The LLM writes the requirements, the code, the assertion code and the unit-test code">
      <text x="0" y="16" fontSize="12" fill={C.ink} fontFamily={body}>
        <tspan fill="var(--ok)" fontWeight="700">
          green: the LLM writes it
        </tspan>
        <tspan fill={C.mute}> · grey: Python runs or checks it</tspan>
      </text>
      {rows.map((r, i) => {
        const y = 36 + i * 56;
        const start = i === 0 ? 0 : 3;
        return (
          <g key={r.label}>
            <text x="0" y={y + 21} fontSize="12" fill={C.mute} fontFamily={body} fontWeight="700">
              {r.label}
            </text>
            {r.phases.map((p, j) => {
              const x = x0 + (start + j) * (bw + gap);
              const llm = LLM.includes(p);
              return (
                <g key={p}>
                  <rect x={x} y={y} width={bw} height="32" rx="5" fill={llm ? C.ok : C.rule} opacity={llm ? 0.85 : 0.6} />
                  <text x={x + bw / 2} y={y + 20} textAnchor="middle" fontSize={p.length > 15 ? 9.5 : 11} fill={llm ? 'var(--ground)' : C.ink} fontFamily={mono} fontWeight="700">
                    {p}
                  </text>
                  {j < r.phases.length - 1 && (
                    <text x={x + bw + gap / 2} y={y + 21} textAnchor="middle" fontSize="13" fill={C.mute}>
                      →
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        );
      })}
      <text x="0" y="210" fontSize="12" fill={C.mute} fontFamily={body}>
        an edit lowers the node, and every node downstream, to an earlier phase; the next build climbs back with the cache
      </text>
    </svg>
  );
}

export function FlowcoBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>One node, many levels: what Flowco teaches about keeping an LLM's work in sync</h1>
      <p className="standfirst">
        Imagine one data step you can read as a sentence, a contract, code, a table or a chart — and edit in whichever
        is easiest, with the rest following. Flowco is the closest working system we found. We read its paper and its
        code: the way down is engineered; the way up is a chat agent.
      </p>
      <PostByline />

      <p>
        The idea this series researches: a <strong>node</strong> — a source, a transformation, a metric, a view — is
        one thing with several projections. An intent in plain words ("uptime per tool, last hour"), a schema, the code
        that computes it, the resulting table, a chart. An engineer edits whichever projection suits them, and the
        others are brought back in line; nodes form a graph, so a change flows downstream like a spreadsheet.
      </p>
      <p>
        Before building anything we looked for who has done this. The closest is <strong>Flowco</strong> (Williams
        College, UMass Amherst, UCLA; arXiv 2504.14038, April 2025; Apache-2.0). We read the paper and the code —
        the repository as of its last commit, May 2026 (version 0.76.0). We did not run it: it needs an OpenAI account. Every statement about the
        code below was checked in the source.
      </p>

      <h2>01 · What Flowco is</h2>
      <p>
        A visual dataflow editor for data analysis, with an LLM at every step. The analyst draws nodes — load a
        dataset, compute something, make a plot — and connects them. Flowco writes the code for each node with an LLM
        (GPT-4o by default), runs it in a pool of Python kernels and shows the output next to the node. The interface is
        Streamlit; the code it writes is Python with pandas, NumPy, SciPy, scikit-learn and statsmodels (plus matplotlib and seaborn for plots). Nodes are pure functions: each sees the outputs of all its ancestors,
        and nothing else.
      </p>
      <p>
        The authors' argument is that the graph is not only a picture for the user — it is what makes the LLM
        reliable. Every generation step is limited to one node, so an LLM call cannot quietly change anything else.
      </p>

      <h2>02 · A node at several levels</h2>
      <p>
        Each node is held at three levels of abstraction, and the user works at whichever they like — some never open
        the code:
      </p>
      <figure>
        <LevelsDiagram />
        <figcaption>
          The middle level is the contract: the requirements as prose bullets, plus an "extended type" — for a table,
          its columns, their types and what each means. The code is generated <em>from</em> it, inside a template whose
          docstring repeats it; the output is checked <em>against</em> it.
        </figcaption>
      </figure>
      <p>Against the five projections we have in mind:</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Our projection</th>
              <th>In Flowco</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Intent</td>
              <td>label (short) and requirements (detailed)</td>
            </tr>
            <tr>
              <td>Schema</td>
              <td>the output type: columns, types, descriptions — close to what we mean</td>
            </tr>
            <tr>
              <td>Code</td>
              <td>one Python function</td>
            </tr>
            <tr>
              <td>Table</td>
              <td>the output, kept with the node and saved with the page — viewable, not editable</td>
            </tr>
            <tr>
              <td>Chart</td>
              <td>a separate kind of node, not a view of the same node</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>03 · Down: one node, one level at a time — and a cache</h2>
      <p>
        Building a node is a climb through phases. The LLM writes the requirements and output type (from the graph, as
        JSON and as an image, and the requirements of the nodes before it), then the code; Python runs it and checks it.
        Nodes are processed in graph order, in parallel where they can be.
      </p>
      <figure>
        <PhaseLadder />
        <figcaption>
          The LLM writes four of the nine phases (checks and tests are run from their own views); the others run or check, calling the LLM again only to repair code or
          to judge a plot. An optional "algorithm" phase between requirements and code exists
          in the code but is off by default.
        </figcaption>
      </figure>
      <p>
        What makes it stable is a cache for each LLM phase. Each declares its input fields — the code phase, for example,
        reads the preconditions, requirements, parameters and output type — and its output fields. If the inputs did not
        change, the LLM is not called. If they did, Flowco has the LLM summarise what changed in the inputs (a "semantic
        diff") and asks:
      </p>
      <blockquote>
        <p>
          "Here are the changes to reflect in the new code: … Preserve any existing code as much as possible."
        </p>
      </blockquote>
      <p>
        And when the user edited a generated level by hand, the instruction is "Make as few changes to the existing
        requirements as possible." This is the answer to the first fear about LLM-maintained projections — that every
        change regenerates everything and the user's work is lost.
      </p>

      <h2>04 · Up: a button and an agent</h2>
      <p>
        Going the other way — the user edits the code, and the requirements and label should follow — is where it gets
        harder. In the node editor every level has a button — for the code of a compute node, "Code → Label and
        Requirements and Return Type". It hands the node to the editor's chat agent with one instruction: <em>"The code
        has been modified. Propagate those changes to the Label and Requirements and Return Type. Don't change the
        code."</em> The agent changes the node through a tool call. A "Check Consistency" button asks the LLM whether
        the levels contradict each other; "Regenerate" rewrites the requirements and the code, using their current
        values as a guide.
      </p>
      <p>
        One detail in the code tells a story. Its prompt file still holds structured prompts for exactly this
        direction — <code>lift_up_changes_from_code</code>: describe what changed in the code, carry it into the
        algorithm, then the requirements, then the label, step by step. <strong>Nothing in the code calls them.</strong>{' '}
        The version that ships does the upward direction with the node editor's chat agent instead, when the user asks.
      </p>
      <p>
        For our idea this is the key finding. "Edit any projection and the others follow" is two problems. Downward —
        from intent to contract to code — can be engineered: small steps, a cache, diffs. Upward — from a hand-edited
        query back to the intent — is a translation with no single right answer, and Flowco leaves it to an agent and a
        human click.
      </p>

      <h2>05 · Locking a node</h2>
      <p>
        A user can lock a node. When something upstream changes, the LLM does not touch a locked node; it checks it and
        writes warnings in the form "… may need to change because …". This is the pin we planned for user edits — with
        one difference: Flowco locks a whole node, where we want to pin a single projection (keep my query, regenerate
        my chart).
      </p>

      <h2>06 · Guards: checks in plain words</h2>
      <ul>
        <li>
          <strong>Assertions</strong> are written as sentences ("Verify that the length of the bootstrap_average list is at
          least 5,000") and
          turned into Python checks; for plots, the LLM looks at the image ("the histogram is bimodal").
        </li>
        <li>
          <strong>Unit tests</strong> are sentences too ("Test with a DataFrame containing no 'fortis' species"): Flowco generates the inputs,
          runs the node's code on them and checks the result. The LLM can suggest both.
        </li>
        <li>
          <strong>Repairs</strong>: a syntax error, a crash or an output that does not match its type goes back to the
          LLM for that node — three attempts by default. If it still fails, the user can ask for a repair of the
          whole graph.
        </li>
      </ul>

      <h2>07 · What the user study says, and does not</h2>
      <p>
        Twelve students in data science, mostly, with a 12-minute tutorial, seven minutes of open exploration and seven
        minutes for one question. Everyone completed an analysis; eight of twelve said they would consider using it;
        almost all preferred it to asking a chatbot for code. One said they trusted it more "knowing that there is a
        layer of prompting that was carefully engineered, and that outputs are being checked for type matching and such".
      </p>
      <p>
        The limits are as clear: seven of twelve noticed the LLM's latency; two hit code errors Flowco could not repair;
        participants were students, not working analysts; and whether the answers
        were right was self-reported, not scored. A small study, honestly reported — and a useful template for testing our own demo.
      </p>

      <h2>08 · What we take, and what we leave</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Take</th>
              <th>Leave</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Levels with a contract in the middle</td>
              <td>Python and pandas as the only runtime — our nodes are SQL, on batch and live data</td>
            </tr>
            <tr>
              <td>Each LLM call limited to one node and one level; a cache per LLM phase; regenerate from a diff</td>
              <td>Streamlit, and an OpenAI account required (other models optional)</td>
            </tr>
            <tr>
              <td>Lock and check, with warnings — as a pin per projection</td>
              <td>A chart as a separate node</td>
            </tr>
            <tr>
              <td>Checks and tests written in plain words</td>
              <td>Leaving the upward direction to a chat agent and a click</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        One more thing SQL gives us that pandas did not give Flowco: much of the work needs <em>no</em> LLM. A SQL
        parser reads a query's output columns, their types and their lineage exactly; running the query gives the
        table. The LLM is then needed only between plain words and the contract. Where an algorithm can replace the LLM,
        it should — that is the thread of this series.
      </p>
      <p>
        Next: <strong>semantic operators</strong> — filter, join and aggregate written in plain words, as database
        operators (LOTUS, Palimpzest), tried on our equipment logs.
      </p>

      <p className="foot-note">
        Sources: S. N. Freund, B. Simon, E. D. Berger, E. Jun, "Flowco: Rethinking Data Analysis in the Age of LLMs",
        arXiv 2504.14038 (2025); the Flowco repository (github.com/stephenfreund/flowco, Apache-2.0), last commit
        2026-05-04 (PyPI 0.76.0): node model, phases and cache (dataflow/, builder/cache.py), regeneration prompts
        (builder/graph_completions.py, util/prompts.yaml), node editor (ui/dialogs/node_editor.py). Read, not run.
      </p>
    </>
  );
}

// The "Latest" slot figure: down engineered, up on request.
export function FlowcoFigure() {
  const boxes = ['Intent', 'Contract', 'Code', 'Output'];
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Flowco keeps a node at several levels: going down from intent to contract to code is generated step by step, cached and regenerated from diffs; going up is done by a chat agent on request">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        READ
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        Flowco's paper and code
      </text>
      {boxes.map((b, i) => (
        <g key={b}>
          <rect x={10 + i * 128} y="56" width="104" height="40" rx="8" fill="none" stroke={i === 1 ? 'var(--ok)' : 'var(--rule)'} strokeWidth="2" />
          <text x={62 + i * 128} y="81" textAnchor="middle" fontSize="14" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="700">
            {b}
          </text>
          {i < 3 && <text x={124 + i * 128} y="82" textAnchor="middle" fontSize="16" fill="var(--ok)">→</text>}
        </g>
      ))}
      <text x="10" y="150" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        Down: one level per call, cached, from a diff
      </text>
      <text x="10" y="178" fontSize="15" fill="#C98A16" fontFamily="var(--f-body)" fontWeight="600">
        Up: a chat agent, when the user asks
      </text>
    </svg>
  );
}
