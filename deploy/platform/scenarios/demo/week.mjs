// The narration for the weekly report. English, matching the previous weeks.
export const WEEK = {
  title: {
    eyebrow: 'NUFI APP · WEEK OF 25–31 AUGUST 2026',
    head: 'Ten department agents, built and running',
    sub: ['One per team the product introduction names, plus the routines any team shares.',
          'Every answer in this recording is live, produced on the box while filming.'],
  },
  premise: {
    eyebrow: 'THE SETTING',
    head: 'A department buys one box.',
    sub: ['A shared drive holds the team&rsquo;s documents; the AI runs on the same machine.',
          'That is the premise these scenarios are built for &mdash; nothing here reaches a cloud.'],
  },
  drive: ['Eight departments, eight shares.',
          'The folder a laptop mounts is the folder the agents read from.'],
  legal: {
    head: 'Scenario 1 — Legal · auto-review of risky clauses',
    canvas: ['Four components: the question, the department&rsquo;s review guide, the on-box model, the answer.',
             'The guide is the only thing the agent is allowed to judge against.'],
    run: ['Both clauses caught, each against the article that forbids it.',
          'Unlimited liability and a five-year non-compete &mdash; 제6조 and 제3조, with the action to take.'],
  },
  hr: {
    head: 'Scenario 2 — HR · leave entitlement, computed by a tool',
    canvas: ['Six components — and the two on the right are the point.',
             'A calculator is handed to the agent as a tool. The model is told not to do the arithmetic itself.'],
    run: ['16 days — and the model did not work that out.',
          'Asked to compute it alone, this same model answers 20 every time. The agent read the years from the question, called the tool, and reported what came back.'],
  },
  strategy: {
    head: 'Scenario 4 — Corporate Strategy · meeting to decisions and owners',
    run: ['Three decisions, two with an owner and a date.',
          'The third had neither in the notes, so it says 미지정 rather than inventing one.'],
  },
  support: {
    head: 'Scenario 7 — Customer Support · ticket triage',
    run: ['Three tickets, three priorities, each citing the rule it used.',
          'A whole box down is P1 at 30 minutes; a font-size request is P4 at three working days.'],
  },
  coverage: {
    eyebrow: 'WHAT THE TEN COVER',
    head: 'Every department in the introduction, and the routines they share.',
    sub: ['법무 · 인사 · 총무 · 전략기획 · 재무 · 영업 · 고객지원 · 개발',
          'Clause review · leave calculation · notice drafting · meeting minutes · duplicate payments ·',
          'RFP checklists · ticket triage · incident postmortems · morning inbox · document classification'],
  },
  fixes: {
    eyebrow: 'ALSO THIS WEEK',
    head: 'Three things that were broken, and are not now.',
    sub: ['The RAG adapter could not talk to the real retriever at all &mdash; it called a route that answers 405.',
          'Chat drifted out of Korean two runs in three; its decoding was never pinned. Both now are.',
          'Six adapter suites had never once run in CI. They run on every push.'],
  },
  close: {
    eyebrow: 'STATE OF PLAY',
    head: 'Ten scenarios, ten clean runs.',
    sub: ['Built through Studio&rsquo;s own API, so each one opens as a flow a person can edit.',
          'Thirty-two department checks pass alongside them, and two runs differ in none of the answers.'],
  },
};
