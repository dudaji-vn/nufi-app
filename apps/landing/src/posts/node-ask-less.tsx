import { PostByline } from '../components/blog/post-context';
// Engineering · Semantic data · part 8. The node demo after part 7: the semantic filter's judgements fixed by asking
// the model one fixed question, charts the user can edit, a database table as a source through Debezium (CDC), and a
// self-test on eight written tasks driven through the page. qwen2.5 7B on Ollama, DuckDB 2.0, PostgreSQL 18,
// Debezium 3.4.3 and Kafka 4.4 in Docker, on an M4 Pro laptop (24 GB). One run per number unless the text says three.

const C = { ok: 'var(--ok)', coral: 'var(--coral)', amber: '#C98A16', ink: 'var(--ink)', mute: 'var(--ink-mute)', rule: 'var(--rule)' };
const body = 'var(--f-body)';
const mono = 'var(--f-mono)';

function Shot({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return (
    <figure>
      <img src={src} alt={alt} loading="lazy" />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

// ---- F1 of the semantic filter, before and after, on three note sets ----
const SETS = [
  { name: 'story notes (40)', tag: 'used to tune', before: 0.731, after: 1.0 },
  { name: 'known wording (200)', tag: 'held out', before: 0.802, after: 1.0 },
  { name: 'new wording (200)', tag: 'held out', before: 0.781, after: 0.999 },
];

function F1Chart() {
  const x0 = 210, w = 420;
  return (
    <svg viewBox="0 0 720 270" role="img" aria-label="F1 of the semantic filter over 11 questions. Story notes: 0.731 before, 1.000 after. Known wording: 0.802 before, 1.000 after. New wording: 0.781 before, 0.999 after">
      {SETS.map((s, i) => {
        const y = 20 + i * 76;
        return (
          <g key={s.name}>
            <text x="0" y={y + 20} fontSize="14" fill={C.ink} fontFamily={body} fontWeight="700">
              {s.name}
            </text>
            <text x="0" y={y + 40} fontSize="12" fill={C.mute} fontFamily={body}>
              {s.tag}
            </text>
            <rect x={x0} y={y} width={s.before * w} height="24" rx="3" fill={C.amber} />
            <text x={x0 + s.before * w + 8} y={y + 17} fontSize="13" fill={C.ink} fontFamily={mono}>
              {s.before.toFixed(3)} before
            </text>
            <rect x={x0} y={y + 30} width={s.after * w} height="24" rx="3" fill={C.ok} />
            <text x={x0 + s.after * w + 8} y={y + 47} fontSize="13" fill={C.ink} fontFamily={mono}>
              {s.after.toFixed(3)}
            </text>
          </g>
        );
      })}
      <text x="0" y="258" fontSize="12" fill={C.mute} fontFamily={body}>
        F1 over 11 questions per set, scored against the labels each note was written from; qwen2.5 7B
      </text>
    </svg>
  );
}

export function NodeAskLessBody() {
  return (
    <>
      <p className="eyebrow">Engineering · Semantic data</p>
      <h1>Ask the model one question: a semantic filter at F1 1.000, a database as a node source, and a self-test</h1>
      <p className="standfirst">
        Part 7 ended on the miss no rule check could catch: the semantic filter judged notes wrongly. The fix was to ask
        the model less. A rule now settles which part and which action a question is about, and the model answers one
        fixed question per note. On 400 notes it had never been tuned on, F1 went from about 0.8 to 1.000, with 9 times
        fewer calls. We also let the user edit the chart, fed the graph from a database through Debezium, and tried the
        whole demo on eight written tasks.
      </p>
      <PostByline />

      <p>
        In <a href="/blog/node-tested-rule-checks-feldera">part 7</a> the model wrote the right SQL for the note
        questions, but <code>sem_filter</code>, the function that asks the model about each note, still got the answer
        wrong: it found 2 of 3 chiller problems and 2 of 3 RF generator problems, and the question "replaced" returned 18
        notes instead of one. A wrong judgement inside right SQL is the hardest miss to see, so it came first.
      </p>

      <h2>01 · Test the judgements on their own</h2>
      <p>
        Scoring through SQL mixes two things: the query and the judgements. So we scored <code>sem_filter</code> alone:
        11 questions, worded the way the model writes them in its SQL ("reports a problem with the chiller",
        "replaced", "a part was only inspected or cleaned and nothing was wrong"), each compared with the labels the notes
        were written from. Three sets of notes: the demo's 40 notes to tune on, and the 200 notes from{' '}
        <a href="/blog/semantic-operators-rule-or-model">part 2</a> twice, in known wording and in new wording that
        avoids the rule's symptom words. The 400 were held out: no wording was tried on them. The questions were fixed
        before the change.
      </p>
      <p>
        Before the change, only pump questions had a rule. Every other question sent every note to the model as written.
        F1 was 0.73 to 0.80. "A problem with a pump", which had the rule, scored 1.000. On the held-out sets, chiller
        questions scored 0.46–0.48 and robot questions 0.17–0.37. "Any problem" missed 36 to 40 notes in 200, and
        "replaced" said yes to 57–73 notes where nothing was replaced.
      </p>
      <p>
        On the 40 tuning notes the mistakes were of two kinds. The model mixed up parts: a turbo pump note counted as a
        dry pump problem. And it missed a symptom when the action sounded mild: "robot inspected after wafer
        misplacement", "TV position error, cleaned". Asked "does the note report a problem?", it missed 4 of 17
        problems. Asked the reverse, "does the note say that nothing was wrong, or that a symptom was looked for and not
        found?", it missed none. We tried five wordings on those 40 notes and kept the reverse one.
      </p>

      <h2>02 · Rules for what a rule can see, one question for the rest</h2>
      <p>
        Part 2 found that a rule is exact on names and the model is needed only for meaning. Now every question is split
        that way. A rule reads three things from the question: the part it names ("a pump", "the chiller"; "any part"
        names none), the action it names ("replaced", "inspected or cleaned"), and whether a problem must be present or
        absent. A note that names another part or another action is ruled out without the model. Only "was anything
        wrong?" goes to the model, always as the same reverse question. So one answer per note serves every question,
        and a question about a replacement needs no model at all. A question the rule cannot read still goes to the
        model as written.
      </p>
      <figure>
        <F1Chart />
        <figcaption>
          The rule settles the part and the action; the model answers one fixed question per note. The one miss left:
          a robot called "the wafer handler", a name the part rule does not know.
        </figcaption>
      </figure>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>11 questions</th>
              <th>model calls</th>
              <th>time</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>story notes (40), before → after</td>
              <td>365 → 40</td>
              <td>68 → 7 s</td>
            </tr>
            <tr>
              <td>known wording (200)</td>
              <td>1,822 → 200</td>
              <td>326 → 35 s</td>
            </tr>
            <tr>
              <td>new wording (200)</td>
              <td>1,822 → 200</td>
              <td>335 → 37 s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Through SQL, on part 7's 84 intents, the score went from 60 to 64 exact (68 to 72 match). Five note intents went
        from wrong to right. One went from right to wrong, and not because of a judgement: the model wrote{' '}
        <code>A AND B OR C</code> without brackets, and that had only come out right by luck before.
      </p>

      <h2>03 · A chart you can edit</h2>
      <p>
        The chart was the one projection a user could not change: a rule picked it, and the user could only pin it.
        Now the user picks the mark (line, bar, point or area), x, y and colour from the node's own columns. The choice
        is kept inside the chart's Vega-Lite spec, so nothing else in the node had to change. When the SQL changes, the
        chart is rebuilt from the choice. If a column it used is gone, the rule's chart comes back and the log says which
        column. A choice that does not fit (a text column as y) is refused, and nothing changes.
      </p>
      <Shot
        src="/blog/semantic-data/node-chart-edit.png"
        alt="The anomalies node: its chart drawn by the user as points coloured by chamber, with the mark, x, y and colour choices under it"
        caption="The chart says who drew it: here the user. Under it, the four choices and a button to give the chart back to the rule."
      />
      <p>
        Checking it in a browser showed an older bug in every chart: the y axis labels and the legend were cut off.
        The chart was laid out before its rows arrived and never measured again. One setting fixed it (Vega-Lite's{' '}
        <code>autosize</code> with <code>resize</code>).
      </p>

      <h2>04 · A database table as a node source</h2>
      <p>
        The graph's sources were sensor readings and maintenance notes. Limits are different: people edit them, in a
        database. So the limits now live in PostgreSQL, and Debezium reads the database's change log (change data
        capture). Debezium writes every insert, update and delete to a Kafka topic. The demo keeps its own copy of the
        table equal to the database, and a new node, <code>over_limit</code>, joins the minute averages with the
        current limits.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>From the database's commit to the node graph</th>
              <th>Debezium's defaults</th>
              <th>tuned</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>commit → visible in the graph (20 updates, median)</td>
              <td>777 ms</td>
              <td>
                <strong>267 ms</strong> (168–379)
              </td>
            </tr>
            <tr>
              <td>of which commit → Kafka (Debezium)</td>
              <td>540 ms</td>
              <td>82 ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Two settings made the difference. Debezium waits 500 ms between reads of the change log by default; we set 100
        ms. And the demo applied changes on its once-a-second tick. Limits change rarely, so it now looks every 100 ms
        and refreshes the graph only when something came. After a snapshot of 18 rows, inserts, updates, deletes and a
        change of a row's key, the copy equalled the table, row for row, and again after a restart (it rebuilds from
        the topic). Lowering one limit from 1500 to 1450 took <code>over_limit</code> from 65 to 81 rows.
      </p>
      <Shot
        src="/blog/semantic-data/node-cdc-limits.png"
        alt="The over_limit node after a limit was lowered to 1450 in the database: 81 rows, and the top bar saying the last change arrived 0.2 s after its commit"
        caption="One UPDATE in psql: 0.2 s later the node shows 81 minutes above the new limit. The limit column is traced to the database's table."
      />

      <h2>05 · A self-test on eight written tasks</h2>
      <p>
        Every part of the demo had been measured, but never the whole on fixed tasks. We wrote eight tasks, each with
        the check that says it is done, and committed them before the run. For example: find the first alert; add a step
        from words; change a threshold and keep the description true; break a step, see what breaks, undo it. A script
        did the tasks through the page in a headless browser, as a person would. It clicked buttons found by their
        text, typed into fields, read every answer from the page, and counted each action.
      </p>
      <p>
        All eight passed in three runs, in 29 actions. The longest task was adding a step from words: 5.8 s, of which
        the model took 4.1 s. The run found one real friction. After a broken step was put back exactly as it was, the
        description stayed marked as out of date, with the model's rewording waiting for "Accept" or "Keep mine". The
        description had been true all along. The graph now remembers which code each description was last true for, so
        an undo needs no model. Two things are noted, not fixed: a table shows only its newest 200 rows, so the first
        minute of a large node cannot be reached, and there is no undo button.
      </p>

      <h2>06 · What we take from it</h2>
      <ul>
        <li>
          <strong>Score the model's judgements on their own,</strong> on notes written before you change anything.
          Through SQL, a wrong judgement hides inside a right query.
        </li>
        <li>
          <strong>Ask the model the smallest question, the same way every time.</strong> Rules took the part and the
          action; one fixed question per note took F1 to 1.000 and cut the calls by 9 times.
        </li>
        <li>
          <strong>The way you word a question matters.</strong> "Nothing was wrong?" found every problem; "is there a
          problem?" missed problems after a mild action.
        </li>
        <li>
          <strong>Try the whole product on written tasks,</strong> even with a script. Our parts were all tested; the
          friction was between them.
        </li>
      </ul>

      <h2>Limits</h2>
      <p>
        The notes were written from a fixed list of part names, actions and a style rule, and the new wording changed
        only the symptom words. Real notes will name parts in ways the rule does not know; such a note is then missed,
        not counted wrongly. The reverse question relies on a note saying that nothing was wrong. The CDC path is one
        table on one laptop, so the database and the demo share a clock. The self-test script knows where every button
        is: it measures the length of each path and the system's speed, not how long a new person takes.
      </p>
    </>
  );
}

// The "Latest" slot figure.
export function NodeAskLessFigure() {
  const bars = [
    { label: 'asked as written', v: 0.781, c: 'var(--ink-mute)' },
    { label: 'rule + one question', v: 0.999, c: 'var(--ok)' },
  ];
  return (
    <svg viewBox="0 0 520 210" role="img" aria-label="F1 of the semantic filter on 200 held-out notes in new wording: 0.781 when every question is asked as written, 0.999 with the rule and one fixed question">
      <rect x="0" y="0" width="92" height="22" rx="5" fill="var(--brand)" />
      <text x="46" y="15" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ground)" fontFamily="var(--f-mono)">
        ASK LESS
      </text>
      <text x="104" y="15" fontSize="13" fill="var(--ink-mute)" fontFamily="var(--f-body)">
        F1, 200 held-out notes (7B)
      </text>
      {bars.map((b, i) => (
        <g key={b.label}>
          <text x="10" y={68 + i * 50} fontSize="13" fill="var(--ink)" fontFamily="var(--f-body)">
            {b.label}
          </text>
          <rect x="160" y={52 + i * 50} width={b.v * 280} height="24" rx="3" fill={b.c} />
          <text x={168 + b.v * 280} y={69 + i * 50} fontSize="13" fill="var(--ink)" fontFamily="var(--f-mono)">
            {b.v.toFixed(3)}
          </text>
        </g>
      ))}
      <text x="10" y="180" fontSize="14" fill="var(--ink)" fontFamily="var(--f-body)" fontWeight="600">
        Rules settle part and action; the model answers one question
      </text>
    </svg>
  );
}
