// Records the weekly report about the box: one command, then a department's
// drive becomes its agent's knowledge.
//
//   node box.mjs --lang en --out box-en.webm --box ../../../box
//   node box.mjs --lang ko --out box-ko.webm --box ../../../box
//
// Same discipline as record.mjs and record-week.mjs: nothing is captioned that
// has not been read back off the live box first. Every URL in the installer's
// banner is asked during the recording; the file copied into the drive is
// stat'ed after it is written; the ingest line is grepped out of the daemon's
// own log rather than assumed; each answer is read out of the message list; the
// console and Studio are checked for a login form before either is called
// "already signed in"; and the 8/32/10 in the closing card is recomputed from
// evidence/box.json instead of typed. Any of those failing aborts the run.
//
// Where a claim can genuinely go either way the script carries both captions and
// the recorder picks after reading -- the Legal question that leaks its tool
// call, the question about the file just dropped on the drive, and a Studio that
// may or may not have flows in it. That is not hedging: a cut about the
// mechanism has to be able to film the mechanism working while the model fails,
// which is exactly what this box does today. Nothing is re-rolled to get a
// nicer take; where a question is asked more than once the retries are counted
// on screen and the caption says how many there were.
//
// The box's secrets never reach the frame. The admin password is read from .env
// to log in and is never rendered, and the installer's real banner is not filmed
// at all -- `install-box.sh --dry-run` prints every secret it would write, so
// the banner here is the README's, with its four URLs asked live to prove it.
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, statSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { BOX } from './box-script.mjs';
import { styles, THEME } from './stage.mjs';

const arg = (n, d) => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const LANG = arg('lang', 'en');
const OUT = arg('out', `box-${LANG}.webm`);
const BOX_DIR = resolve(arg('box', '../../../box'));
const INGEST = arg('ingest', 'nufi-box-nufi-ingest-1');
const EVIDENCE = resolve(arg('evidence', '../evidence/box.json'));
const T = BOX[LANG];
if (!T) throw new Error(`no script for --lang ${LANG}`);

