import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 3. SemBaker (arXiv 2608.06677) and OCTOPUS (arXiv 2610.32586) read; our run on an
// M4 Pro laptop (24 GB): qwen2.5 7B / 14B on Ollama write 42 functions; SQLGlot 30.33 vs the same models on 12 queries.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const mono = 'var(--f-mono)';

// F1 on the new wording for every compiled function, by question; null = the function did not run
const SPREAD: { q: string; ref?: { v: number; label: string }; runs: (number | null)[] }[] = [
  {
    q: 'Q1 pump problem',
    ref: { v: 0.911, label: 'model reads all 200 notes: 0.911' },
    runs: [0.0, 0.3, 0.075, 0.0, 0.932, 0.178, null, 0.771, 0.741, 0.0, 0.0, null, 0.533, 0.571],
  },
  {
    q: 'S symptom present',
    runs: [0.0, 0.0, 0.0, 0.0, 0.261, 0.525, null, 0.0, 0.0, 0.0, 0.791, 0.25, 0.2, 0.436],
  },
  {
    q: 'Q3 replaced',
    ref: { v: 1.0, label: 'hand rule: 1.000' },
    runs: [0.247, 1.0, 1.0, 1.0, 0.083, 0.78, 1.0, 0.0, 1.0, 0.653, 0.465, 0.516, 0.16, 0.083],
  },
];

function SpreadChart() {
  const x0 = 160, w = 500;
  return (
    <svg viewBox="0 0 720 330" role="img" aria-label="F1 on the new wording of 42 functions written by qwen2.5 7B and 14B, 14 per question. Q1 pump problem: from 0.000 to 0.932, two did not run; the model reading every note scores 0.911. S symptom present: from 0.000 to 0.791, one did not run, seven score 0.000; the 0.791 says yes to almost every note. Q3 replaced: from 0.000 to 1.000, five score 1.000; the hand rule scores 1.000">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line x1={x0 + t * w} x2={x0 + t * w} y1="20" y2="272" stroke={C.rule} strokeWidth="1" />
          <text x={x0 + t * w} y="290" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
            {t.toFixed(2)}
          </text>
        </g>
      ))}
      {SPREAD.map((row, i) => {
        const y = 60 + i * 86;
        const failed = row.runs.filter((v) => v === null).length;
        // stack equal values so every function is visible
        const seen: Record<string, number> = {};
        return (
          <g key={row.q}>
            <text x={x0 - 14} y={y + 4} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
              {row.q}
            </text>
            {failed > 0 && (
              <text x={x0 - 14} y={y + 22} textAnchor="end" fontSize="11" fill={C.coral} fontFamily={body}>
                {failed} did not run
              </text>
            )}
            {row.ref && (
              <g>
                <line x1={x0 + row.ref.v * w} x2={x0 + row.ref.v * w} y1={y - 26} y2={y + 26} stroke={C.ok} strokeWidth="2" strokeDasharray="4 3" />
                <text x={x0 + row.ref.v * w - 4} y={y - 30} textAnchor="end" fontSize="11" fill={C.ok} fontFamily={body}>
                  {row.ref.label}
                </text>
              </g>
            )}
            {row.runs.map((v, j) => {
              if (v === null) return null;
              const k = v.toFixed(2);
              const n = (seen[k] = (seen[k] ?? 0) + 1) - 1;
              const dy = ((n + 1) >> 1) * 6 * (n % 2 ? -1 : 1); // stack equal values around the row's line
              return <circle key={j} cx={x0 + v * w} cy={y + dy} r="4.5" fill={C.amber} fillOpacity="0.85" />;
            })}
          </g>
        );
      })}
      <text x="0" y="320" fontSize="12" fill={C.mute} fontFamily={body}>
        one dot per compiled function (7B and 14B; no examples, or 20 from either note set, 3 seeds) · F1 on the new wording
      </text>
    </svg>
  );
}

