// The narration for the weekly report. English, matching the previous weeks.
//
// Written to answer two questions a customer asks in order: what can this do,
// and how would we set it up. An earlier cut answered neither -- it flashed
// four answers and moved on.
export const WEEK = {
  title: {
    eyebrow: 'NUFI APP · WEEK OF 25–31 AUGUST 2026',
    head: 'Ten department agents, built and running',
    sub: ['One per team the product introduction names, plus the routines any team shares.',
          'Every answer in this recording is produced live, on the box, while filming.'],
  },
  premise: {
    eyebrow: 'THE SETTING',
    head: 'A department buys one box.',
    sub: ['A shared drive holds the team&rsquo;s documents. The model runs on the same machine.',
          'Nothing in the next eight minutes reaches a cloud &mdash; that is the whole point of the box.'],
  },
  drive: ['Eight departments, eight shares.',
          'The folder a laptop mounts is the folder these agents read from.'],

  // The link the earlier cut never drew: a routine clicked in the box's own
  // console is served by a flow built in Studio. The answer's shape proves it.
  link: {
    eyebrow: 'THE PART THAT JOINS THEM',
    head: 'The box and Studio are one path, not two products.',
    sub: ['A member never opens Studio. They open the box&rsquo;s console and press <b>Run</b> on a routine.',
          'That routine reaches a flow you built &mdash; through an adapter that maps one to the other.'],
  },
  linkChain: ['Member &rarr; box console &rarr; adapter &rarr; Studio flow &rarr; on-box model.',
              'The adapter is 300 lines and lives in nufi-app. It is the whole of the integration between the two products.'],
  linkRun: ['The console confirms it ran &mdash; and stops there.',
            'It reports the routine and the status, and never shows what came back. A member pressing Run learns only that something happened.'],
  linkOutput: ['Here is what it actually produced, read from the API.',
               'Three parts: 위험 여부, 근거 조항, 조치 &mdash; the Legal flow&rsquo;s own shape. Nobody opened Studio to get this. The routine a department clicks <em>is</em> the flow you watched being built.'],
  linkHonest: ['And here is what is not finished.',
               'The box sends the routine&rsquo;s <em>name</em> and nothing else, so a flow needing material asks for it. Handing a routine its meeting or its folder is the next piece of work, and it belongs to the box, not the model.'],

  setupCard: {
    eyebrow: 'SETUP',
    head: 'Three things, and only one of them is configuration.',
    sub: ['<b>1.</b> Open Studio on the box. <b>2.</b> Point one field at the box&rsquo;s own model.',
          '<b>3.</b> Open a scenario and run it.',
          'There is no cloud account to create, no key to paste, and no per-seat licence to count.'],
  },
  flowList: ['Ten flows, shipped ready to open.',
             'Each is small enough to read in a minute and open enough to change. Nothing is locked.'],
  wiring: ['This is the only setup step: the address of your own model.',
           'Ollama API URL points at the box. Model name is whatever the box runs. That field is the difference between an on-prem agent and a cloud one.'],
  reproduce: {
    eyebrow: 'REPRODUCIBLE',
    head: 'The ten are built by a script, not by hand.',
    sub: ['<code>build_flows.py</code> creates them through Studio&rsquo;s own API; <code>run_flows.py</code> runs all ten and prints what each returned.',
          'Change a department&rsquo;s instructions, re-run, and you have your own version of this in a minute.'],
  },

  legal: {
    head: 'Legal &middot; risky clause review',
    anatomy1: ['Four components, and you can read the whole thing.',
               'A question comes in on the left. The department&rsquo;s review guide sits underneath it. The model is in the middle. The answer leaves on the right.'],
    anatomy2: ['The guide is the only thing this agent may judge against.',
               'It is not general legal knowledge — it is your team&rsquo;s standard, pasted in. Change the standard, and the agent changes with it.'],
    ask: ['Now the question a lawyer would actually type.',
          'Two clauses from a draft: one with no cap on damages, one with a five-year non-compete.'],
    run: ['Both caught, each against the article that forbids it.',
          '제6조 lists unlimited liability as report-on-sight; 제3조 requires approval when there is no cap. It also says what to do about them.'],
  },
  hr: {
    head: 'HR &middot; leave entitlement',
    anatomy1: ['Six components this time. The two extra ones are the whole point.',
               'A calculator sits below the model, and both feed the agent in the middle — one as its brain, one as its tool.'],
    anatomy2: ['The agent decides; the tool computes.',
               'The system prompt tells it the rule and forbids it the arithmetic. It has to reach for the calculator to answer at all.'],
    why: ['Why go to that trouble for one number?',
          'Because asked to work it out alone, this model answers 20. The rule gives 16. At temperature zero it answers 20 every single time — confidently, and wrong.'],
    run: ['16 days — and the CALCULATOR lines above it are how.',
          'The agent read three years out of the question, built the expression, called the tool four times, and reported what came back. None of that number was guessed.'],
    lesson: ['Retrieval grounds finding. It does not ground reasoning.',
             'Anything that must be computed — entitlements, prorations, deadlines, totals — belongs in a tool. That is a rule worth taking to every department.'],
  },
  strategy: {
    head: 'Corporate Strategy &middot; meeting notes to decisions',
    ask: ['Meeting notes, pasted in raw.',
          'Three things were discussed. Two got an owner and a date. The third did not.'],
    run: ['Two rows filled, one marked 미지정.',
          'The notes never assigned the budget review, so it says so. A summariser that fills that cell to look complete is worse than no summariser.'],
  },
  support: {
    head: 'Customer Support &middot; ticket triage',
    ask: ['Three tickets, arriving the way they really do.',
          'A whole box down, a drive not showing, and someone asking for bigger text.'],
    run: ['Three grades, each citing the rule it came from.',
          'P1 at 30 minutes, P2 at four hours, P4 at three working days. A disagreement is now about the standard, not about the model.'],
  },
  finance: {
    head: 'Finance &middot; duplicate payment check',
    ask: ['Five payments, and one rule.',
          'Same supplier, same amount, twice inside thirty days.'],
    run: ['One suspect named, and only one.',
          '대한물산 twice at 120만원, sixteen days apart. 서울테크 also repeats — but fifty-two days apart, so it is left alone. The rule was applied, not approximated.'],
  },

  coverage: {
    eyebrow: 'THE OTHER FIVE',
    head: 'Every team in the introduction, and the routines they share.',
    sub: ['<b>General Affairs</b> notice drafting &nbsp;·&nbsp; <b>Sales</b> RFP to a requirement checklist &nbsp;·&nbsp; <b>Engineering</b> incident to root cause',
          '<b>Any team</b> morning inbox summary &nbsp;·&nbsp; <b>Any team</b> document classification',
          'All ten run clean, and run_flows.py prints what each returned so the claim can be checked.'],
  },
  refuses: {
    eyebrow: 'WHAT THESE DELIBERATELY DO NOT DO',
    head: 'Two things we cut rather than show working.',
    sub: ['<b>PII masking by prompt.</b> Asked to mask a Korean document, it left an email address untouched and dropped an account number. That belongs to the guardrail layer, which already carries Korean detectors, because Presidio finds nothing on a 주민등록번호.',
          '<b>Answering past the material.</b> Every prompt names what the agent may use and tells it to say so when the answer is not there. That is why you saw 미지정 and 조건부 rather than a confident guess.'],
  },
  fixes: {
    eyebrow: 'ALSO THIS WEEK',
    head: 'Three things that were broken, and are not now.',
    sub: ['The RAG adapter could not reach the real retriever at all &mdash; it called a route that answers 405.',
          'Chat drifted out of Korean two runs in three; its decoding had never been pinned. Both are fixed.',
          'Six adapter test suites had never once run in CI. They now run on every push.'],
  },
  close: {
    eyebrow: 'STATE OF PLAY',
    head: 'Ten scenarios, ten clean runs.',
    sub: ['Built through Studio&rsquo;s own API, so each opens as a flow a person can edit.',
          'Thirty-two department checks pass alongside them, and two runs differ in none of the answers.',
          'Documented at docs.app.nufi.me/docs/studio/department-scenarios.'],
  },
};