// ---- the box, as it describes itself ------------------------------------
const envPath = join(BOX_DIR, '.env');
if (!existsSync(envPath)) throw new Error(`no box .env at ${envPath} -- pass --box <dir>`);
const ENV = Object.fromEntries(readFileSync(envPath, 'utf8').split('\n')
  .filter((l) => l.includes('=') && !l.trimStart().startsWith('#'))
  .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
for (const k of ['BOX_HOST', 'BOX_IP', 'ADMIN_EMAIL', 'ADMIN_PASSWORD', 'NUFI_MODEL', 'NUFI_DATA_DIR',
  'STUDIO_API_KEY']) {
  if (!ENV[k]) throw new Error(`.env is missing ${k}`);
}
// ---- the score, from the acceptance run rather than from memory ---------
//
// Read here and not at the closing card, because three captions quote it and
// two of them play long before the card. The old version asserted the numbers
// it had been told to expect (`8/32/10`) and printed the card from a string;
// that is backwards -- a re-measured box would abort the recording instead of
// being reported. What is worth refusing is evidence that is not about the
// box being filmed, so that is what is checked: one model, and that model the
// one this box serves.
const EV = JSON.parse(readFileSync(EVIDENCE, 'utf8'));
const SCORE = {
  model: ENV.NUFI_MODEL,
  depts: EV.departments.length,
  qs: EV.departments.reduce((n, d) => n + d.questions.length, 0),
  passed: EV.departments.reduce((n, d) => n + d.questions.filter((q) => q.pass).length, 0),
};
SCORE.failed = SCORE.qs - SCORE.passed;
// Answers that left Korean mid-sentence. On this box that is eleven of
// thirty-two, and until now the recording had no line that said so: a viewer
// saw one Thai preamble on screen and no way to know whether it was a fluke.
SCORE.drift = EV.departments.reduce(
  (n, d) => n + d.questions.filter((q) => q.drifted).length, 0);
// The breadth card claims every citation that appeared named the file the
// answer came from, and every department ingested. Both are read off the
// evidence here rather than trusted, for the same reason the four URLs in the
// banner are asked live: a sentence on screen that nothing checks is a
// sentence that goes quietly false. A question that cites a file and still
// fails is the counterexample -- there was one, and it turned out to be the
// judge missing a refusal, not a bad citation.
const citedAndWrong = EV.departments
  .flatMap((d) => d.questions)
  .filter((q) => (q.sources || []).length && !q.pass);
if (citedAndWrong.length) {
  throw new Error(`${citedAndWrong.length} answer(s) cite a file and still fail, so the `
    + `breadth card cannot claim otherwise: ${citedAndWrong[0].ask}`);
}
const notIngested = EV.departments.filter((d) => !d.ingest_complete);
if (notIngested.length) {
  throw new Error(`${notIngested.map((d) => d.id).join(', ')} never finished ingesting, so `
    + 'the breadth card cannot say every department did');
}
if (!EV.models || EV.models.length !== 1) {
  throw new Error(`the evidence was measured across ${JSON.stringify(EV.models)}; `
    + 'a single score cannot describe more than one model');
}
if (EV.models[0] !== ENV.NUFI_MODEL) {
  throw new Error(`the evidence was measured on ${EV.models[0]}, but this box serves `
    + `${ENV.NUFI_MODEL} -- re-run run_box.py before recording`);
}

const HOST = ENV.BOX_HOST;
const NAME = ENV.BOX_NAME || HOST.replace(/\.local$/, '');
const CHAT = `https://${HOST}:3080`;
const CONSOLE = `https://${HOST}:3001`;
const LANDING = `http://${HOST}/`;

// The drive document this cut writes on camera, and takes back out afterwards.
// Deliberately a real department document in the same register as the rest of
// the corpus, and deliberately removed in the `finally` below: the daemon
// reconciles a deletion by dropping the file and its embedding server-side, so
// a recording leaves the Legal drive exactly as it found it and the next
// acceptance run measures the same corpus as the last one.
const DEMO_DOC = '계약검토_부속서_하도급.txt';
const DEMO_BODY = `계약 검토 표준 조항 부속서 — 하도급 (2026-09 시행)

제1조(적용) 본 부속서는 표준 조항 가이드 v3의 부속 문서로, 하도급 계약에 한하여 적용한다.

제2조(사전 검토) 하도급 계약은 착수 30일 전까지 법무팀 사전 검토를 받아야 한다.

제3조(재하도급) 재하도급은 원칙적으로 금지하며, 불가피한 경우 발주처의 서면 동의를 받아야 한다.

제4조(대금 지급) 하도급 대금은 검수 완료일로부터 15일 이내에 지급한다.
`;
const LEGAL_DRIVE = join(ENV.NUFI_DATA_DIR, 'drives', 'legal');
const DEMO_PATH = join(LEGAL_DRIVE, DEMO_DOC);
const DATA_MASK = '&lt;data dir&gt;';

// The Legal agent is found by name rather than pinned by id: the ids are minted
// by the ingest daemon on each box, so a hard-coded one would be right on this
// machine and wrong on every other.
const LEGAL_AGENT_NAME = /legal/i;
const Q1 = '자동연장 조항이 있는 계약은 만료 며칠 전까지 통보해야 하나요?';
const Q2 = 'NDA의 비밀유지 의무는 계약 종료 후 몇 년간 존속하나요?';
const Q3 = '하도급 대금은 검수 완료 후 며칠 이내에 지급하나요?';

const beat = (p, ms) => p.waitForTimeout(ms);
const nap = (ms) => new Promise((r) => { setTimeout(r, ms); });
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
/** Fills {n}/{max} in a caption with numbers the run actually counted. */
const fill = (lines, vars) =>
  lines.map((l) => l.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)));
const fillCard = (c, vars) => ({
  eyebrow: c.eyebrow,
  head: fill([c.head], vars)[0],
  sub: fill(c.sub || [], vars),
});

// ---- the presentation layer, from stage.mjs -----------------------------
//
// Two rules this cut needs on top of the shared look, kept here rather than in
// stage.mjs so the other two recordings are not touched:
//
//   - `code`. stage.mjs styles no inline code, so a <code> in a headline
//     inherits whatever the page underneath styles it as -- and the box's own
//     landing page gives it a white block, which swallowed the install command
//     whole. Every card here names a file or a command, so it needs its own.
//   - room at the bottom. The caption card floats over the lower ~200px, and
//     on a centred card that is exactly where the last line of a terminal
//     panel lands. Padding the stage lifts the card clear of it.
const EXTRA_CSS = `
  #stage{padding-bottom:180px}
  #stage code,#cap code{font-family:"IBM Plex Mono",monospace;font-size:.9em;
    background:rgba(124,107,245,.16);color:#C6BCFF;padding:2px 8px;border-radius:6px}
  #stage h1 code{font-size:.8em;padding:6px 14px}
`;

async function install(page) {
  await page.evaluate(([css]) => {
    if (document.getElementById('mbstyle')) return;
    const s = document.createElement('style');
    s.id = 'mbstyle'; s.textContent = css; document.head.appendChild(s);
    const stage = document.createElement('div'); stage.id = 'stage';
    const cap = document.createElement('div'); cap.id = 'cap';
    document.body.append(stage, cap);
  }, [styles(T.font) + EXTRA_CSS]);
}