function SchemaChart() {
  const rows = [
    { n: 'SQLGlot', exact: 10, t: '< 0.2 s', c: C.ok },
    { n: 'qwen2.5 14B', exact: 8, t: '70 s', c: C.amber },
    { n: 'qwen2.5 7B', exact: 5, t: '36 s', c: C.amber },
  ];
  const x0 = 130, w = 480;
  return (
    <svg viewBox="0 0 720 170" role="img" aria-label="Queries whose output columns, types and sources were all right, of 12: SQLGlot 10 in under 0.2 seconds, qwen2.5 14B 8 in 70 seconds, qwen2.5 7B 5 in 36 seconds">
      {rows.map((r, i) => {
        const y = 12 + i * 44;
        return (
          <g key={r.n}>
            <text x={x0 - 12} y={y + 20} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
              {r.n}
            </text>
            <rect x={x0} y={y + 4} width={w} height="24" fill="none" stroke={C.rule} />
            <rect x={x0} y={y + 4} width={(r.exact / 12) * w} height="24" fill={r.c} />
            <text x={x0 + (r.exact / 12) * w + 8} y={y + 21} fontSize="12" fill={C.ink} fontFamily={mono} fontWeight="700">
              {r.exact} / 12 · {r.t}
            </text>
          </g>
        );
      })}
      <text x="0" y="160" fontSize="12" fill={C.mute} fontFamily={body}>
        queries with every output column's name, type and source columns right, against answers written by hand
      </text>
    </svg>
  );
}

