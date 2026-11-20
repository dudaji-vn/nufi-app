import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 2. LOTUS (arXiv 2407.11418) run, Palimpzest (arXiv 2405.14696) read.
// Every number is from our run on an M4 Pro laptop (24 GB): 200 synthetic maintenance notes, LOTUS 1.2.4,
// qwen2.5 7B / 14B and llama3.2 3B on Ollama, temperature 0, one run per configuration.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const mono = 'var(--f-mono)';

// ---- Q1 F1 on both note sets ----
function WordingChart() {
  const rows = [
    { name: 'keyword rule', known: 1.0, fresh: 0.0, calls: '0 calls' },
    { name: 'qwen2.5 7B via LOTUS', known: 0.903, fresh: 0.911, calls: '200 calls' },
    { name: 'rule + 7B, split', known: null, fresh: 1.0, calls: '74 calls' },
  ];
  const x0 = 200, w = 400;
  return (
    <svg viewBox="0 0 720 270" role="img" aria-label="F1 for question 1, a pump problem. Keyword rule: 1.000 on known wording, 0.000 on new wording. qwen2.5 7B through LOTUS: 0.903 on known wording, 0.911 on new wording, 200 model calls. The rule picking the part and the 7B model judging the symptom: 1.000 on new wording with 74 model calls">
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <line x1={x0 + t * w} x2={x0 + t * w} y1="20" y2="220" stroke={C.rule} strokeWidth="1" />
          <text x={x0 + t * w} y="238" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={mono}>
            {t.toFixed(1)}
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = 30 + i * 66;
        return (
          <g key={r.name}>
            <text x={x0 - 12} y={y + 18} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
              {r.name}
            </text>
            <text x={x0 - 12} y={y + 36} textAnchor="end" fontSize="11" fill={C.mute} fontFamily={body}>
              {r.calls} on new wording
            </text>
            {r.known !== null && (
              <>
                <rect x={x0} y={y} width={Math.max(r.known * w, 2)} height="18" fill={C.rule} />
                <text x={x0 + r.known * w + 6} y={y + 14} fontSize="11" fill={C.mute} fontFamily={mono}>
                  {r.known.toFixed(3)} known
                </text>
              </>
            )}
            <rect x={x0} y={y + 22} width={Math.max(r.fresh * w, 2)} height="18" fill={r.fresh === 0 ? C.coral : C.ok} />
            <text x={x0 + r.fresh * w + 6} y={y + 36} fontSize="11" fill={r.fresh === 0 ? C.coral : C.ink} fontFamily={mono} fontWeight="700">
              {r.fresh.toFixed(3)} new
            </text>
          </g>
        );
      })}
      <text x="0" y="262" fontSize="12" fill={C.mute} fontFamily={body}>
        Q1 F1: does the note report a problem with a pump? 51 of 200 notes do · grey: known wording, colour: new wording
      </text>
    </svg>
  );
}

// ---- Q3 with and without the glossary ----
function GlossaryChart() {
  const rows = [
    { name: '7B, no glossary', v: 1.0 },
    { name: '7B, glossary', v: 0.868 },
    { name: '14B, glossary', v: 0.231 },
    { name: '3B, glossary', v: 0.103 },
  ];
  const x0 = 150, w = 420;
  return (
    <svg viewBox="0 0 720 220" role="img" aria-label="F1 for question 3, was a part replaced, on known wording. qwen2.5 7B without the glossary: 1.000. qwen2.5 7B with the glossary: 0.868. qwen2.5 14B with the glossary: 0.231. llama3.2 3B with the glossary: 0.103">
      {rows.map((r, i) => {
        const y = 14 + i * 42;
        return (
          <g key={r.name}>
            <text x={x0 - 12} y={y + 18} textAnchor="end" fontSize="13" fill={C.ink} fontFamily={body}>
              {r.name}
            </text>
            <rect x={x0} y={y + 4} width={r.v * w} height="20" fill={i === 0 ? C.ok : C.amber} />
            <text x={x0 + r.v * w + 6} y={y + 19} fontSize="12" fill={C.ink} fontFamily={mono} fontWeight="700">
              {r.v.toFixed(3)}
            </text>
          </g>
        );
      })}
      <text x="0" y="200" fontSize="12" fill={C.mute} fontFamily={body}>
        Q3 F1: was a part replaced? Known wording, 33 of 200 notes · the rule scores 1.000
      </text>
    </svg>
  );
}