async function card(page, { eyebrow, head, sub = [] }, hold = 6500) {
  await install(page);
  await page.evaluate(([e, h, s]) => {
    const el = document.getElementById('stage');
    el.innerHTML = (e ? `<div class="eyebrow">${e}</div>` : '')
      + `<h1>${h}</h1><div class="rule"></div>`
      + s.map((l) => `<p>${l}</p>`).join('');
    el.classList.add('on');
    document.getElementById('cap').classList.remove('on');
  }, [eyebrow || '', head, sub]);
  await beat(page, hold);
}

async function clearCard(page) {
  await page.evaluate(() => document.getElementById('stage')?.classList.remove('on'));
  await beat(page, 650);
}

async function say(page, lines, hold = 7000) {
  await install(page);
  await page.evaluate(([a, b]) => {
    const el = document.getElementById('cap');
    el.innerHTML = `<div class="l1"><b>${a}</b></div>` + (b ? `<div class="l2">${b}</div>` : '');
    el.classList.add('on');
  }, [lines[0], lines[1] || '']);
  await beat(page, hold);
}

const hush = (page) =>
  page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));

/** A terminal panel on the current card. Only ever fed text read off the box. */
async function terminal(page, lines, accent = 'accent') {
  await page.evaluate(([b, a, th]) => {
    const pre = document.createElement('pre');
    pre.style.cssText = `margin-top:26px;text-align:left;background:${th.panel};
      border:1px solid ${th.line};border-left:4px solid ${th[a]};border-radius:12px;
      padding:22px 30px;font:500 16px/1.75 "IBM Plex Mono",monospace;color:${th.ink};
      white-space:pre-wrap;max-width:1180px;overflow:hidden`;
    pre.innerHTML = b;
    document.getElementById('stage').appendChild(pre);
  }, [lines.join('\n'), accent, THEME]);
}

// ---- the checks ---------------------------------------------------------

/** Asks every URL the banner prints. A banner promising a dead URL is a lie.
 *
 * Through a scratch tab rather than `page.request`, and for one reason: the API
 * request context does its own DNS and would resolve the box's name through the
 * host, which is exactly the stale answer the browser is launched to bypass. A
 * tab in this context uses the browser's resolver, so these four rows are the
 * box's real name, reaching the box.
 */
async function probeBanner(ctx) {
  const scratch = await ctx.newPage();
  try {
    const rows = [];
    for (const [label, url] of [['Chat', `${CHAT}/login`], ['Console', `${CONSOLE}/`],
                                ['Admin panel', `https://${HOST}:3002/`], ['Certificate', LANDING]]) {
      const r = await scratch.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 })
        .catch(() => null);
      const code = r ? r.status() : 0;
      if (code < 200 || code >= 400) {
        throw new Error(`banner URL ${url} answered ${code || 'nothing'}`);
      }
      rows.push([label, url.replace(/\/(login)?$/, ''), code]);
    }
    return rows;
  } finally {
    await scratch.close();
  }
}

/** The last assistant turn, with the app's own chrome stripped off. */
async function lastAnswer(page, agentName) {
  const full = await page.locator('[data-testid="messages-view"]').innerText().catch(() => '');
  const i = full.lastIndexOf(agentName);
  if (i < 0) return '';
  return full.slice(i + agentName.length).replace(/NUFI v[\d.a-z-]+\s*$/i, '').trim();
}

/** The last answer as the box stored it, split into its parts.
 *
 * `lastAnswer` scrapes the message view, which is the right source for "has it
 * stopped growing" and the wrong one for "what did the model say": the
 * retrieved passage is rendered on screen too, so a citation card containing
 * the number and the file name satisfies any regex looking for the number and
 * the file name, whether or not the model ever wrote them. An earlier version
 * of this script only escaped that by gating the answer test behind `!leaked`,
 * which made "leaked" and "answered" mutually exclusive -- and this box does
 * both at once.
 *
 * So the verdict comes from the message the box persisted:
 *   - `prose`      the model's own text, minus any typed-out call
 *   - `typedCall`  a text part in which the model printed its tool call
 *   - `toolCalls`  calls it actually made
 * Same-origin fetch, and the session exchanged for a bearer first, for the
 * same reasons as the agent listing above.
 */