export function WriteTheRuleOnceBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>Can the model write the rule once? Compiled semantic operators, and a query's schema without a model</h1>
      <p className="standfirst">
        Asking a model about every row is slow. One answer is to ask it once, for code, and run the code on every row.
        We had local models write 42 such functions. For "was a part replaced?" a third of them were perfect. For
        "does the note report a pump problem?" the score swung between 0 and 0.93 with the examples the model was
        shown. For a SQL query's schema, a parser beat the models.
      </p>
      <PostByline />

      <p>
        In the <a href="/blog/semantic-operators-rule-or-model">previous post</a> a keyword rule and a language model
        split the work on 200 maintenance notes. The rule picked the part from its name, the model judged only whether
        a symptom was present, and the split was right on every note with 74 model calls instead of 200. That still
        meant 74 calls. This post asks how far an algorithm goes with no model at run time: when the model writes the
        rule, and when the question is about a SQL query rather than free text.
      </p>

      <h2>01 · Compile instead of interpret</h2>
      <p>
        <strong>SemBaker</strong> (University of Hawaii at Manoa; arXiv 2608.06677, August 2026) calls the model once
        per operator as a <em>compiler</em>. For a <code>sem_filter</code>, <code>sem_map</code> or{' '}
        <code>sem_join</code> it asks for a deterministic Python function, which then runs on every row. The function
        may not call a model. SemBaker plugs into LOTUS, Palimpzest and other engines. A cost model compiles an operator
        only when there are enough rows to pay for the compile call: about 11 rows for a filter or a map, 187 pairs for
        a join. A lexical screen keeps predicates about tone, sarcasm, nuance or multi-hop reasoning with the model.
      </p>
      <p>
        The paper reports 4.8–6.3× faster runs and 5.4–10.7× lower cost on average. Its single-operator F1 is measured
        against the model's own answers, not against ground truth: 0.890 for filters, 0.911 for maps, 0.961 for joins.
        On whole workloads quality can drop sharply. On a movie benchmark with one backend (Nirvana), F1 fell from 0.793
        to 0.586, while with Palimpzest and LOTUS it rose to 1.000. On a review-mapping task with DocETL it fell from
        0.873 to 0.679. A step that checks compiled code against model-made labels exists, but is off by
        default.
      </p>
      <p>
        <strong>OCTOPUS</strong> (mainly UC Irvine, with UC Berkeley; arXiv 2610.32586, October 2026; a vision paper) takes the
        other road: keep the model on each row, but never pay twice. Every judgement is stored as a "tag" column next to
        the data (NULL when not yet judged), and rules between predicates are derived once per pair of predicates
        (synonym, complement, taxonomy). A later query reuses the tags. On eight queries of a movie benchmark it judged
        268 rows where LOTUS judged 28,910, with quality 0.82 against 0.79 (iPDB scored 0.87, judging 2,768). Reuse has a cost: one query that inherited
        another's tags scored 0.58.
      </p>

      <h2>02 · Our test: the model writes the function</h2>
      <p>
        The same 200 maintenance notes as in the previous post. In the second set the notes avoid every symptom word the
        hand rule knows ("above spec", "grinding sound" instead of "high", "noise"). Three questions: Q1, does the note
        report a problem with a pump? S, was any symptom present? Q3, was a part replaced? qwen2.5 7B and 14B, local
        on Ollama, at temperature 0, got the question and the glossary, and wrote{' '}
        <code>def answer(note: str) -&gt; bool</code> with the standard library only.
      </p>
      <p>
        Unlike SemBaker, some runs also showed 20 labelled example notes (10 yes, 10 no). The examples came from either
        note set, with 3 different random draws. That gives 7 functions per question and model, 42 in all. Each function
        ran in its own Python process on every note it had not seen as an example. A compile call took 3–17 seconds on
        7B and 11–42 on 14B. Running the function over 200 notes took under 0.07 seconds, process start included.
      </p>
      <figure>
        <SpreadChart />
        <figcaption>
          The same request, with different examples, gave functions that score anything from 0 to 0.93 on Q1. On
          "replaced", 5 of 14 were perfect; the rest ranged down to 0. The model line is over all 200 notes.
        </figcaption>
      </figure>

      <h2>03 · What the functions got right, and wrong</h2>
      <p>
        <strong>The examples decide the function.</strong> On Q1 the best function (7B, shown examples from the new
        wording) scored 0.932 on the 180 new-wording notes it had not seen. On the same 180 notes, the model reading
        every note scored 0.891, with 180 calls instead of one. With another draw of examples, the same model and prompt gave 0.178, and with a third, a
        function that did not run. Across all 42, 3 did not run: a syntax error, a call to <code>re.re</code>, a call to
        a module.
      </p>
      <p>
        <strong>A compiled rule learns the words it was given.</strong> The glossary lists symptom words such as
        "high", "noise" and "alarm", and the examples from the first set use them too. Every symptom function written
        from those, with or without examples, scored 0 on the new wording, except one. That one says yes to 194 of 200
        notes, which scores about the same as answering yes to every note (0.78). The new notes say "above spec" and
        "grinding". This is the same failure as the hand-written rule in the previous post, now written by a model.
      </p>
      <p>
        <strong>Word questions compile.</strong> "Was a part replaced?" has an anchor that does not change with the
        writer: the word <em>replaced</em>. Compiled by 7B from known examples, it scored 1.000 in 3 of 3 runs. It was not always so easy:
        14B, shown the same kind of examples, scored 1.000, 0.653 and 0.465; 5 of the 14 "replaced" functions were
        perfect overall. SemBaker
        draws the same line: its code comments call keyword and substring predicates, numeric and date comparisons,
        and field equality the ones that compile well, and free text "with no lexical anchor" the ones that do not.
      </p>
      <p>
        <strong>Without examples, two functions were plainly broken.</strong> One searched for <code>\breplace\b</code>,
        which never matches "replaced", and found 0 of 33. Another required the part name immediately before the
        symptom word, and found none of the 51 pump problems. (The third, 14B on Q1, scored 0.771, better than most of its
        runs that had examples.)
      </p>
      <p>
        These are small local models; SemBaker used a hosted one (gpt-5-mini). A stronger model may make fewer such
        mistakes.
        But the spread between draws is what matters for a platform: a compiled function has to be checked on labelled
        rows before it replaces the model, every time it is compiled.
      </p>

      <h2>04 · A query's schema needs no model</h2>
      <p>
        In the node we are designing, one of the projections is the <em>schema</em>: the output columns of the node's
        query, their types and where each comes from. When the query is SQL, that can be read from the query itself.
        We wrote 12 queries over four fab tables (sensor readings, lots, alarms, maintenance) and the expected answer for
        each by hand. The queries range from a one-table average to a CTE with a window, joins, <code>SELECT *</code>,
        a subquery, a correlated subquery and a timestamp difference.
      </p>
      <p>
        We compared <strong>SQLGlot</strong> 30.33 (parse, qualify, annotate types, trace lineage) with the two models,
        which were given the table definitions and the query and asked for the same JSON.
      </p>
      <figure>
        <SchemaChart />
        <figcaption>
          Of 43 output columns, SQLGlot got the type wrong for 2 and the sources for 1. The models got every name
          right, but 7B got the sources wrong for 19 columns.
        </figcaption>
      </figure>
      <p>SQLGlot's three mistakes can be listed:</p>
      <ul>
        <li>
          no type for <code>DATE_TRUNC('hour', ts)</code>;
        </li>
        <li>
          the window's PARTITION BY and ORDER BY columns counted as sources of <code>v - LAG(v)</code>;
        </li>
        <li>
          <code>end_ts - start_ts</code> typed as a timestamp instead of an interval.
        </li>
      </ul>
      <p>
        14B got two of those three right. The models' mistakes are of another kind. 7B often gave the alias or the whole
        expression as the "source", <code>s.tool</code> instead of <code>fdc.tool</code>, without following the CTE or
        subquery back to the table. 14B named <code>alarms.tool</code> as the source of a <code>COUNT(*)</code>. A
        parser's mistakes can be listed and fixed one by one, and stay fixed. A model's cannot be listed that way.
      </p>

      <h2>05 · What we take</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Part of the question</th>
              <th>Who answers</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>The schema and lineage of a SQL node</td>
              <td>
                The parser, checked against hand-written answers. It said "unknown" for 1 column of 43; 2 more were
                wrong without a warning
              </td>
            </tr>
            <tr>
              <td>Names, codes, units, and words like <em>replaced</em></td>
              <td>A rule, written by hand or by a model, checked on labelled rows before use</td>
            </tr>
            <tr>
              <td>"Is this reading a symptom?"</td>
              <td>The model, only for the rows the rules have not ruled out</td>
            </tr>
            <tr>
              <td>The same judgement asked again</td>
              <td>Stored with the row, as OCTOPUS's tags, and reused</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Next in this series: SQL over live events. In an incremental view, the question is not "is the answer right?"
        but "how much work does it take to keep it right as rows arrive?" — Flink, RisingWave and DBSP.
      </p>

      <p className="foot-note">
        Sources: W. Dong, Y. Wang, "From Interpretation to Compilation: A Compilation-Based Execution Engine for
        Semantic Operator Systems", arXiv 2608.06677 (v1, 2026), code github.com/iDB-Research-Group/SemBaker (AGPL-3.0;
        read, not used); G. Zhang, N. Lahjouji, Y. Lin, A. Colaco, S. Mehrotra, "OCTOPUS: Towards A Tag Model for
        Cross-Query Reuse in Semantic Query Processing", arXiv 2610.32586 (v1, 2026); SQLGlot 30.33. Our run: qwen2.5:7b
        and qwen2.5:14b on Ollama, on an M4 Pro laptop with 24 GB. The notes are synthetic, written by a language model
        from labelled events.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function WriteTheRuleOnceFigure() {
  const dots = SPREAD[0].runs.filter((v): v is number => v !== null);
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Twelve functions written by a model for the same question score from 0 to 0.93; a SQL parser gets 10 of 12 query schemas right">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        RUN
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        rules written by a model · Q1 F1
      </text>
      <line x1="20" x2="500" y1="90" y2="90" stroke="var(--rule)" />
      {dots.map((v, i) => (
        <circle key={i} cx={20 + v * 480} cy={90 - (dots.slice(0, i).filter((d) => d === v).length * 9)} r="6" fill="#C98A16" />
      ))}
      <text x="20" y="114" fontSize="12" fill="var(--ink-mute)" fontFamily="var(--f-mono)">0</text>
      <text x="500" y="114" textAnchor="end" fontSize="12" fill="var(--ink-mute)" fontFamily="var(--f-mono)">1</text>
      <text x="20" y="160" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        Same request, different examples: 0 to 0.93
      </text>
      <text x="20" y="188" fontSize="15" fill="var(--ok)" fontFamily="var(--f-body)" fontWeight="600">
        Query schema: parser 10/12, models 8/12 and 5/12
      </text>
    </svg>
  );
}