// ---- the split plan ----
function SplitDiagram() {
  const boxes = [
    { x: 0, title: '200 notes', sub: 'free text', c: C.rule },
    { x: 180, title: 'Rule: which part?', sub: 'names, codes · 0 calls', c: C.ok },
    { x: 380, title: '74 pump notes', sub: '126 ruled out: "no"', c: C.rule },
    { x: 560, title: 'Model: symptom?', sub: 'sem_filter · 74 calls', c: C.amber },
  ];
  return (
    <svg viewBox="0 0 720 150" role="img" aria-label="The split plan: 200 notes go to the rule, which picks the part from names and codes with no model calls; 126 notes are not about a pump and get no; the 74 pump notes go to the model, which only judges whether a symptom was present, in 74 calls. Result: 51 of 51 pump problems found, no false alarms">
      {boxes.map((b, i) => (
        <g key={b.title}>
          <rect x={b.x} y="20" width="150" height="62" rx="8" fill="none" stroke={b.c} strokeWidth="2" />
          <text x={b.x + 75} y="46" textAnchor="middle" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="700">
            {b.title}
          </text>
          <text x={b.x + 75} y="66" textAnchor="middle" fontSize="11" fill={C.mute} fontFamily={body}>
            {b.sub}
          </text>
          {i < boxes.length - 1 && (
            <text x={b.x + 165} y="57" textAnchor="middle" fontSize="18" fill={C.ok}>
              →
            </text>
          )}
        </g>
      ))}
      <text x="0" y="118" fontSize="13" fill={C.ink} fontFamily={body} fontWeight="600">
        New wording: 51 of 51 pump problems found, 0 false alarms — F1 1.000 with 63 % fewer model calls
      </text>
      <text x="0" y="140" fontSize="11" fill={C.mute} fontFamily={body}>
        qwen2.5 7B, one run · 157 s instead of 385 s for the model alone
      </text>
    </svg>
  );
}