async function answerParts(page) {
  // The app rewrites the URL to /c/<id> once the conversation exists, which is
  // the cheapest place to get the id -- but if it has not yet, the newest
  // conversation on the account is this one, because the recording is the only
  // thing talking to this box. Falling back beats aborting a six-minute take
  // over a URL that had not caught up.
  const fromUrl = (page.url().match(/\/c\/([\w-]+)/) || [])[1];
  const msgs = await page.evaluate(async (hint) => {
    const rt = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' });
    if (!rt.ok) return { error: `refresh ${rt.status}` };
    const { token } = await rt.json();
    const auth = { Authorization: `Bearer ${token}` };
    let cid = hint && hint !== 'new' ? hint : null;
    if (!cid) {
      const c = await fetch('/api/convos?pageNumber=1', { headers: auth });
      if (!c.ok) return { error: `convos ${c.status}` };
      const body = await c.json();
      cid = (body.conversations || body.data || [])[0]?.conversationId;
      if (!cid) return { error: 'no conversation on the account' };
    }
    const r = await fetch(`/api/messages/${cid}`, { headers: auth });
    return r.ok ? r.json() : { error: `messages ${r.status}` };
  }, fromUrl);
  if (msgs.error) throw new Error(`could not read the answer back: ${msgs.error}`);
  const last = [...msgs].reverse().find((m) => !m.isCreatedByUser);
  if (!last) throw new Error('the conversation has no answer in it');
  const parts = last.content || [];
  const texts = parts.filter((x) => x.type === 'text').map((x) => x.text || '');
  const isCall = (t) => /file_search|tool_call|"arguments"/.test(t);
  return {
    prose: texts.filter((t) => !isCall(t)).join('\n').trim(),
    typedCall: texts.some(isCall),
    toolCalls: parts.filter((x) => x.type === 'tool_call').length,
  };
}

