// Records the NuFi box introduction: what the box is, the one-command install,
// the folder-is-the-interface idea answered live with a citation, the Studio
// routines, and reaching the box from home over the mesh. Filmed against a
// real box (the acceptance VM, on the live coordinator) in the format the
// weekly recordings set: 1600×1000, dark cards between shots, a floating
// caption over the footage, English.
//
// Two disciplines inherited from the other recorders:
//   1. Nothing is captioned that has not been read back. The citation caption
//      only goes up once the reply on screen actually contains the file name.
//   2. The terminal cards show real command output (box.mjs TERMINAL), captured
//      from this box — not typed for the film.
//
//   BOX_ADMIN_EMAIL=… BOX_ADMIN_PASSWORD=… STUDIO_PASSWORD=… \
//     node record-box.mjs --base https://192.168.64.2 --studio https://192.168.64.2:7860 --out box.webm
//   ffmpeg -i box.webm -c:v libx264 -pix_fmt yuv420p -crf 22 -movflags +faststart box-intro.mp4
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { styles, THEME } from './stage.mjs';
import { BOX, TERMINAL } from './box.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > -1 ? process.argv[i + 1] : d; };
const has = (n) => process.argv.includes(`--${n}`);

// The box serves its SPA only for its own hostnames (Caddy has no site for a
// bare IP), so the film addresses it by name and maps that name to the box's
// address at the browser, the way a laptop on the LAN resolves it over mDNS.
const HOST = arg('host', 'nufi.local');                       // the box's LAN name
const ADDR = arg('addr', '192.168.64.2');                     // where that name lives
const BASE = arg('base', `https://${HOST}`);
const STUDIO = arg('studio', `${BASE}:7860`);
const OUT = arg('out', 'box.webm');
const EMAIL = process.env.BOX_ADMIN_EMAIL;
const PASSWORD = process.env.BOX_ADMIN_PASSWORD;
const STUDIO_PASSWORD = process.env.STUDIO_PASSWORD || PASSWORD;
if (!EMAIL || !PASSWORD) { console.error('Set BOX_ADMIN_EMAIL and BOX_ADMIN_PASSWORD.'); process.exit(1); }

const SCENES = ['title', 'install', 'ask', 'studio', 'mesh', 'close'];
const FROM = SCENES.indexOf(arg('from', 'title'));
const runs = (s) => SCENES.indexOf(s) >= FROM;
// The detailed cut adds scenes (what-you-get, the drive filling, a second and
// a third question, the per-department wall, day two, and the honest edges).
// The default is the two-minute intro.
const DETAIL = has('detail');

const FONT = '"IBM Plex Sans","Helvetica Neue",Arial,sans-serif';
const ASK = 'Under our standard NDA, which law governs the agreement and where are disputes resolved?';
const CITE_TOKENS = [/NDA/i, /Vietnam/i];   // what the reply must contain before the citation caption
// The detailed cut's extra questions, each with what its reply must contain
// before the film captions it (so a wrong or empty answer stops the recording).
const ASK_TERM = 'How long does the standard NDA stay in effect?';
const ASK_TERM_TOKENS = [/three|3\b/i, /year/i];
const ASK_ABSENT = 'What is our parental leave entitlement?';
const ASK_ABSENT_TOKENS = [/not|does not|no\b/i];   // it must decline, not answer
const ASK_HR = 'How many days of annual leave do employees get, and does it change with length of service?';
const ASK_HR_TOKENS = [/15/, /18/];

const beat = (p, ms) => p.waitForTimeout(ms);
let current = null;

// ---- overlay: cards, captions, cursor, and a terminal panel ----------------
const OVERLAY_CSS = `${styles(FONT)}
  #cur{position:fixed;left:-40px;top:-40px;width:22px;height:22px;border-radius:50%;
    background:rgba(124,107,245,.6);border:2px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.35);
    transform:translate(-50%,-50%) scale(1);pointer-events:none;z-index:2147483590;opacity:0;
    transition:opacity .25s ease,transform .12s ease}
  #cur.on{opacity:1}
  #cur.press{transform:translate(-50%,-50%) scale(.7)}
  #term{width:min(1120px,84vw);text-align:left;background:#0E0C1C;border:1px solid ${THEME.line};
    border-radius:14px;box-shadow:0 30px 80px rgba(0,0,0,.5);overflow:hidden;margin-top:6px}
  #term .bar{display:flex;gap:8px;padding:14px 18px;border-bottom:1px solid ${THEME.line};background:#141127}
  #term .bar i{width:12px;height:12px;border-radius:50%;display:inline-block}
  #term pre{margin:0;padding:22px 26px;font:15px/1.85 "IBM Plex Mono",ui-monospace,monospace;
    white-space:pre-wrap;word-break:break-word}
  #term .prompt::before{content:"$ ";color:${THEME.accent2}}
  #term .prompt{color:${THEME.ink}}
  #term .out{color:#CFCBE6}
  #term .dim{color:${THEME.dim}}
  #term .ok{color:${THEME.ok}}
  #term .accent{color:${THEME.accent2}}
`;