export function SemanticOperatorsBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>A keyword rule or a language model? Semantic operators on 200 maintenance notes</h1>
      <p className="standfirst">
        Semantic operators let you filter and map a table with a condition written in plain words. We ran LOTUS with
        local models on synthetic maintenance notes, against a keyword rule. The rule was perfect until the wording
        changed, then it found none of the pump problems. The model got most of it right. The best result came from splitting the question:
        the rule answers what it can, and the model gets only the part that needs meaning.
      </p>
      <PostByline />

      <p>
        In the <a href="/blog/flowco-one-node-many-levels">first post</a> of this series we ended on one rule: where an
        algorithm can replace the language model, it should. This post tests that rule on a concrete task. Engineers
        type notes like <em>"ETCH-06/D DP bearing noise, inspected"</em> into a maintenance log. We want to ask the log
        questions in plain words, the way a database answers SQL.
      </p>

      <h2>01 · What a semantic operator is</h2>
      <p>
        A relational operator whose condition is a sentence, evaluated by a language model. <strong>LOTUS</strong>{' '}
        (Stanford and UC Berkeley; arXiv 2407.11418) adds them to pandas. <code>sem_filter</code> keeps the rows for
        which a sentence holds, and <code>sem_map</code> writes a new column from an instruction. There are also{' '}
        <code>sem_join</code>, <code>sem_agg</code> and <code>sem_topk</code>. The sentence names columns in braces:
      </p>
      <pre>
        <code>{`df.sem_filter("{note} reports a problem with a pump (a dry pump or a turbo pump).")
df.sem_map("Which part is {note} about? Answer with exactly one of: dry pump, turbo pump, ...")`}</code>
      </pre>
      <p>
        Each operator has a "gold" algorithm: in the simplest case, one model call per row. Each also has optimizations
        that keep a stated accuracy. The main one is a <em>cascade</em>: a cheap proxy answers first, and only the rows
        it is unsure about go to the large model. Targets for recall and precision, and a probability of missing them,
        decide where the proxy stops. The paper reports up to 1,000× faster than its own gold algorithm on one benchmark.
      </p>
      <p>
        <strong>Palimpzest</strong> (MIT and others; arXiv 2405.14696) takes the declarative road. The user writes a pipeline of
        schemas and operators, and an optimizer chooses a plan for each operator, trading run time, cost and quality.
        A plan can use a smaller model, or code that a model writes once and that then runs in place of model
        calls. We read Palimpzest but did not run it; we ran
        LOTUS.
      </p>

      <h2>02 · The test</h2>
      <ul>
        <li>
          <strong>200 labelled events.</strong> Seeded maintenance events on 12 tools: one of six parts (dry pump,
          turbo pump, chiller, RF generator, robot, throttle valve), a fault or none, a symptom, an action.
        </li>
        <li>
          <strong>Notes in four styles.</strong> A language model wrote one note of at most 22 words per event. The
          styles are plain, shorthand ("DP", "TMP", "TV"), negation (a check that found nothing, written as "no
          bearing noise and no current rise") and indirect (a fault described only by what was seen). The labels stay
          with the events, so every answer is scored.
        </li>
        <li>
          <strong>Two sets of the same 200 events.</strong> <em>Known wording</em> uses ordinary words. <em>New
          wording</em> bans every symptom word the rule knows, so the notes say "above spec", "grinding sound from its
          bearings", "sparking" or "speed was falling" instead.
        </li>
        <li>
          <strong>Three questions.</strong> Q1 (<code>sem_filter</code>): does the note report a problem with a pump?
          51 notes do. Q2 (<code>sem_map</code>): which part is it about? Q3 (<code>sem_filter</code>): was a part
          replaced? 33 notes do.
        </li>
        <li>
          <strong>The algorithm.</strong> A keyword rule built from a glossary: part names and their abbreviations, a
          list of symptom words, and negation handled clause by clause.
        </li>
        <li>
          <strong>The models.</strong> LOTUS 1.2.4 with qwen2.5 7B and 14B and llama3.2 3B, local on Ollama, at
          temperature 0, with the cache off. In some runs the same glossary the rule uses was put in front of the
          question. Each configuration ran once.
        </li>
      </ul>

      <h2>03 · On its own words, the rule wins</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Known wording</th>
              <th>Q1 F1</th>
              <th>Q2 accuracy</th>
              <th>Q3 F1</th>
              <th>Time, 3 questions</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>keyword rule</td>
              <td>1.000</td>
              <td>1.000</td>
              <td>1.000</td>
              <td>0.01 s</td>
            </tr>
            <tr>
              <td>qwen2.5 7B, no glossary</td>
              <td>0.786</td>
              <td>0.945</td>
              <td>1.000</td>
              <td>250 s</td>
            </tr>
            <tr>
              <td>qwen2.5 7B, glossary</td>
              <td>0.903</td>
              <td>1.000</td>
              <td>0.868</td>
              <td>971 s</td>
            </tr>
            <tr>
              <td>qwen2.5 14B, glossary</td>
              <td>0.804</td>
              <td>1.000</td>
              <td>0.231</td>
              <td>1,804 s</td>
            </tr>
            <tr>
              <td>llama3.2 3B, glossary</td>
              <td>0.038</td>
              <td>0.810</td>
              <td>0.103</td>
              <td>310 s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        This is not a fair fight. The rule's symptom list covers exactly the symptoms in this data set, which is why we
        made the second set. Still, the model results show three things.
      </p>
      <p>
        <strong>Without the glossary, the model does not know the abbreviations.</strong> qwen2.5 7B without the
        glossary got every plain, negation and indirect note right on Q1, but only 46 of 64 shorthand notes. It does not
        know that "DP" is a dry pump.
      </p>
      <p>
        <strong>The glossary fixes Q1 and breaks Q3.</strong> The glossary explains when a note "reports a problem".
        Put in front of "was a part replaced?", it makes the model say yes to notes that say only <em>cleaned</em>,{' '}
        <em>adjusted</em> or <em>inspected</em>, like "ETCH-06/A EFEM robot wafer misplacement, cleaned." In this
        run the bigger model did worse, not better.
      </p>
      <figure>
        <GlossaryChart />
        <figcaption>
          The same glossary, in front of a question it was not written for. Context belongs to one question, not to
          the whole pipeline.
        </figcaption>
      </figure>
      <p>
        <strong>llama3.2 3B was not usable as a filter here.</strong> It found 1 of 51 pump problems.
      </p>

      <h2>04 · New wording: the rule finds nothing</h2>
      <p>
        On the second set, the rule's Q1 finds 0 of 51 pump problems: no symptom word matches "above spec" or
        "grinding sound".
        Its Q2 (0.995) and Q3 (1.000) still work, because part names and "replaced" did not change. For the model we
        used what the first set taught us: qwen2.5 7B, with the glossary for Q1 and Q2 but not for Q3. (We had planned
        the full model matrix on this set too, but the laptop ran short of memory; only this configuration ran.)
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>New wording</th>
              <th>Q1 F1</th>
              <th>Q2 accuracy</th>
              <th>Q3 F1</th>
              <th>Q1 time</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>keyword rule</td>
              <td>0.000</td>
              <td>0.995</td>
              <td>1.000</td>
              <td>&lt; 0.01 s (all three)</td>
            </tr>
            <tr>
              <td>qwen2.5 7B</td>
              <td>0.911</td>
              <td>1.000</td>
              <td>1.000</td>
              <td>385 s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        The model found all 51 problems, and raised 10 false alarms. The 10 false alarms have one thing in common: all
        of them are about parts that are <em>not</em> pumps. Nine are real faults; the tenth is an RF generator check
        that found nothing.
      </p>
      <blockquote>
        <p>"ETCH-04/B RF gen: sparking observed; cleaned RF gen."</p>
        <p>"ETCH-07/A TV: pressure swinging up and down, TV adjusted."</p>
        <p>"ETCH-03/B chiller replaced; coolant circulation was under spec."</p>
      </blockquote>
      <p>
        Q1 asks two things at once: <em>is it a pump?</em> and <em>is something wrong?</em> In nine of the ten, the
        model answered the second and lost track of the first. On its own, it answers the first one perfectly: its Q2 accuracy is 1.000.
      </p>

      <h2>05 · Split the question</h2>
      <p>
        So we split it. The rule answers "which part?" from names and codes. It costs nothing and never forgets. Notes
        that are not about a pump get "no" without a model call. The model gets a different question, about the symptom
        alone ("…reports a symptom that was present"), and only for the 74 notes the rule says are about a pump. The
        rule missed none.
      </p>
      <figure>
        <SplitDiagram />
        <figcaption>
          Measured on the new wording with qwen2.5 7B: 74 model calls, 157 s and 22,724 tokens, against 200 calls and
          385 s for the model alone. One run.
        </figcaption>
      </figure>
      <figure>
        <WordingChart />
        <figcaption>
          The rule alone is perfect on its own words and useless on new ones. The model alone is good on both. The two
          together are perfect on the new words, with 126 fewer model calls.
        </figcaption>
      </figure>
      <p>
        Palimpzest's optimizer is designed to make this kind of choice per operator, and LOTUS's cascades make a
        similar one between a cheap proxy and a large model. Here we made it by hand, for one
        question. A platform would have to make it for every question a user types.
      </p>

      <h2>06 · What this means for a data platform</h2>
      <ul>
        <li>
          <strong>Split each question.</strong> Names, codes, units, dates and words like <em>replaced</em> go to an
          algorithm or plain SQL. Only "is this reading a symptom?" goes to a model, and only for the rows the
          algorithm has not ruled out.
        </li>
        <li>
          <strong>Give context per question.</strong> A glossary that defines "problem" belongs to the problem question.
          The same text in front of every question made one answer much worse.
        </li>
        <li>
          <strong>Measure on wording you did not write the rule for.</strong> On its own words, the rule looked
          perfect. Real logs are not written in the rule's words.
        </li>
        <li>
          <strong>Count the calls.</strong> Here, one model call per row took 4–30 minutes for 600 calls on a laptop.
          At a fab's log volume, rows that never reach the model are what make the feature affordable.
        </li>
      </ul>
      <p>
        Next in this series: how far an algorithm can go on its own. Compiling semantic operators into code, and
        reading what a SQL query means from its parse tree, before any model is asked.
      </p>

      <p className="foot-note">
        Sources: L. Patel, S. Jha, M. Pan, H. Gupta, P. Asawa, C. Guestrin, M. Zaharia, "Semantic Operators: A
        Declarative Model for Rich, AI-based Data Processing", arXiv 2407.11418 (v3); C. Liu, M. Russo et al., "A
        Declarative System for Optimizing AI Workloads" (Palimpzest), arXiv 2405.14696 (v2).
        Our run: LOTUS 1.2.4 (lotus-ai on PyPI), Ollama with qwen2.5:7b, qwen2.5:14b and llama3.2:3b, one run per
        configuration on an M4 Pro laptop with 24 GB. The notes are synthetic, written by a language model from
        labelled events.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function SemanticOperatorsFigure() {
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="Question 1 F1 on new wording: keyword rule 0.000, qwen2.5 7B 0.911 with 200 calls, rule and model split 1.000 with 74 calls">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        RUN
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        200 notes, new wording · Q1 F1
      </text>
      {[
        { n: 'rule', v: 0.0, s: '0 calls', c: 'var(--coral)' },
        { n: 'model', v: 0.911, s: '200 calls', c: '#C98A16' },
        { n: 'split', v: 1.0, s: '74 calls', c: 'var(--ok)' },
      ].map((r, i) => (
        <g key={r.n}>
          <text x="70" y={66 + i * 46} textAnchor="end" fontSize="15" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="700">
            {r.n}
          </text>
          <rect x="82" y={50 + i * 46} width={Math.max(r.v * 300, 3)} height="22" fill={r.c} />
          <text x={90 + Math.max(r.v * 300, 3)} y={66 + i * 46} fontSize="13" fill="var(--ink)" fontFamily="var(--f-mono)">
            {r.v.toFixed(3)} · {r.s}
          </text>
        </g>
      ))}
    </svg>
  );
}