/** Opens a fresh conversation with one agent, ready for a question. */
async function openAgent(page, agentId) {
  await hush(page);
  await page.goto(`${CHAT}/c/new?endpoint=agents&agent_id=${agentId}`,
    { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="text-input"]', { timeout: 60000 });
  await beat(page, 1800);
  await install(page);
}

/** Sends one question and waits for the answer to stop growing.
 *
 * The composer's button keeps its test id while it is a stop button, so there
 * is no "done" flag to read; what there is, is the answer text, and the only
 * honest signal is that it has held still. Four identical reads at 1.5s is six
 * seconds of silence -- long enough that a model pausing between a tool call
 * and its prose is not mistaken for a finished answer, which is how an earlier
 * pass filmed an empty bubble.
 */
async function ask(page, agentName, question, { timeout = 300000 } = {}) {
  const t0 = Date.now();
  await page.locator('[data-testid="text-input"]').fill(question);
  await beat(page, 700);
  await page.locator('[data-testid="send-button"]').click();

  let seen = '';
  let still = 0;
  while (Date.now() - t0 < timeout) {
    await beat(page, 1500);
    const body = await lastAnswer(page, agentName);
    if (body && body === seen) { still += 1; if (still >= 4) break; } else still = 0;
    seen = body;
  }
  const seconds = (Date.now() - t0) / 1000;
  if (!seen) throw new Error(`no answer to "${question.slice(0, 40)}" in ${seconds.toFixed(0)}s`);
  if (/internal server error|502 bad gateway|failed to fetch/i.test(seen)) {
    throw new Error(`the app reported an error: ${seen.slice(0, 160)}`);
  }
  return { text: seen, seconds };
}

/** Waits for this file's line in the ingest daemon's own log.
 *
 * The window is measured from `since`, not from a fixed `--since 10m`: a
 * previous take of this same recording leaves an identical line in the log, and
 * a wider window happily matched it and reported the ingest as instant. The
 * line filmed has to be this run's.
 *
 * Sleeps on a timer rather than through the page: this is also called from the
 * cleanup, by which point the browser context is already closed, and it must
 * not stall the event loop while the card sits on screen either.
 */
async function ingestLine(name, since, { timeout = 180000, verb = 'added' } = {}) {
  const re = new RegExp(`${verb} .*${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`);
  while (Date.now() - since < timeout) {
    const sinceArg = `${Math.max(1, Math.ceil((Date.now() - since) / 1000))}s`;
    const log = execFileSync('docker', ['logs', '--since', sinceArg, INGEST],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    const hit = log.split('\n').reverse().find((l) => re.test(l));
    if (hit) return { line: hit.trim(), seconds: (Date.now() - since) / 1000 };
    await nap(3000);
  }
  return null;
}

// ---- the run ------------------------------------------------------------
async function main() {
  mkdirSync('recording', { recursive: true });

  // The box announces itself on the LAN with a background `dns-sd`, which
  // records the address the machine had at install time -- so after a new DHCP
  // lease the name resolves to a host that is no longer the box. Rather than
  // reconfigure a box this recording is only supposed to use, the browser is
  // told to resolve the box's own name to the address the box's own .env calls
  // itself. The name in the frame and the certificate behind it are both real.
  const browser = await chromium.launch({
    args: [`--host-resolver-rules=MAP ${HOST} ${ENV.BOX_IP}`],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 1,
    ignoreHTTPSErrors: true,
    recordVideo: { dir: 'recording', size: { width: 1600, height: 1000 } },
  });
  const page = await ctx.newPage();
  const t = THEME;

  try {
    // 1 -- title
    await page.goto(LANDING, { waitUntil: 'domcontentloaded' });
    await card(page, T.title, 7000);

    // 2 -- one command. The banner is the README's, verbatim, because the
    // installer's own prints the generated admin password; every URL in it is
    // asked live while the card is up.
    await card(page, T.install, 1200);
    const rows = await probeBanner(ctx);
    await terminal(page, [
      `  <span style="color:${t.accent2}">NuFi box "${esc(NAME)}" is up.</span>`,
      '',
      ...rows.map(([label, url, code]) =>
        `  ${esc(label.padEnd(14))}${esc(url)}   <span style="color:${t.ok}">${code} ok</span>`),
      `  ${esc('Admin login:'.padEnd(14))}${esc(ENV.ADMIN_EMAIL)} / &lt;generated password&gt;`,
      `  ${esc('Drives:'.padEnd(14))}${DATA_MASK}/drives/&lt;department&gt;`,
    ]);
    await beat(page, 2400);
    await say(page, T.installCap, 8000);
    await clearCard(page);

    // 3 -- the app, on the box's own name and certificate
    await page.goto(`${CHAT}/login`, { waitUntil: 'domcontentloaded' });
    await beat(page, 2200);
    await install(page);
    await say(page, T.login, 5500);
    await page.fill('input[name=email]', ENV.ADMIN_EMAIL);
    await page.fill('input[name=password]', ENV.ADMIN_PASSWORD);
    await page.click('button[type=submit]');
    await page.waitForURL(/\/c\//, { timeout: 90000, waitUntil: 'domcontentloaded' });
    await beat(page, 3500);
    // The account lands in Basic, and Basic's header carries no model badge --
    // the shot below reads one, and the take that tried it read the "Basic
    // interface enabled" banner instead and failed the whole cut. Same two keys
    // record-chat.mjs and the docs screenshots use, then a reload so the app
    // picks them up.
    await page.evaluate(() => {
      localStorage.setItem('uiMode', JSON.stringify('advanced'));
      localStorage.setItem('uiModeIntroSeen', 'true');
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await beat(page, 2600);
    await page.locator('#ui-mode-intro-dismiss').click({ timeout: 3000 }).catch(() => {});
    // Collapse the conversation list. Every take of this recording leaves four
    // more conversations in it, and a sidebar of the recorder's own leftovers
    // is noise in front of the thing being shown.
    await page.click('[data-testid="close-sidebar-button"]').catch(() => {});
    await beat(page, 1200);
    await install(page);

    // The model badge, read rather than asserted -- and waited for rather than
    // sampled once, because the header renders it a beat after the route does
    // and a missed read here fails a whole take for a screen that was fine.
    let shown = [];
    let badge = '';
    for (let i = 0; i < 20 && !badge; i += 1) {
      shown = (await page.locator('body').innerText().catch(() => '')).split('\n').map((s) => s.trim());
      badge = shown.find((s) => s.toLowerCase() === ENV.NUFI_MODEL.toLowerCase()) || '';
      if (!badge) await beat(page, 1500);
    }
    if (!badge) {
      throw new Error(`no "${ENV.NUFI_MODEL}" on the chat screen; saw ${shown.slice(0, 8).join(' | ')}`);
    }
    console.log(`model badge: ${badge}`);
    await say(page, fill(T.model, SCORE), 6800);
    await hush(page);

    // 4 -- the department's agent, on the drive as it was found
    //
    // Same-origin fetch from the page, for the same resolver reason as the
    // banner probe: `page.request` would look the box's name up on the host.
    // The app keeps its access token in memory and only the refresh token in a
    // cookie, so the session has to be exchanged for a bearer first -- a plain
    // cookie fetch of /api/agents answers 401.
    const list = await page.evaluate(async () => {
      const rt = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' });
      if (!rt.ok) return { error: `refresh ${rt.status}` };
      const { token } = await rt.json();
      const r = await fetch('/api/agents?limit=50', { headers: { Authorization: `Bearer ${token}` } });
      return r.ok ? r.json() : { error: `agents ${r.status}` };
    });
    if (list.error) throw new Error(`could not list the box's agents: ${list.error}`);
    const legal = (list.data || list.agents || []).find((a) => LEGAL_AGENT_NAME.test(a.name || ''));
    if (!legal) throw new Error('no Legal agent on this box');
    console.log(`legal agent: ${legal.id} (${legal.name})`);

    await openAgent(page, legal.id);
    await say(page, T.ask, 5500);
    const a1 = await ask(page, legal.name, Q1);
    console.log(`q1 (${a1.seconds.toFixed(1)}s): ${a1.text.replace(/\s+/g, ' ').slice(0, 140)}`);
    // The caption follows the screen, never the other way round -- and there
    // are three things the screen can show, not two. The model can print the
    // call instead of making it (nothing is retrieved, nothing is answered);
    // it can make the call and answer; or it can print the call *and* make it
    // *and* answer, which is what this box does on a 14B model and what the
    // old two-way verdict had no caption for.
    //
    // Each half of the verdict is read where its claim lives. The *number* has
    // to come out of the model's own prose -- the retrieved passage is on
    // screen too and contains it either way, so a screen-wide regex for "60"
    // proves nothing about the answer. The *file name* is the opposite: the
    // caption's claim is that it is printed above the answer, which is the
    // citation card, so the screen is exactly the right place to read it.
    const p1 = await answerParts(page);
    const answered = /60/.test(p1.prose) && /계약검토_표준조항/.test(a1.text);
    console.log(`q1 parts: typedCall=${p1.typedCall} toolCalls=${p1.toolCalls} answered=${answered}`);
    if (!answered && !p1.typedCall) {
      throw new Error(`q1 was neither a printed tool call nor a cited answer: ${a1.text.slice(0, 160)}`);
    }
    let q1Cap = fill(T.q1Drift, SCORE);
    if (answered) q1Cap = p1.typedCall ? T.q1AnsweredNoisy : T.q1Answered;
    await say(page, q1Cap, 9000);

    // 5 -- ...and one the same agent does answer, off the same drive.
    //
    // Up to three tries, because at the app's own temperature this model can
    // print its tool call instead of making it, and a cut that can only be
    // finished on a lucky first roll is a cut that gets re-run until it
    // flatters the box. Nothing changes between attempts, the retries are
    // counted on screen, and three failures get their own caption rather than
    // an abort: three questions answered with nothing but a printed call is a
    // thing this cut is willing to say out loud. Printing the call and then
    // making it anyway is not a failed try -- the answer is what decides.
    await openAgent(page, legal.id);
    await say(page, T.ask2, 5000);
    const tries = 3;
    let a2 = null;
    for (let n = 1; n <= tries; n += 1) {
      if (n > 1) {
        await say(page, fill(T.q2Retry, { n, max: tries, model: ENV.NUFI_MODEL }), 7000);
        await openAgent(page, legal.id);
      }
      const got = await ask(page, legal.name, Q2);
      const p2 = await answerParts(page);
      console.log(`q2/${n} (${got.seconds.toFixed(1)}s): typedCall=${p2.typedCall} `
        + `toolCalls=${p2.toolCalls} :: ${p2.prose.replace(/\s+/g, ' ').slice(0, 140)}`);
      if (/3년|3 years/.test(p2.prose) && /계약검토_표준조항/.test(got.text)) { a2 = got; break; }
      if (!p2.typedCall) {
        throw new Error(`q2 answered something this script cannot caption: ${p2.prose.slice(0, 160)}`);
      }
    }
    // The second half of the `q2` caption used to tell the viewer that the
    // previous question had this same page a tool call away and never made the
    // call. That is a claim about q1, and it is only true on a box where q1
    // failed -- so it is now its own caption, picked by what q1 actually did.
    await say(page, a2 ? (answered ? T.q2 : T.q2AfterDrift) : fill(T.q2Drift, { max: tries, model: ENV.NUFI_MODEL }), 9500);
    await hush(page);

    // 6 -- the drive, written on camera
    await card(page, T.drive, 4500);
    const wroteAt = Date.now();
    writeFileSync(DEMO_PATH, DEMO_BODY, 'utf8');
    const st = statSync(DEMO_PATH);
    const listing = execFileSync('ls', ['-1', LEGAL_DRIVE], { encoding: 'utf8' }).trim();
    if (!listing.includes(DEMO_DOC)) throw new Error('the document is not on the drive');
    await terminal(page, [
      `  <span style="color:${t.accent2}">$ cp ${esc(DEMO_DOC)} ${DATA_MASK}/drives/legal/</span>`,
      `  <span style="color:${t.accent2}">$ ls ${DATA_MASK}/drives/legal</span>`,
      '',
      ...listing.split('\n').map((l) => `  ${esc(l)}`),
      '',
      `  <span style="color:${t.dim}">${st.size} bytes on disk. Nothing else about the box was touched.</span>`,
    ]);
    await beat(page, 2000);
    await say(page, T.driveCap, 6800);

    // 7 -- the daemon, on its own clock. The card stays up for the wait: there
    // is nothing to watch on a folder, and the wait is itself the claim.
    await clearCard(page);
    await card(page, { eyebrow: T.drive.eyebrow, head: T.drive.head }, 900);
    await say(page, T.waiting, 900);
    const added = await ingestLine(DEMO_DOC, wroteAt, { verb: 'added' });
    if (!added) throw new Error('the daemon never logged this file as added');
    if (!/embedded=True/.test(added.line)) {
      throw new Error(`the daemon logged it, but not as embedded: ${added.line}`);
    }
    console.log(`ingest (${added.seconds.toFixed(0)}s): ${added.line}`);
    await hush(page);
    await terminal(page, [
      `  <span style="color:${t.accent2}">$ nufi-box logs nufi-ingest</span>`,
      '',
      `  ${esc(added.line)}`,
      '',
      `  <span style="color:${t.dim}">${added.seconds.toFixed(0)} s after the file landed on the drive.</span>`,
    ], 'ok');
    await beat(page, 2200);
    await say(page, T.ingested, 8000);
    await clearCard(page);

    // 8 -- a question only the new file can answer.
    //
    // Two tries, and both outcomes have a caption written for them: on this box
    // a second document on one drive is not free, and the honest version of
    // this shot is the one that can film that.
    await openAgent(page, legal.id);
    await say(page, T.askNew, 6000);
    let a3 = null;
    for (let n = 1; n <= 2 && !a3; n += 1) {
      if (n > 1) await openAgent(page, legal.id);
      const got = await ask(page, legal.name, Q3);
      const p3 = await answerParts(page);
      console.log(`q3/${n} (${got.seconds.toFixed(1)}s): typedCall=${p3.typedCall} `
        + `toolCalls=${p3.toolCalls} :: ${p3.prose.replace(/\s+/g, ' ').slice(0, 140)}`);
      // The claim is the name above the answer, so the name is read off the
      // screen; the prose only has to be an answer rather than a printed call.
      if (/부속서_하도급/.test(got.text) && p3.prose.length > 20) a3 = got;
    }
    await say(page, a3 ? T.newCited : T.newDrift, 9500);
    await hush(page);

    // 9 -- one login, four products
    await card(page, T.sso, 5500);
    await clearCard(page);
    await page.click('[data-testid="nav-user"]');
    await beat(page, 1600);
    // The menu opens the console in a second tab, and Playwright records one
    // video per page -- a tab the recording cannot see is a shot that does not
    // exist. So the tab is opened for real, allowed to finish its single
    // sign-on (which is what puts the console's session cookie in this
    // context), checked for a login form, and then closed; the URL it was given
    // by the app's own menu is what the recorded page then goes to.
    const opened = ctx.waitForEvent('page', { timeout: 30000 }).catch(() => null);
    await page.getByRole('menuitem', { name: /console|콘솔/i }).click();
    const tab = await opened;
    if (!tab) throw new Error('the account menu did not open the console');
    // domcontentloaded, not the default `load`: these pages pull a web font
    // from the internet, and on a box that cannot reach it the load event never
    // fires and the recording dies on a page that is perfectly usable.
    await tab.waitForLoadState('domcontentloaded').catch(() => {});
    await beat(tab, 4500);
    const consoleUrl = tab.url();
    const consoleAsked = await tab.locator('input[type=password]').count();
    await tab.close();
    if (!new RegExp(`${HOST.replace('.', '\\.')}:3001`).test(consoleUrl)) {
      throw new Error(`the account menu opened ${consoleUrl}, not the console`);
    }
    if (consoleAsked) {
      throw new Error('the console asked for a password -- that is not one login');
    }
    await page.goto(consoleUrl, { waitUntil: 'domcontentloaded' });
    await beat(page, 3000);
    await install(page);
    await say(page, T.console, 6500);

    await page.goto(`${CONSOLE}/choose`, { waitUntil: 'domcontentloaded' });
    await beat(page, 3200);
    const chooseText = await page.locator('body').innerText();
    if (!/already signed in|이미 로그인/i.test(chooseText)) {
      throw new Error(`the console did not say it was already signed in: ${chooseText.slice(0, 120)}`);
    }
    await install(page);
    await say(page, T.choose, 6500);
    await hush(page);

    // 10 -- Studio, on the same session
    await page.click('a[href="/enter/studio"]');
    await page.waitForURL(new RegExp(`${HOST.replace('.', '\\.')}:7860`),
      { timeout: 90000, waitUntil: 'domcontentloaded' });
    // Studio spends a few seconds on "Loading…" after the redirect, and how
    // many depends on the box. Waiting on the screen rather than on a fixed
    // beat -- an earlier take aborted here for reading a spinner, which is the
    // check doing its job but a poor reason to lose a recording.
    // Both empty-state wordings, because Studio has had two of them, plus
    // the sidebar's own labels. This decides only *when the page has
    // finished loading*; what is on it is counted, not read.
    const ready = /create first flow|첫 플로우|start building|my projects|starter project|flows/i;
    let studioText = '';
    for (let i = 0; i < 40; i += 1) {
      studioText = await page.locator('body').innerText().catch(() => '');
      if (ready.test(studioText)) break;
      await beat(page, 1500);
    }
    await beat(page, 2500);
    if (await page.locator('input[type=password]').count()) {
      throw new Error('Studio asked for a password -- single sign-on did not carry');
    }
    if (!ready.test(studioText)) {
      throw new Error(`Studio never finished loading: ${studioText.slice(0, 140)}`);
    }

    // How many flows this canvas has is a number, not a phrase. It used to be
    // read by looking for Studio's empty-state copy ("Create first flow"), and
    // when that copy changed to "Start building" the test matched neither
    // branch and fell through to "flows present" -- so the cut captioned a
    // canvas that plainly said Start building as having the department flows
    // already there. A check whose unknown answer is the flattering one is not
    // a check.
    //
    // Two counts, because they caption differently. `mine` is what the signed-
    // in member can list, which is what the viewer is looking at. `onBox` is
    // what the box holds under its superuser, read with the API key from .env
    // (never rendered) -- a member seeing none of the routines the box does
    // have is a different story from a box that has none.
    // `headers: {}` is not decoration: Studio wraps window.fetch and its
    // interceptor writes Accept-Language into whatever headers object it is
    // given, so a call without one dies inside the app's own bundle.
    const mine = await page.evaluate(async () => {
      const r = await fetch('/api/v1/flows/?get_all=true&header_flows=true',
        { credentials: 'include', headers: {} });
      if (!r.ok) return { error: `flows ${r.status}` };
      const body = await r.json();
      const list = (Array.isArray(body) ? body : (body.flows || body.items || []))
        .filter((f) => !f.is_component);
      // Studio's sidebar lists flows *by project*, and opens on the default
      // one. A flow with no folder is returned by this endpoint and rendered
      // nowhere, so counting rows would caption an empty canvas as full --
      // which is exactly the bug this shot uncovered. Count what is listable.
      return { count: list.filter((f) => f.folder_id).length, rows: list.length };
    });
    if (mine.error) throw new Error(`could not list this member's flows: ${mine.error}`);
    const onBox = JSON.parse(execFileSync('curl', ['-sk', '-H', `x-api-key: ${ENV.STUDIO_API_KEY}`,
      '-H', 'User-Agent: Mozilla/5.0',
      `https://${HOST}:7860/api/v1/flows/?get_all=true&header_flows=true`],
      { encoding: 'utf8' })).filter((f) => !f.is_component).length;
    console.log(`studio: ${mine.count} flow(s) in this member's projects `
      + `(${mine.rows} row(s) owned), ${onBox} on the box`);
    await install(page);
    let studioCap = T.studioEmpty;
    if (mine.count > 0) studioCap = T.studioFlows;
    else if (onBox > 0) studioCap = fill(T.studioNotMine, { onBox, rows: mine.rows });
    await say(page, studioCap, 9000);
    await hush(page);

    // 11 -- what it scores, printed from the evidence rather than typed
    console.log(`evidence: ${SCORE.depts} departments, ${SCORE.qs} questions, `
      + `${SCORE.passed} passed, on ${EV.models[0]} (${EV.started})`);
    await card(page, fillCard(T.breadth, SCORE), 10500);

    // 12 -- what is next
    await card(page, T.close, 8000);

    const video = page.video();
    await ctx.close();
    await video.saveAs(OUT);
    console.log(`wrote ${OUT}`);
  } finally {
    // Put the drive back the way it was found, and wait for the daemon to
    // agree: it deletes the server-side file and its embedding on the next
    // scan, so the corpus the acceptance run measures is unchanged.
    if (existsSync(DEMO_PATH)) {
      const removedAt = Date.now();
      rmSync(DEMO_PATH, { force: true });
      const gone = await ingestLine(DEMO_DOC, removedAt, { verb: 'removed', timeout: 120000 })
        .catch(() => null);
      console.log(gone ? `cleanup: ${gone.line}` : 'cleanup: the daemon has not logged the removal yet');
    }
    await browser.close();
  }
}

main().catch((e) => { console.error(String(e.message || e)); process.exit(1); });