function overlayInit({ css }) {
  const build = () => {
    if (document.getElementById('nfstyle') || !document.body) return;
    const s = document.createElement('style'); s.id = 'nfstyle'; s.textContent = css;
    document.head.appendChild(s);
    const stage = document.createElement('div'); stage.id = 'stage';
    const cap = document.createElement('div'); cap.id = 'cap';
    const cur = document.createElement('div'); cur.id = 'cur';
    document.body.append(stage, cap, cur);
    document.addEventListener('mousemove', (e) => {
      cur.style.left = `${e.clientX}px`; cur.style.top = `${e.clientY}px`; cur.classList.add('on');
    }, true);
    let held = ''; try { held = sessionStorage.getItem('nf.card') || ''; } catch {}
    if (held) {
      stage.classList.add('instant'); stage.innerHTML = held; stage.classList.add('on');
      requestAnimationFrame(() => requestAnimationFrame(() => stage.classList.remove('instant')));
    }
  };
  if (document.body) build(); else document.addEventListener('DOMContentLoaded', build);
  window.__nfInstall = build;
}
const install = (page) => page.evaluate(() => window.__nfInstall?.());

async function go(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 })
    .catch(() => page.goto(url, { waitUntil: 'commit', timeout: 90000 }));
}

function cardHTML({ eyebrow, head, sub = [], extra = '' }) {
  return (eyebrow ? `<div class="eyebrow">${eyebrow}</div>` : '')
    + `<h1>${head}</h1><div class="rule"></div>` + sub.map((l) => `<p>${l}</p>`).join('') + extra;
}
async function card(page, spec, hold = 6500) {
  await install(page);
  await page.evaluate((html) => {
    const el = document.getElementById('stage');
    el.innerHTML = html; el.classList.add('on');
    document.getElementById('cap').classList.remove('on');
    try { sessionStorage.setItem('nf.card', html); } catch {}
  }, cardHTML(spec));
  await beat(page, hold);
}

// A card whose body is a terminal panel with real command output, revealed
// line by line so the eye reads it.
async function terminalCard(page, spec, lines, { step = 260, hold = 3800 } = {}) {
  const rows = lines.map(([k, t]) =>
    k === 'blank' ? '<span> </span>' : `<span class="${k}">${t.replace(/</g, '&lt;')}</span>`).join('\n');
  const term = `<div id="term"><div class="bar"><i style="background:#FF5F57"></i>`
    + `<i style="background:#FEBC2E"></i><i style="background:#28C840"></i></div>`
    + `<pre id="termpre"></pre></div>`;
  await card(page, { ...spec, extra: term }, 900);
  // type the rows in
  for (let i = 0; i < lines.length; i++) {
    await page.evaluate((html) => { document.getElementById('termpre').innerHTML = html; },
      rows.split('\n').slice(0, i + 1).join('\n'));
    await beat(page, step);
  }
  await beat(page, hold);
}

async function clearCard(page) {
  await page.evaluate(() => {
    document.getElementById('stage')?.classList.remove('on');
    try { sessionStorage.removeItem('nf.card'); } catch {}
  });
  await beat(page, 650);
}

async function say(page, lines, hold = 6000) {
  await install(page);
  await page.evaluate(([a, b]) => {
    const el = document.getElementById('cap');
    el.innerHTML = `<div class="l1"><b>${a}</b></div>` + (b ? `<div class="l2">${b}</div>` : '');
    el.classList.add('on');
  }, [lines[0], lines[1] || '']);
  await beat(page, hold);
}
const hush = (page) => page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));

// ---- motion ----------------------------------------------------------------
const cursor = { x: 800, y: 520 };
async function glide(page, target, { steps = 24, hold = 120 } = {}) {
  const box = await target.boundingBox();
  if (!box) throw new Error('glide: target has no box');
  const to = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const from = { ...cursor };
  for (let i = 1; i <= steps; i++) {
    const e = 1 - Math.pow(1 - i / steps, 3);
    await page.mouse.move(from.x + (to.x - from.x) * e, from.y + (to.y - from.y) * e);
    await beat(page, 11);
  }
  cursor.x = to.x; cursor.y = to.y; await beat(page, hold); return to;
}
async function tap(page, target, opts = {}) {
  await target.waitFor({ state: 'visible', timeout: opts.timeout ?? 15000 });
  await glide(page, target, opts);
  await page.evaluate(() => document.getElementById('cur')?.classList.add('press'));
  await page.mouse.down(); await beat(page, 90); await page.mouse.up();
  await page.evaluate(() => document.getElementById('cur')?.classList.remove('press'));
  await beat(page, opts.after ?? 350);
}
async function type(page, text, delay = 26) { await page.keyboard.type(text, { delay }); await beat(page, 400); }

// ---- chat helpers ----------------------------------------------------------
const composer = (page) => page.locator('#text-input, textarea[aria-label="Message input"]').first();
const prose = (page) => page.locator('.markdown.prose');
async function replyTexts(page, question) {
  const all = await prose(page).allInnerTexts().catch(() => []);
  return all.map((t) => t.trim()).filter((t) => t && t !== question.trim());
}
async function waitReply(page, question, { timeout = 240000 } = {}) {
  const t0 = Date.now(); let seen = ''; let stableSince = 0;
  while (Date.now() - t0 < timeout) {
    const texts = await replyTexts(page, question);
    const txt = texts.length ? texts.slice(-1)[0] : '';
    if (/too many requests|something went wrong|an error occurred|internal server error/i.test(txt)) {
      throw new Error(`reply errored on screen: ${txt.slice(0, 160)}`);
    }
    if (txt) {
      if (txt === seen) { if (!stableSince) stableSince = Date.now(); else if (Date.now() - stableSince > 3000) return txt; }
      else { seen = txt; stableSince = 0; }
    }
    await beat(page, 500);
  }
  throw new Error('no reply appeared');
}

// Type a question to the agent already selected, wait for the reply, and check
// it contains what the caption is about to claim. Returns the reply text.
async function askAndVerify(page, question, tokens) {
  await tap(page, composer(page));
  await type(page, question);
  await page.keyboard.press('Enter');
  await beat(page, 600);
  const reply = await waitReply(page, question);
  for (const rx of tokens) {
    if (!rx.test(reply)) throw new Error(`refusing to film: reply to "${question.slice(0, 40)}…" did not match ${rx}`);
  }
  return reply;
}

// Select one department agent from the model picker (My Agents → <name>).
async function pickAgent(page, nameRx) {
  await tap(page, page.locator('button').filter({ hasText: /qwen|nufi|assistant/i }).first(), { after: 700 });
  await tap(page, page.getByText(/my agents/i).first(), { after: 700 });
  await tap(page, page.getByText(nameRx).first(), { after: 900 });
  await beat(page, 600);
}

// ---- the film --------------------------------------------------------------
async function main() {
  mkdirSync('recording', { recursive: true });
  const browser = await chromium.launch({
    args: [`--host-resolver-rules=MAP ${HOST} ${ADDR}, MAP ${HOST}:7860 ${ADDR}`],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1,
    ignoreHTTPSErrors: true,   // the box uses its own certificate authority
    recordVideo: { dir: 'recording', size: { width: 1600, height: 1000 } },
  });
  await ctx.addInitScript(overlayInit, { css: OVERLAY_CSS });
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  current = page;

  // --- sign in behind the title card --------------------------------------
  await go(page, `${BASE}:3080/login`);
  if (runs('title')) await card(page, BOX.title, 7000);
  const email = page.locator('input[type="email"], input[name="email"], #email').first();
  await email.waitFor({ state: 'visible', timeout: 40000 });
  await email.fill(EMAIL);
  await page.locator('input[type="password"], #password').first().fill(PASSWORD);
  await page.getByRole('button', { name: /sign in|log ?in|continue|submit/i }).first().click()
    .catch(() => page.locator('button[type="submit"]').first().click());
  await page.waitForURL((u) => !/\/login/.test(u.pathname), { timeout: 60000 });

  // --- what you get (detailed cut) ----------------------------------------
  if (runs('title') && DETAIL) { await card(page, BOX.whatYouGet, 8500); }

  // --- install: the one command and the banner ----------------------------
  if (runs('install')) {
    await terminalCard(page, BOX.install, TERMINAL.install, { step: 230, hold: 5200 });
    await clearCard(page);
  }

  // --- the drive fills (detailed cut) -------------------------------------
  if (runs('install') && DETAIL) {
    await terminalCard(page, BOX.driveFill, TERMINAL.drop, { step: 300, hold: 3200 });
    await say(page, BOX.driveFillCap, 6000);
    await clearCard(page);
  }

  // --- the folder is the interface: ask, and get a citation ---------------
  await go(page, `${BASE}:3080/c/new`);
  await composer(page).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByRole('button', { name: /close sidebar/i }).first().click({ timeout: 4000 }).catch(() => {});

  if (runs('ask')) {
    // Advanced mode so the department agents (Legal assistant, Hr assistant)
    // are selectable; Basic talks to the bare model with no drive behind it.
    await page.evaluate(() => {
      try { localStorage.setItem('uiMode', JSON.stringify('advanced')); localStorage.setItem('uiModeIntroSeen', 'true'); } catch {}
    });
    await go(page, `${BASE}:3080/c/new`);
    await composer(page).waitFor({ state: 'visible', timeout: 60000 });
    await page.locator('#ui-mode-intro-dismiss').click({ timeout: 3000 }).catch(() => {});
    await page.getByRole('button', { name: /close sidebar/i }).first().click({ timeout: 4000 }).catch(() => {});

    if (!DETAIL) { await card(page, BOX.premise, 6500); await say(page, BOX.drop, 5200); await clearCard(page); }
    // Pick the Legal assistant: open the model picker, My Agents, Legal.
    await pickAgent(page, /legal assistant/i);
    await say(page, BOX.ask, 4200);
    await askAndVerify(page, ASK, CITE_TOKENS);
    await beat(page, 800);
    await say(page, BOX.cite, 7000);
    await hush(page);
    await beat(page, 800);

    // Detailed cut: a second question (stays on the document) and a third
    // (declines when the answer is not in the folder).
    if (DETAIL) {
      await askAndVerify(page, ASK_TERM, ASK_TERM_TOKENS);
      await beat(page, 700);
      await say(page, BOX.term, 6500);
      await hush(page);
      await beat(page, 600);
      await askAndVerify(page, ASK_ABSENT, ASK_ABSENT_TOKENS);
      await beat(page, 700);
      await say(page, BOX.absent, 6500);
      await hush(page);
      await beat(page, 800);
    }
  }

  // --- per department: the HR agent answers from its own folder -----------
  if (runs('ask') && DETAIL) {
    await card(page, BOX.separation, 7000);
    await go(page, `${BASE}:3080/c/new`);
    await composer(page).waitFor({ state: 'visible', timeout: 60000 });
    await clearCard(page);
    await pickAgent(page, /hr assistant/i);
    await askAndVerify(page, ASK_HR, ASK_HR_TOKENS);
    await beat(page, 700);
    await say(page, BOX.hr, 7000);
    await hush(page);
    await beat(page, 800);
  }

  // --- Studio routines on the same box ------------------------------------
  // Shown as a routines terminal (real `flows list` output) rather than the
  // live canvas: the box's Studio build renders a project shell, not the graph
  // the film wants, so the honest, legible shot is the list of routines it ships.
  if (runs('studio')) {
    await terminalCard(page, BOX.studio, TERMINAL.flows, { step: 280, hold: 5000 });
    await say(page, BOX.studioCap, 6500);
    await clearCard(page);
  }

  // --- day two (detailed cut): the box looks after itself -----------------
  if (runs('studio') && DETAIL) {
    await terminalCard(page, BOX.dayTwo, TERMINAL.status, { step: 240, hold: 4200 });
    await say(page, BOX.dayTwoCap, 5600);
    await clearCard(page);
    await terminalCard(page, { ...BOX.dayTwo, head: 'Update, and roll back on its own', eyebrow: 'DAY TWO' },
      TERMINAL.update, { step: 300, hold: 4400 });
    await clearCard(page);
  }

  // --- from home: the mesh -------------------------------------------------
  if (runs('mesh')) {
    await go(page, `${BASE}:3080/c/new`);
    await terminalCard(page, BOX.mesh, TERMINAL.mesh, { step: 300, hold: 4600 });
    await say(page, BOX.meshStatus, 5600);
    await clearCard(page);
    await terminalCard(page, { ...BOX.mesh, head: 'One file invites a laptop', eyebrow: 'FROM HOME' },
      TERMINAL.invite, { step: 300, hold: 4200 });
    await say(page, BOX.meshInvite, 6200);
    await clearCard(page);
  }

  // --- the honest edges (detailed cut) ------------------------------------
  if (runs('mesh') && DETAIL) await card(page, BOX.notYet, 8500);

  if (runs('close')) await card(page, BOX.close, 8000);

  await page.close(); await ctx.close(); await browser.close();
  console.log('done');
}

main().catch(async (e) => {
  console.error(`\nStopped: ${e.message}`);
  try { if (current) await current.screenshot({ path: 'recording/where-it-stopped.png' }); } catch {}
  process.exit(1);
});
